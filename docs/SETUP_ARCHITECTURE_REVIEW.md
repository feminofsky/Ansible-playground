# Setup, Architecture & Tools — Comprehensive Review

**Date:** February 2026  
**Scope:** Ansible repo (inventory, playbooks, roles), Argo CD layout, security, runbooks, and validation.

---

## 1. What You Have (Summary)

### 1.1 Architecture

| Layer | Technology | Notes |
|-------|------------|--------|
| **Nodes** | 2× Contabo VPS (node1, node2) | Public IPs in `inventory/hosts.yml` |
| **SSH** | Port 2222, `deploy` user, key-based | Hardened in `common` + `security` |
| **VPN** | WireGuard 10.10.10.0/24 | Cluster + API over VPN when `wireguard_enabled: true` |
| **Firewall** | UFW | Cloudflare-only 80/443 when proxy enabled; VPN + K3s rules |
| **Kubernetes** | K3s HA (etcd) | v1.34.0+k3s1, API on VPN only |
| **Load balancer** | MetalLB | Single IP = node1 (Traefik) |
| **Ingress** | Traefik v3 (Helm 39.0.1) | Cloudflare proxy, forwarded headers, optional AOP |
| **Secrets** | Ansible Vault + Infisical (in-cluster) | Vault for bootstrap/Ansible; Infisical for apps |
| **GitOps** | Argo CD | ApplicationSet → `Blumefy/gitops-services` |
| **Namespaces** | `dev`, `prod` | Redis + RabbitMQ per env (Phase 7) |
| **Monitoring** | Optional | Prometheus + Grafana when `monitoring_enabled: true` (currently false) |

### 1.2 What’s “Running” (by design)

- **Ansible:** Drives everything; no daemon. Run `site.yml` or tagged plays.
- **On nodes:** `sshd`, UFW, Fail2Ban, WireGuard (if enabled), K3s, Helm-managed Traefik/MetalLB/Infisical/Argo CD.
- **In cluster:** Traefik, MetalLB, Infisical (node1-pinned), Argo CD, dev/prod Redis+RabbitMQ; apps via Argo CD from Git.

### 1.3 Key Files

- **Inventory:** `inventory/hosts.yml` (node IPs, user, port), `inventory/group_vars/all/vars.yml` (config), `vault.yml` (secrets).
- **Main entrypoint:** `playbooks/site.yml` (phases 1–7 + verify).
- **Security/UFW:** `playbooks/refresh-ufw.yml`, `roles/security/`, Cloudflare IP list in `vars.yml`.

---

## 2. Critical Issues to Fix

### 2.1 **update.yml — FIXED**

- **Was:** `playbooks/update.yml` targeted node3, node2, node1; inventory has only node1 and node2.
- **Fix applied:** The playbook is now inventory-driven: it updates **non-init nodes first** (e.g. node2), then **the init node last** (node1), using `groups['control_plane']`. It works for 2 or 3+ nodes without code changes. `vars.yml` also defines `update_init_node` and `update_other_nodes` for reference/overrides.

### 2.2 **drain-node.yml and README reference node3**

- **Issue:** Examples use `target_node=node3`; with only node1/node2, that’s misleading.
- **Fix:** Use `target_node=node2` (or `node1`) in examples, or add a short note: “Use a node that exists in your inventory (e.g. node1 or node2).”

### 2.3 **Vault: ensure all required keys exist**

- **Issue:** Several roles assume vault variables are defined. If any are missing, plays fail mid-run.
- **Required in vault.yml (see README):**  
  `vault_deploy_password`, `vault_k3s_token`, `vault_grafana_password` (if monitoring),  
  `vault_infisical_auth_secret`, `vault_infisical_encryption_key` (if Infisical),  
  `vault_dev_redis_password`, `vault_dev_rabbitmq_user`, `vault_dev_rabbitmq_password`,  
  `vault_prod_redis_password`, `vault_prod_rabbitmq_user`, `vault_prod_rabbitmq_password`,  
  and for private Argo CD repo: `vault_argocd_repo_ssh_key` (or use `argocd_repo_ssh_key_file`).
