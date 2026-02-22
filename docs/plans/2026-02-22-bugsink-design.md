# Bugsink (VPN-only) — Design

**Date:** 2026-02-22  
**Status:** Approved

---

## Goal

Add Bugsink (self-hosted, Sentry-SDK–compatible error tracking) to the existing K3s cluster, exposed VPN-only at `https://bugsink.blumefy.local`, using the same patterns as Infisical, Argo CD, and Redis Commander.

---

## Decisions

| Decision | Choice |
|----------|--------|
| **Where to run** | Same K3s cluster, dedicated namespace `bugsink` |
| **How to deploy** | New Ansible role `roles/bugsink` using community Helm chart `bugsink/bugsink` |
| **Access** | VPN-only via Traefik IngressRoute; host `bugsink.blumefy.local` added to `vpn_internal_hosts` |
| **Secrets** | `SECRET_KEY` and optional admin auth in Ansible vault; role creates K8s secret or passes to Helm |
| **Chart** | Community repo https://github.com/bugsink/helm-charts; pin version in vars for reproducibility |

---

## Architecture

- **Namespace:** `bugsink` (created by the role when `bugsink_enabled: true`).
- **Helm:** Repo `bugsink` at `https://bugsink.github.io/helm-charts`; release name `bugsink`, chart `bugsink/bugsink`.
- **Chart defaults:** Built-in PostgreSQL (enabled), service ClusterIP port 8000; ingress disabled (we use Traefik).
- **Config:** `baseUrl: https://bugsink.{{ vpn_internal_domain }}`; `secretKey` from vault (existingSecret or value); optional `admin.auth` or existingSecret for initial superuser.
- **Traefik:** One IngressRoute for `bugsink.{{ vpn_internal_domain }}` → service in namespace `bugsink` port 8000, with `vpn-allowlist` middleware and `tls-blumefy-local`.
- **Vault:** New vars (e.g. `vault_bugsink_secret_key`, optional `vault_bugsink_admin_auth`) in `inventory/group_vars/all/vault.yml`.

---

## Role Structure

- **Role:** `roles/bugsink/`
  - `tasks/main.yml` — add Helm repo, create namespace, create K8s secret for secretKey (and optional admin), template Helm values, `helm upgrade --install`, wait for Bugsink pod, optional debug with access URL.
  - `templates/bugsink-values.yml.j2` — values for Helm: baseUrl, secretKey.existingSecret (or value), admin, ingress.enabled: false, postgresql persistence size if needed.
  - `defaults/main.yml` — bugsink_enabled, bugsink_namespace, bugsink_helm_chart_version, bugsink_base_url (derived), bugsink_postgresql_size, etc.
- **Traefik:** In `roles/traefik/templates/ingressroute-vpn-internal.yml.j2`, add conditional block `{% if bugsink_enabled | default(false) %}` with IngressRoute for Bugsink (name e.g. `bugsink-vpn`), namespace `traefik`, route to service in namespace `bugsink` port 8000. Service name from Helm is typically the release name (`bugsink`); confirm after first install and adjust if chart uses a different name.
- **Vars:** In `inventory/group_vars/all/vars.yml` add `bugsink_enabled: true`, `bugsink_namespace: bugsink`, and append `bugsink.blumefy.local` to `vpn_internal_hosts`.
- **Playbook:** New phase (e.g. Phase 5d) in `playbooks/site.yml` to run role `bugsink` on node1 when `bugsink_enabled` is true, with tag `bugsink`.
- **Execution order:** Bugsink after Traefik (so IngressRoute can be applied). No dependency on Infisical or Argo CD.

---

## Error Handling

- If vault vars for Bugsink are missing, role asserts with clear message (edit vault.yml, generate secret key).
- If Helm install fails, playbook fails; operator re-runs with fixed vars or chart version.

---

## Out of Scope

- Public exposure; SMTP; multiple instances; migration from Sentry (app-side only).
- Argo CD Application for Bugsink (can be added later if desired).
