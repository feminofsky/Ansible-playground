# Bugsink (VPN-only) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Bugsink to the Ansible-driven K3s cluster via a new role and Traefik IngressRoute, exposed VPN-only at https://bugsink.blumefy.local.

**Architecture:** New role `roles/bugsink` installs Bugsink using the community Helm chart; Traefik template gains a conditional IngressRoute; vars and site.yml get Bugsink options and a new phase.

**Tech Stack:** Ansible, Helm, Kubernetes (K3s), Traefik IngressRoute, Ansible Vault.

---

## Task 1: Add Bugsink variables to group_vars

**Files:**
- Modify: `inventory/group_vars/all/vars.yml`

**Step 1:** Add a Bugsink section after the Infisical block (e.g. after `infisical_node: node1`), before the Monitoring section.

Add:

```yaml
# ─── Bugsink (self-hosted error tracking, VPN-only) ─
bugsink_enabled: true
bugsink_namespace: bugsink
bugsink_helm_chart_version: ""   # Pin e.g. "1.2.3" for reproducibility; empty = latest
bugsink_postgresql_size: 5Gi
```

**Step 2:** Append `bugsink.blumefy.local` to the `vpn_internal_hosts` list in the same file (add one line to the list that includes `dashboard.blumefy.local`, `argocd.blumefy.local`, etc.).

**Step 3:** Commit.

```bash
git add inventory/group_vars/all/vars.yml
git commit -m "chore: add Bugsink vars and VPN host"
```

---

## Task 2: Create role defaults for Bugsink

**Files:**
- Create: `roles/bugsink/defaults/main.yml`

**Step 1:** Create the file with:

```yaml
---
bugsink_enabled: false
bugsink_namespace: bugsink
bugsink_helm_chart_version: ""
bugsink_postgresql_size: 5Gi
```

**Step 2:** Commit.

```bash
git add roles/bugsink/defaults/main.yml
git commit -m "feat(bugsink): add role defaults"
```

---

## Task 3: Create Bugsink Helm values template

**Files:**
- Create: `roles/bugsink/templates/bugsink-values.yml.j2`

**Step 1:** Create the template. Use the chart’s values structure: `baseUrl`, `secretKey` (existingSecret), `admin` (optional existingSecret or auth), `ingress.enabled: false`, `postgresql.enabled: true`, `postgresql.primary.persistence.size`. Ensure `baseUrl` uses `https://bugsink.{{ vpn_internal_domain | default('blumefy.local') }}`.

**Step 2:** If using existingSecret for secretKey, the role will create a K8s secret from vault; reference that secret name and key in the values (e.g. `existingSecret: bugsink-secret`, `existingSecretKey: secret-key`). Same for admin if using existingSecret.

**Step 3:** Commit.

```bash
git add roles/bugsink/templates/bugsink-values.yml.j2
git commit -m "feat(bugsink): add Helm values template"
```

---

## Task 4: Implement Bugsink role tasks (namespace, secret, Helm)

**Files:**
- Create: `roles/bugsink/tasks/main.yml`

**Step 1:** Add a pre-task that ends the play when `bugsink_enabled` is false (same pattern as `roles/infisical/tasks/main.yml` or `roles/monitoring`).

**Step 2:** Assert vault vars: require `vault_bugsink_secret_key`; optionally require admin auth vars if you document admin via secret.

**Step 3:** Add Helm repo `bugsink` with URL `https://bugsink.github.io/helm-charts`; run `helm repo update`. Use `KUBECONFIG: /etc/rancher/k3s/k3s.yaml` on tasks that run Helm/kubectl.

**Step 4:** Create namespace `bugsink` via `kubectl create namespace {{ bugsink_namespace }} --dry-run=client -o yaml | kubectl apply -f -`.

**Step 5:** Create a K8s Secret in namespace `bugsink` that holds the secret key (from `vault_bugsink_secret_key`). Template a small manifest (e.g. `roles/bugsink/templates/bugsink-secret.yml.j2`) or use `kubectl create secret generic` from the role. Secret name used in values (e.g. `bugsink-secret`) with key `secret-key`.

**Step 6:** Template Helm values to `/tmp/bugsink-values.yml` from `bugsink-values.yml.j2`.

**Step 7:** Run `helm upgrade --install bugsink bugsink/bugsink --namespace {{ bugsink_namespace }} --values /tmp/bugsink-values.yml`. If `bugsink_helm_chart_version` is set, add `--version {{ bugsink_helm_chart_version }}`.