- **Recommendation:** Add a small “pre-flight” play or separate playbook that asserts all required vault vars are defined (with clear messages), so you fail fast before changing state.

---

## 3. Security & Hardening

### 3.1 Already in good shape

- SSH on 2222, key-based, non-root `deploy` user.
- UFW default deny incoming; 80/443 restricted to Cloudflare + VPN when proxy enabled.
- K3s API (6443) only from VPN (or `k3s_api_allowed_ips` when not using WireGuard).
- Fail2Ban with configurable `maxretry` / `bantime` / `findtime`.
- Cloudflare: forwarded headers (real IP), optional Authenticated Origin Pulls (AOP) in Traefik.
- VPN-only internal UIs (*.blumefy.local) with self-signed TLS and WireGuard allowlist.
- Docs: `CLOUDFLARE_TRAEFIK_SECURITY.md`, `VPN_INTERNAL_DASHBOARD.md`, `RECOVERY.md`.

### 3.2 Recommended improvements

1. **Authenticated Origin Pulls (AOP)**  
   - Currently commented out: `# traefik_cloudflare_origin_pull_enabled: false`.  
   - Enabling AOP (and placing Cloudflare’s CA at `roles/traefik/files/cloudflare-origin-pull-ca.pem`) ensures only Cloudflare can complete TLS to your origin. Strongly recommended if you rely on Cloudflare proxy.

