# Longhorn, Falco, and Velero Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Install Longhorn (default StorageClass), Falco (runtime security), and Velero (backup to external S3); expose Longhorn UI at longhorn.blumefy.local and add Longhorn, Falco, and Velero to the internal dashboard (Falco/Velero as Grafana dashboard links).

**Architecture:** Three new Ansible roles (longhorn, falco, velero); Traefik gains Longhorn IngressRoute and internal dashboard cards/nav for all three; monitoring role provisions Falco and Velero Grafana dashboards; vars and site.yml updated.

**Tech Stack:** Ansible, Helm, Kubernetes (K3s), Traefik IngressRoute, Longhorn, Falco, Velero, Grafana, S3-compatible object storage.

---

## Task 1: Add Longhorn, Falco, and Velero variables to group_vars

**Files:**
- Modify: `inventory/group_vars/all/vars.yml`

**Step 1:** Add a new section after Monitoring (e.g. after `monitoring_traefik_tracing_enabled`) and before Fail2Ban. Insert:

```yaml
# ─── Longhorn (storage, default StorageClass) ───────
longhorn_enabled: true
longhorn_namespace: longhorn-system

# ─── Falco (runtime security) ───────────────────────
falco_enabled: true
falco_namespace: falco

# ─── Velero (backup to external S3) ─────────────────
velero_enabled: true
velero_namespace: velero
velero_s3_bucket: ""          # Set to your bucket name (vault or vars)
velero_s3_region: ""          # e.g. us-east-1 or auto for R2
velero_s3_url: ""             # Optional: S3-compatible endpoint (R2, B2, etc.)
velero_schedule_enabled: true
velero_schedule_cron: "0 2 * * *"
velero_schedule_retention: "7"
```

**Step 2:** Append `longhorn.blumefy.local` to the `vpn_internal_hosts` list in the same file (one line in the list with `dashboard.blumefy.local`, etc.).

**Step 3:** Commit.

```bash
git add inventory/group_vars/all/vars.yml
git commit -m "chore: add Longhorn, Falco, Velero vars and longhorn VPN host"
```

---

## Task 2: Create Longhorn role defaults and tasks

**Files:**
- Create: `roles/longhorn/defaults/main.yml`
- Create: `roles/longhorn/tasks/main.yml`

**Step 1:** Create `roles/longhorn/defaults/main.yml`:

```yaml
---
longhorn_enabled: false
longhorn_namespace: longhorn-system
longhorn_helm_chart_version: ""   # empty = latest
```

**Step 2:** Create `roles/longhorn/tasks/main.yml` with: meta end_play when not longhorn_enabled; add Helm repo `longhorn` URL `https://charts.longhorn.io`; helm repo update; create namespace `longhorn-system`; template longhorn values (minimal or empty) to `/tmp/longhorn-values.yml`; helm upgrade --install longhorn longhorn/longhorn --namespace longhorn-system --values /tmp/longhorn-values.yml (optionally --version); wait for longhorn-manager or frontend pod Ready; patch StorageClass longhorn to set default (kubectl patch storageclass longhorn -p '{"metadata": {"annotations": {"storageclass.kubernetes.io/is-default-class": "true"}}}'); unset default on other StorageClasses (kubectl get storageclass -o jsonpath='{.items[*].metadata.name}' then for each that has is-default-class=true and name != longhorn, patch to false).

**Step 3:** If you use a values template, create `roles/longhorn/templates/longhorn-values.yml.j2` with minimal content (e.g. defaultSettings if needed); otherwise use a minimal inline values file or omit --values and use chart defaults.

**Step 4:** Commit.

```bash
git add roles/longhorn/
git commit -m "feat(longhorn): add role with Helm install and default StorageClass"
```

---

## Task 3: Add Longhorn phase and tag to site.yml

**Files:**
- Modify: `playbooks/site.yml`

**Step 1:** After Phase 4 (MetalLB) and before Phase 5 (Traefik), add a new phase:

```yaml
# ── Phase 4b: Install Longhorn (node1 only) ─────────
- name: Phase 4b — Install Longhorn
  hosts: node1
  become: yes
  tags: longhorn
  pre_tasks:
    - meta: end_play
      when: not (longhorn_enabled | default(false))
  vars:
    ansible_port: "{{ ssh_port }}"
  roles:
    - longhorn
```

**Step 2:** Add a short comment in the tags section at the top for `--tags longhorn`.

**Step 3:** Commit.

```bash
git add playbooks/site.yml
git commit -m "feat(site): add Phase 4b Longhorn"
```

---

## Task 4: Add Longhorn IngressRoute and dashboard entry (Traefik)

**Files:**
- Modify: `roles/traefik/templates/ingressroute-vpn-internal.yml.j2`
- Modify: `roles/traefik/templates/internal-dashboard-index.html.j2`

**Step 1:** In `ingressroute-vpn-internal.yml.j2`, after the jaeger block (`{% endif %}`), add:

```yaml
{% if longhorn_enabled | default(false) %}
---
apiVersion: {{ traefik_crd_api_group | default('traefik.io') }}/v1alpha1
kind: IngressRoute
metadata:
  name: longhorn-vpn
  namespace: {{ traefik_namespace }}
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`longhorn.{{ vpn_internal_domain | default('blumefy.local') }}`)
      kind: Rule
      middlewares:
        - name: vpn-allowlist
          namespace: {{ traefik_namespace }}
      services:
        - name: longhorn-frontend
          port: 80
          namespace: longhorn-system
  tls:
    secretName: tls-blumefy-local
{% endif %}
```

(Ensure the service name matches the Longhorn chart — typically `longhorn-frontend` in `longhorn-system`.)

**Step 2:** In `internal-dashboard-index.html.j2`, add a "Storage & Security" section in the cards grid: after the "Other" section (MetalLB card), add a new section label and Longhorn card when `longhorn_enabled`:

```jinja2
      {% if longhorn_enabled | default(false) %}
      <span class="section-label">Storage & Security</span>
      <a href="https://longhorn.{{ vpn_internal_domain | default('blumefy.local') }}" class="card longhorn" target="_blank" rel="noopener noreferrer">
        <span class="icon">💾</span>
        <h2>Longhorn</h2>
        <p>Storage & volumes</p>
      </a>
      {% endif %}
```

Add a matching nav item in the sidebar (after "Other" / MetalLB):

```jinja2
      {% if longhorn_enabled | default(false) %}
      <a href="#" class="nav-item" data-app="longhorn" data-url="https://longhorn.{{ vpn_internal_domain | default('blumefy.local') }}" data-embed="true" data-label="Longhorn">
        <span class="label">💾 Longhorn</span>
        <span class="ext" title="Open in new tab">↗</span>
      </a>
      {% endif %}
```

**Step 3:** Add CSS for `.card.longhorn .icon` if desired (e.g. background color); optional.

**Step 4:** Commit.

```bash
git add roles/traefik/templates/ingressroute-vpn-internal.yml.j2 roles/traefik/templates/internal-dashboard-index.html.j2
git commit -m "feat(traefik): Longhorn VPN IngressRoute and internal dashboard entry"
```

---

## Task 5: Create Falco role (defaults, tasks, Helm)

**Files:**
- Create: `roles/falco/defaults/main.yml`
- Create: `roles/falco/tasks/main.yml`
- Create: `roles/falco/templates/falco-values.yml.j2` (optional; can use chart defaults)

**Step 1:** Create `roles/falco/defaults/main.yml`:

```yaml
---
falco_enabled: false
falco_namespace: falco
falco_helm_chart_version: ""
falco_driver: "ebpf"
falco_metrics_enabled: true
```

**Step 2:** Create `roles/falco/tasks/main.yml`: meta end_play when not falco_enabled; add Helm repo `falcosecurity` URL `https://falco.org/charts`; helm repo update; create namespace; template values (falco.driver, falco.jsonOutput, metrics if enabled) to `/tmp/falco-values.yml`; helm upgrade --install falco falcosecurity/falco --namespace falco --values /tmp/falco-values.yml; wait for DaemonSet falco pods Ready.

**Step 3:** Create minimal `roles/falco/templates/falco-values.yml.j2` with driver and metrics (e.g. `falco.driver: {{ falco_driver }}`, `falco.jsonOutput: false`, and chart option for metrics if available — check falcosecurity/falco chart values).

**Step 4:** Commit.

```bash
git add roles/falco/
git commit -m "feat(falco): add role with Helm install and metrics"
```

---

## Task 6: Add Falco phase and Falco/Velero dashboard links to internal dashboard

**Files:**
- Modify: `playbooks/site.yml`
- Modify: `roles/traefik/templates/internal-dashboard-index.html.j2`

**Step 1:** In `site.yml`, after Phase 4b (Longhorn), add Phase 5a — Install Falco (hosts: node1, tag: falco, pre_tasks meta end_play when not falco_enabled, role falco).

**Step 2:** In `internal-dashboard-index.html.j2`, in the same "Storage & Security" section (or right after Longhorn card), add Falco card when falco_enabled and monitoring_enabled, linking to `https://grafana.{{ vpn_internal_domain }}/d/falco` (Grafana Falco dashboard). Add matching nav item. Use label "Falco" and description "Runtime security (Grafana)".

**Step 3:** Add Velero card and nav when velero_enabled and monitoring_enabled, link to `https://grafana.{{ vpn_internal_domain }}/d/velero`. Label "Velero", description "Backups (Grafana)".

**Step 4:** Commit.

```bash
git add playbooks/site.yml roles/traefik/templates/internal-dashboard-index.html.j2
git commit -m "feat(site): add Falco phase; add Falco and Velero to internal dashboard (Grafana links)"
```

