# Longhorn, Falco, and Velero — Design

**Date:** 2026-02-22  
**Status:** Approved

---

## Goal

Install and configure Longhorn (storage), Falco (runtime security), and Velero (backup) on the K3s cluster; make them the default solutions where applicable; expose UIs on the internal dashboard and at `*.blumefy.local` where they exist.

---

## Decisions

| Decision | Choice |
|----------|--------|
| **Structure** | Three separate Ansible roles: `longhorn`, `falco`, `velero` |
| **Longhorn** | Default StorageClass cluster-wide; Helm chart `longhorn/longhorn` |
| **Falco** | DaemonSet on all nodes; default ruleset; metrics to Prometheus/Grafana |
| **Velero** | External S3 (bucket + credentials in vault); one default schedule + retention |
| **UIs** | Longhorn: own host `longhorn.blumefy.local`. Falco/Velero: no standalone UI → link from internal dashboard to Grafana dashboards |

---

## Architecture

### Longhorn

- **What:** Distributed block storage; default StorageClass so new PVCs use Longhorn unless specified otherwise.
- **Install:** Role `roles/longhorn`: add Helm repo `longhorn` at https://charts.longhorn.io; install in namespace `longhorn-system`. After install, patch StorageClass `longhorn` to set `storageclass.kubernetes.io/is-default-class: "true"` and remove that annotation from any other default (e.g. K3s `local-path`).
- **Order:** Before Traefik (or early enough that components needing storage can use it). Phase 4b (after MetalLB, before Traefik).
- **UI:** Longhorn exposes a web UI (service `longhorn-frontend`, port 80). Expose at `longhorn.blumefy.local` via IngressRoute (VPN-only, TLS). Add to `vpn_internal_hosts` and internal dashboard (card + nav).

### Falco

- **What:** Runtime security (syscall monitoring); DaemonSet so one pod per node.
- **Install:** Role `roles/falco`: add Helm repo `falcosecurity` at https://falco.org/charts; install in namespace `falco` (or `falco-system`). Use default driver (eBPF where supported). Enable metrics for Prometheus.
- **Order:** After Longhorn; e.g. Phase 5a. No dependency on Traefik.
- **UI:** No built-in UI. Enable Falco metrics; add a Grafana dashboard for Falco. Internal dashboard: add card/nav "Falco" linking to Grafana Falco dashboard (e.g. `grafana.blumefy.local/d/falco`).

### Velero

- **What:** Backup and restore; default backup storage location = external S3; one default schedule (e.g. daily) with retention.
- **Install:** Role `roles/velero`: add Helm repo `vmware-tanzu` at https://vmware-tanzu.github.io/helm-charts; create K8s Secret with S3 credentials from vault (`vault_velero_s3_access_key`, `vault_velero_s3_secret_key`); install Velero with `configuration.backupStorageLocation` and optional `volumeSnapshotLocation` for Longhorn. Create Velero Schedule (e.g. daily 02:00, retain 7).
- **Vars:** `velero_s3_bucket`, `velero_s3_region`, optional `velero_s3_url` for S3-compatible endpoints (R2, B2, etc.). Vault: `vault_velero_s3_access_key`, `vault_velero_s3_secret_key`.
- **Order:** After Longhorn (for volume snapshot location). Phase 5f.
- **UI:** No official UI. Add Grafana dashboard for backup/schedule status (or community JSON). Internal dashboard: card/nav "Velero" → Grafana Velero dashboard (e.g. `grafana.blumefy.local/d/velero`).

### Internal dashboard and VPN hosts

- **Longhorn:** IngressRoute in Traefik template (conditional on `longhorn_enabled`), service `longhorn-frontend` in namespace `longhorn-system`, port 80. TLS: `tls-blumefy-local` (Traefik namespace). Append `longhorn.blumefy.local` to `vpn_internal_hosts`.
- **Dashboard HTML:** In `roles/traefik/templates/internal-dashboard-index.html.j2`:
  - Add section (e.g. "Storage & Security") with Longhorn card (link to `https://longhorn.{{ vpn_internal_domain }}/`) and nav item; show when `longhorn_enabled`.
  - Add Falco card and nav item (link to `https://grafana.{{ vpn_internal_domain }}/d/falco` or equivalent); show when `falco_enabled` and `monitoring_enabled`.
  - Add Velero card and nav item (link to `https://grafana.{{ vpn_internal_domain }}/d/velero`); show when `velero_enabled` and `monitoring_enabled`.
- **Grafana:** Provision Falco and Velero dashboard JSONs via monitoring role (ConfigMaps + sidecar or dashboard provider) so the UIDs are stable (e.g. `falco`, `velero`).

---

## Role structure summary

| Role | Namespace | Key tasks |
|------|-----------|-----------|
| `longhorn` | longhorn-system | Helm install; set default StorageClass; unset other default |
| `falco` | falco | Helm install; DaemonSet; metrics enabled |
| `velero` | velero | Create S3 secret; Helm install; BackupStorageLocation; Schedule |

---

## Vars (group_vars/all/vars.yml)

- `longhorn_enabled: true`, `falco_enabled: true`, `velero_enabled: true`
- `longhorn_namespace: longhorn-system`, `falco_namespace: falco`, `velero_namespace: velero`
- Velero: `velero_s3_bucket`, `velero_s3_region`, `velero_s3_url` (optional), `velero_schedule_enabled: true`, `velero_schedule_cron: "0 2 * * *"`, `velero_schedule_retention: "7"`
- Vault: `vault_velero_s3_access_key`, `vault_velero_s3_secret_key`
- `vpn_internal_hosts`: append `longhorn.blumefy.local`

---

## Error handling

- Longhorn/Falco: Helm install fails → playbook fails; no vault required for basic install.
- Velero: Role asserts vault vars and `velero_s3_bucket` / `velero_s3_region` are set before install.
- If default StorageClass patch fails (e.g. no longhorn StorageClass yet), task can be made conditional on StorageClass existence.

---

## Out of scope

- Falco custom rules or Slack/webhook outputs (can add later).
- Velero restores (manual or separate playbook).
- Argo CD Applications for these components (optional later).