2. **Cloudflare IP list**  
   - `traefik_cloudflare_ip_ranges` in `vars.yml` is a static list. Cloudflare occasionally updates [their IPs](https://www.cloudflare.com/ips/).  
   - Consider: a periodic task (or doc step) to refresh this list, or a small script/play that fetches and updates the variable/file so UFW and Traefik stay in sync.

3. **Vault password**  
   - `ansible.cfg` has `vault_password_file = ~/.vault_pass`. Ensure `~/.vault_pass` exists and is `chmod 600` so playbooks don’t accidentally prompt in automation.

4. **Secrets on disk**  
   - Argo CD repo key: `argocd_repo_ssh_key_file` points to `playbook_dir/../argocd-deploy`. That path is gitignored; ensure it’s only on trusted machines and not committed.

---

## 4. Reliability & Operations

### 4.1 Single points of failure

- **Traefik:** One replica (documented: PVC ReadWriteOnce). Acceptable for your size; document that scaling would require shared storage or different storage class.
- **MetalLB:** Single IP (node1); if node1 is down, ingress IP is lost. Aligns with “node1 = ingress” design; document failover (e.g. promote another node / change pool) if you grow.
- **Infisical / Argo CD:** Pinned to node1 to avoid cross-node DNS issues. If node1 is down, those services are down until node1 is back or you move them.

### 4.2 Idempotency and safety

- **refresh-ufw.yml:** Uses `failed_when: false` on “delete allow 80/443” so missing rules don’t fail the run. Good.
- **site.yml:** Phase completion check skips bootstrap when `/etc/ansible/bootstrap-complete` exists. Tagged plays allow re-running specific phases (e.g. `--tags traefik`).
- **K3s:** Install is skipped when binary exists unless `k3s_force_reinstall` is set. Config changes still applied.

### 4.3 Versions (as of review)

- **K3s:** v1.34.0+k3s1 — valid; newer v1.35.x exists if you want to plan an upgrade.
- **Traefik Helm:** 39.0.1 (Traefik v3).
- **MetalLB:** v0.15.3.
- **Argo CD Helm:** 9.4.3.
- **Infisical:** v0.158.2.

Consider a short “versions” section in `vars.yml` or a doc that states support policy (e.g. “we bump K3s/Traefik after testing in dev”).

---

## 5. Validation & Testing

### 5.1 Gaps

- **No CI/CD:** No `.github/workflows` or other automation for lint/run.
- **No automated tests:** No Molecule, no automated Ansible playbook runs in CI.
- **Manual checks:** Final verify in `site.yml` only prints `kubectl get nodes` and `kubectl get pods -A`; no assertion on “all critical pods Ready”.

### 5.2 What exists

- **test-cross-node-pods.yml:** Validates cross-node pod networking (server on node1, client on node2). Good to run after cluster changes.
- **cluster-resource-report.yml:** Present; can be used for ad-hoc resource visibility.
- **infisical-unlock-migrations.yml:** For Infisical migrations.

### 5.3 Recommended validations

1. **Pre-flight playbook**  
   - Ping + vault assertions + (optional) version checks. Run before `site.yml` or in CI to fail fast.

2. **Post-site sanity**  
   - After `site.yml`: assert core pods (traefik, argocd, infisical if enabled) are Ready in expected namespaces; optional HTTP check to Traefik or internal dashboard.

3. **Periodic checks**  
   - Optional: a small playbook that runs `kubectl get nodes`, `kubectl get pods -A`, and optionally `ufw status` on control_plane, and writes a short report or exits non-zero if something critical is down.

4. **Linting**  
   - `ansible-lint` (and optionally `yamllint`) in CI or pre-commit to catch simple mistakes.

---

## 6. Documentation & Repo Layout

### 6.1 Strengths

- README with prerequisites, bootstrap, site run, tags, and post-setup (VPN UIs, Argo CD, team access).
- Focused docs: Cloudflare/Traefik, VPN dashboard, Argo CD submodule, Infisical K8s auth, Recovery.
- Playbook headers describe usage and tags; vars.yml is well-commented.

### 6.2 Gaps

- **Argo CD vs Git repo:** ApplicationSet watches `applications/*.yaml` in the **Git** repo (`Blumefy/gitops-services`). This repo’s `argocd/` holds structure and examples; actual app list lives in the other repo. Make this explicit in README or `argocd/README.md` (“Application manifests live in gitops-services; here we document structure and examples”).
- **Runbook index:** A single “Operations” or “Runbooks” doc listing playbooks (bootstrap, site, update, refresh-ufw, drain-node, migrate-to-vpn, add-vpn-tls-san, k3s-rotate-cert-vpn, infisical-unlock-migrations, test-cross-node-pods) with one-line purpose and when to run would help.

---

## 7. Improvement Checklist (Prioritized)

| Priority | Item | Action |
|----------|------|--------|
| **P0** | ~~update.yml assumes node3~~ | ✅ Done — playbook is inventory-driven. |
| **P0** | drain/README examples | Use node1/node2 in examples or add a note. |
| **P1** | Vault pre-flight | Add play or playbook that asserts required vault vars. |
| **P1** | Cloudflare IP list | Document or automate periodic refresh from cloudflare.com/ips. |
| **P1** | AOP | Enable and configure Authenticated Origin Pulls if using Cloudflare proxy. |
| **P2** | Post-site verification | After site.yml, assert critical pods Ready (and optional HTTP check). |
| **P2** | Runbook index | Add Operations/Runbooks doc with playbook list and when to run. |
| **P2** | Argo CD vs Git | Clarify in README/argocd that app list is in gitops-services repo. |
| **P3** | CI/lint | Add ansible-lint (and optionally yamllint) in CI or pre-commit. |
| **P3** | Versions doc | Document version support/upgrade policy for K3s/Traefik/Argo CD. |

---

## 8. Quick Validation Commands

Run these to validate current state (from a machine that can reach the nodes and has vault access):

```bash
# Connectivity
ansible all -i inventory/hosts.yml -m ping

# Vault (ensure password loads; don’t expose secrets)
ansible all -i inventory/hosts.yml -m debug -a "var=hostvars[inventory_hostname]"
# Or run a minimal play that uses one vault var and --check

# Full apply (after fixing update.yml if you use it)
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --ask-vault-pass

# UFW refresh (no vault needed if vars are in vars.yml)
ansible-playbook playbooks/refresh-ufw.yml -i inventory/hosts.yml

# Cross-node networking
ansible-playbook playbooks/test-cross-node-pods.yml -i inventory/hosts.yml
```

---

**Summary:** The setup is coherent and well-documented for a 2-node K3s cluster with WireGuard, Cloudflare, Traefik, Infisical, and Argo CD. The only blocking issue is **update.yml** targeting a non-existent node3; fixing that and adding vault pre-flight plus the suggested validations will make the stack more robust and easier to operate.