---

## Task 7: Create Velero role (defaults, tasks, S3 secret, Helm)

**Files:**
- Create: `roles/velero/defaults/main.yml`
- Create: `roles/velero/tasks/main.yml`
- Create: `roles/velero/templates/velero-credentials-secret.yml.j2` (or use kubectl create secret from vars)
- Create: `roles/velero/templates/velero-values.yml.j2`

**Step 1:** Create `roles/velero/defaults/main.yml` with velero_enabled, velero_namespace, velero_s3_bucket, velero_s3_region, velero_s3_url, velero_schedule_* and chart version default.

**Step 2:** In `roles/velero/tasks/main.yml`: meta end_play when not velero_enabled; assert vault_velero_s3_access_key and vault_velero_s3_secret_key are defined; assert velero_s3_bucket and velero_s3_region are set; add Helm repo vmware-tanzu https://vmware-tanzu.github.io/helm-charts; create namespace velero; create K8s Secret in velero namespace with S3 credentials (from vault); template velero-values.yml.j2 to /tmp/velero-values.yml (configuration.backupStorageLocation with bucket, region, s3Url if set, and credentials from secret); helm upgrade --install velero vmware-tanzu/velero --namespace velero --values /tmp/velero-values.yml; optionally create Velero Schedule via kubectl apply (YAML) when velero_schedule_enabled.

**Step 3:** Create secret template and values template. Velero Helm chart expects credentials in a secret; use `configuration.backupStorageLocation[0].credential` or chart’s `credentials.secretContents` / `initContainers` pattern per chart docs.

**Step 4:** Commit.

```bash
git add roles/velero/
git commit -m "feat(velero): add role with S3 backend and default schedule"
```

---

## Task 8: Add Velero phase to site.yml

**Files:**
- Modify: `playbooks/site.yml`

**Step 1:** Add Phase 5f — Install Velero after Falco (or after Bugsink), with tag velero and pre_tasks meta end_play when not velero_enabled, role velero.

**Step 2:** Add `--tags velero` to the tags comment at top.

**Step 3:** Commit.

```bash
git add playbooks/site.yml
git commit -m "feat(site): add Phase 5f Velero"
```

---

## Task 9: Provision Falco and Velero Grafana dashboards (monitoring role)

**Files:**
- Create: `roles/monitoring/files/dashboard-falco.json`
- Create: `roles/monitoring/files/dashboard-velero.json`
- Modify: `roles/monitoring/tasks/main.yml`

**Step 1:** Create minimal Grafana dashboard JSON for Falco with `"uid": "falco"` and at least one panel (e.g. Prometheus query for falco_events or falco_alerts if Falco exports such metrics). If Falco chart does not expose metrics by default, add a panel that shows a placeholder or document that Falco metrics need to be enabled and scraped; the link from the internal dashboard will still work once the dashboard exists.

**Step 2:** Create minimal Grafana dashboard JSON for Velero with `"uid": "velero"` and panels for backup/schedule status (e.g. velero_backup_* metrics if Velero is configured to expose Prometheus metrics). Otherwise placeholder panels.

**Step 3:** In `roles/monitoring/tasks/main.yml`, add tasks (when monitoring_grafana_enabled) to copy dashboard-falco.json and dashboard-velero.json to the host and create ConfigMaps (e.g. grafana-dashboard-falco, grafana-dashboard-velero) in the monitoring namespace, and add them to the same dashboard provider / sidecar that already provisions dashboard-apps-infra (so Grafana picks them up).

**Step 4:** Commit.

```bash
git add roles/monitoring/files/dashboard-falco.json roles/monitoring/files/dashboard-velero.json roles/monitoring/tasks/main.yml
git commit -m "feat(monitoring): provision Falco and Velero Grafana dashboards"
```

---

## Task 10: Update VPN and internal dashboard docs

**Files:**
- Modify: `docs/VPN_INTERNAL_DASHBOARD.md` (or equivalent)

**Step 1:** In the table or list of internal apps, add rows for Longhorn (https://longhorn.blumefy.local), Falco (Grafana dashboard link), and Velero (Grafana dashboard link). Note that Longhorn/Falco/Velero are optional and controlled by longhorn_enabled, falco_enabled, velero_enabled.

**Step 2:** Commit.

```bash
git add docs/VPN_INTERNAL_DASHBOARD.md
git commit -m "docs: add Longhorn, Falco, Velero to VPN internal dashboard doc"
```

---

## Execution handoff

Plan complete and saved to `docs/plans/2026-02-22-longhorn-falco-velero-implementation.md`.

**Two execution options:**

1. **Subagent-Driven (this session)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open a new session with executing-plans and run the plan task-by-task with checkpoints.

Which approach?

- If **Subagent-Driven** is chosen: use superpowers:subagent-driven-development in this session.
- If **Parallel Session** is chosen: open a new session in the worktree and use superpowers:executing-plans there.