**Step 8:** Wait for the Bugsink app pod (e.g. `kubectl wait pod -l app.kubernetes.io/name=bugsink --namespace {{ bugsink_namespace }} --for=condition=Ready --timeout=600s`). Adjust label if the chart uses a different one (check after first run).

**Step 9:** Add a debug task that prints access info: VPN URL `https://bugsink.{{ vpn_internal_domain }}` and note to add host to `wireguard-configs` if needed.

**Step 10:** Commit.

```bash
git add roles/bugsink/tasks/main.yml roles/bugsink/templates/bugsink-secret.yml.j2
git commit -m "feat(bugsink): add role tasks and secret template"
```

---

## Task 5: Add Bugsink IngressRoute to Traefik VPN template

**Files:**
- Modify: `roles/traefik/templates/ingressroute-vpn-internal.yml.j2`

**Step 1:** After the Infisical block (`{% if infisical_enabled | default(false) %}...{% endif %}`), add a conditional block:

`{% if bugsink_enabled | default(false) %}`  
… IngressRoute YAML for host `bugsink.{{ vpn_internal_domain | default('blumefy.local') }}`, middleware `vpn-allowlist`, service in namespace `bugsink` port 8000, TLS secret `tls-blumefy-local`.  
`{% endif %}`

**Step 2:** Use the same structure as the existing IngressRoutes (name e.g. `bugsink-vpn`, namespace `traefik`). Service name: `bugsink` (Helm release name); if the chart creates a different service name, use a variable or fix after first deploy.

**Step 3:** Commit.

```bash
git add roles/traefik/templates/ingressroute-vpn-internal.yml.j2
git commit -m "feat(traefik): add Bugsink VPN IngressRoute"
```

---

## Task 6: Add Bugsink phase to site.yml

**Files:**
- Modify: `playbooks/site.yml`

**Step 1:** Add a new phase (e.g. Phase 5d) after Phase 5c (Secrets Store CSI), before Phase 6. Play: Install Bugsink (node1, tag `bugsink`). Include a pre_task that skips the play when `bugsink_enabled` is false.

**Step 2:** Add a comment in the tags section at the top: `#   --tags bugsink   Bugsink (error tracking, VPN-only)`.

**Step 3:** Commit.

```bash
git add playbooks/site.yml
git commit -m "feat(site): add Bugsink phase and tag"
```

---

## Task 7: Document vault variables and wireguard-configs

**Files:**
- Modify: `inventory/group_vars/all/vault.yml` (or create placeholder if encrypted — document in README or vars comment)
- Optional: `wireguard-configs/vpn-hosts.txt` or `wireguard-configs/add-vpn-hosts.sh` if Bugsink host must be listed there

**Step 1:** In `vars.yml` (or in a comment in the Bugsink section), document that vault must define `vault_bugsink_secret_key` (e.g. 50+ char random string). Optionally document `vault_bugsink_admin_auth` as `username:password` for initial superuser.

**Step 2:** If the project’s VPN setup requires explicit host entries for `bugsink.blumefy.local`, add `bugsink.blumefy.local` to the relevant file in `wireguard-configs/` (or note in design doc that internal dashboard / DNS already covers it).

**Step 3:** Commit.

```bash
git add inventory/group_vars/all/vars.yml
# if wireguard-configs changed:
# git add wireguard-configs/...
git commit -m "docs: document Bugsink vault vars and VPN host"
```

---

## Task 8: Manual verification

**Steps:**

1. Ensure `vault_bugsink_secret_key` is set in vault (e.g. `ansible-vault edit inventory/group_vars/all/vault.yml` and add a long random value).
2. Run: `ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags bugsink,traefik --ask-vault-pass` (Traefik so IngressRoute is applied; adjust inventory path if different).
3. Connect via VPN; open `https://bugsink.blumefy.local` and confirm login (create superuser or use admin auth if configured).
4. If the Helm chart’s service name is not `bugsink`, run `kubectl get svc -n bugsink` and update the IngressRoute in `ingressroute-vpn-internal.yml.j2` to use the correct service name, then re-run Traefik tag and re-verify.

---

## Execution options

**Plan complete and saved to `docs/plans/2026-02-22-bugsink-implementation.md`.**

Two execution options:

1. **Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open a new session with executing-plans and run the plan with checkpoints there.

Which approach do you want?
