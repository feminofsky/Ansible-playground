# Infisical Kubernetes Auth Setup

Pods using `SecretProviderClass` (e.g. blumefy-web-app) authenticate to Infisical via **Kubernetes Auth**: the pod's ServiceAccount JWT is sent to Infisical, which validates it and returns secrets.

**Error:** `Kubernetes auth method not found for identity` means the identity in Infisical does not have Kubernetes Auth configured.

**Error:** `Local IPs not allowed as URL` — The playbook sets `ALLOW_INTERNAL_IP_CONNECTIONS=true` in Infisical's secrets so Kubernetes auth can use `kubernetes.default.svc.cluster.local` (which resolves to 10.43.0.1). Re-run the Infisical role to apply.

---

## Prerequisites

1. **ClusterRoleBinding** — The playbook grants `app-sa` (in dev/prod) the `system:auth-delegator` role. Run:

   ```bash
   ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags secrets_store_csi --ask-vault-pass
   ```

2. **Identity and project in Infisical** — Create an identity and add it to your project. The SPC uses:
   - `identityId`: from values (or hardcoded in helm base)
   - `projectId`: from values (or hardcoded in helm base)

---

## Configure Kubernetes Auth in Infisical

1. **Open Infisical** — https://infisical.blumefy.local (on VPN) or `kubectl port-forward -n infisical svc/infisical 8080:8080`

2. **Create or edit an identity**
   - Organization Settings → Access Control → Identities → Create identity
   - Or use an existing identity

3. **Set authentication to Kubernetes Auth**
   - Edit the identity → Authentication
   - Remove Universal Auth if present
   - Add **Kubernetes Auth** with:
     - **Token Reviewer JWT**: leave empty (we use Option 2: client JWT as reviewer)
     - **Kubernetes Host**: `https://kubernetes.default.svc` (or your API server URL)
     - **CA Certificate**: optional; for in-cluster Infisical, often not needed
     - **Allowed Service Account Names**: `app-sa`
     - **Allowed Namespaces**: `dev,prod` (comma-separated)

4. **Add identity to the project**
   - Project Settings → Access Control → Machine Identities → Add identity
   - Choose the identity and a role with access to the required secrets

5. **Set identityId and projectId in your app values**
   - Copy the identity ID from Infisical (Organization → Identities → your identity)
   - Copy the project ID from Infisical (Project Settings)
   - Add to your service values (e.g. `services/blumefy-web-app/values.yaml` or overlay):
     ```yaml
     infisical:
       identityId: "your-identity-uuid"
       projectId: "your-project-uuid"
     ```
   - Commit and push; Argo CD will sync the updated SecretProviderClass

---

## Verify

After configuring, sync the Application in Argo CD. The pod should start and mount secrets from Infisical.

If it still fails:
- Check identity has Kubernetes Auth (not Universal Auth)
- Ensure Allowed Service Account Names = `app-sa` and Allowed Namespaces = `dev,prod`
- Confirm the identity is added to the project with secret access
