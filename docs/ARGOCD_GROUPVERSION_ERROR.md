# Argo CD: "groupVersion shouldn't be empty"

This error appears when Argo CD fails to **load live state** from the cluster (API discovery returns a resource type with empty `groupVersion`). It often happens **when you click Sync**, because the sync path re-runs discovery. The desired state (manifests) is usually fine; the failure is **cluster-side** during API discovery.

## Find the bad resource (cluster-side)

Run on the cluster and look for empty GROUP or VERSION:

```bash
# List all API resources; look for blank GROUP or empty entries
kubectl api-resources -o wide

# Aggregated APIs (extension servers) can return bad discovery
kubectl get apiservice -o wide
# Fix or remove any with AVAILABLE=False or that point to a broken service

# CRDs with conversion webhooks that point to a down/failing service break discovery
kubectl get crd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.conversion.strategy}{"\t"}{.spec.conversion.webhook.clientConfig.service.namespace}/{.spec.conversion.webhook.clientConfig.service.name}{"\n"}{end}' 2>/dev/null
# Ensure any webhook services exist and are reachable, or remove/fix the CRD
```

If you find an APIService or CRD that is broken or its webhook is unavailable, fix or remove it; then restart the application controller and hard-refresh the app.

### Check CRDs used by your app first

Your helm/base app may use these API groups. Inspect their CRDs and fix any that are invalid or have failing webhooks:

```bash
# Traefik IngressRoute (traefik.io/v1alpha1)
kubectl get crd ingressroutes.traefik.io -o yaml 2>/dev/null | head -50

# Secrets Store CSI (if app has secrets:)
kubectl get crd secretproviderclasses.secrets-store.csi.x-k8s.io -o yaml 2>/dev/null | head -50
```

If `kubectl api-resources` or `kubectl get crd` hang or error for a specific group, that group is a strong candidate for the broken discovery.

### Duplicate Traefik CRDs (traefik.containo.us vs traefik.io)

If you see **both** `traefik.containo.us/v1alpha1` and `traefik.io/v1alpha1` for the same kinds (IngressRoute, Middleware, etc.), discovery can fail with "groupVersion shouldn't be empty". This repo uses **traefik.io** (Traefik v3) only; the old **traefik.containo.us** (v2) CRDs are leftovers and can be removed.

**1. Check that no resources use the old API (optional):**
```bash
kubectl get ingressroutes.traefik.containo.us -A 2>/dev/null || true
kubectl get middlewares.traefik.containo.us -A 2>/dev/null || true
```
If these are empty or "no resources found", it's safe to remove the old CRDs.

**2. Delete the old Traefik v2 CRDs:**
```bash
for crd in ingressroutes ingressroutetcps ingressrouteudps middlewares middlewaretcps serverstransports tlsoptions tlsstores traefikservices; do
  kubectl delete crd "${crd}.traefik.containo.us" --ignore-not-found
done
```

**3. Restart Argo CD application controller and hard-refresh the app:**
```bash
kubectl rollout restart deployment/argocd-application-controller -n argocd
```
Then in the UI: Application → Refresh → Hard Refresh, then Sync.

---

## Other causes and fixes

## 1. Resource missing `apiVersion` (Helm charts)

**Cause:** A manifest rendered by Helm has no `apiVersion` (e.g. template whitespace chomping like `{{- with $ -}}` eating the next line).

**Fix:**

- Ensure every resource in `helm/base/templates` has `apiVersion` on its own line after template directives (no `{{- ... -}}` that could strip it).
- If the broken resource is in another repo/chart, add `apiVersion` there and re-sync.

## 2. Force Helm v3 for the Application

**Cause:** Older Helm version or rendering path producing invalid manifests.

**Fix:** In the Application (or ApplicationSet template), set the app to use Helm v3:

```yaml
spec:
  source:
    helm:
      version: v3
```

Or in the Argo CD UI: Application → App Details → Helm Version → v3.

## 3. Clear Argo CD cluster cache

**Cause:** Stale cluster API discovery cache.

**Fix:**

```bash
# Restart repo server to clear caches
kubectl rollout restart deployment/argocd-repo-server -n argocd

# Or invalidate cluster cache for the app (Argo CD UI: Application → "Hard Refresh").
```

## 4. Bad CRD or extension API in the cluster (most likely when error is "load live state")

**Cause:** A CRD (e.g. with a conversion webhook pointing to an unavailable service) or an aggregated APIService causes the API server to return invalid discovery (empty groupVersion). Argo CD then fails when loading live state.

**Fix:**

- Run the "Find the bad resource" commands above.
- Ensure any CRD conversion webhook services are running and reachable.
- For broken/unused CRDs: `kubectl delete crd <name>` (only if you don't need them).
- For broken APIService: fix the backing service or remove the APIService.
- Restart Argo CD application controller after fixing the cluster: `kubectl rollout restart deployment/argocd-application-controller -n argocd`.

## 5. Check rendered manifests

**Cause:** One of the resources in the app’s manifest is invalid.

**Fix:**

- In Argo CD UI: open the Application → "App diff" or "Manifest" and confirm every resource has `apiVersion` and `kind`.
- Or render locally: `helm template release-name helm/base -f services/<app>/values.yaml` and inspect output.

---

**Order of operations:** Try (2) Helm v3 and (3) hard refresh first. If the error persists, inspect manifests (5) and cluster CRDs (4).
