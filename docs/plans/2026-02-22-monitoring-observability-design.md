# Full Monitoring Stack (Jaeger, Grafana, Loki, Prometheus) — Design

**Date:** 2026-02-22  
**Status:** Approved

---

## Goal

Add a full observability stack to the k3s cluster so you can see incoming requests, trace them through the system, and jump from traces to related logs. All deployed via Ansible (no ArgoCD for monitoring), reusing the existing internal domain (`*.blumefy.local`) and VPN-only access.

---

## Decisions

| Decision | Choice |
|----------|--------|
| **Where to run** | Same k3s cluster, new `monitoring` namespace |
| **How to deploy** | Ansible only (new role), no ArgoCD for monitoring |
| **App instrumentation** | Not assumed; design includes Traefik tracing + header propagation + apps logging trace ID |
| **Role structure** | Single role `monitoring` with optional components (feature flags) |
| **Access** | Reuse internal domain: `grafana.blumefy.local`, `jaeger.blumefy.local` (VPN-only, same as dashboard/argocd/infisical) |

---

## Architecture

- **Namespace:** `monitoring` (created by the role when any component is enabled).
- **Components (all optional via vars):**
  - **Prometheus** — metrics scraping (Traefik, nodes, pods, optional app metrics).
  - **Grafana** — single UI for dashboards; data sources: Prometheus, Loki, Jaeger.
  - **Loki** — log aggregation; apps (and optionally Traefik) send logs so you can query by `trace_id`.
  - **Jaeger** — trace storage and UI; receives spans from Traefik (and later from apps if you add OTel).
- **Traefik:** Configured to send tracing to Jaeger and to propagate W3C trace headers (`traceparent` / `X-Trace-ID`) to backends. When apps log that ID, Grafana can link Jaeger trace → Loki logs.
- **Access:** Grafana and Jaeger exposed via Traefik IngressRoutes on the internal domain, with `vpn-allowlist` middleware (same pattern as ArgoCD, Infisical, RabbitMQ). Internal dashboard updated with links to Grafana and Jaeger.

---

## Data Flow (Trace → Logs)

1. Request hits Traefik → Traefik creates root span, sends to Jaeger, adds/propagates `traceparent` (and optionally `X-Trace-ID`) to backend.
2. Backend services read trace ID from request headers and add it to every log line (e.g. `trace_id=abc123` or structured field).
3. Logs are collected (e.g. Promtail or app stdout → Loki).
4. In Grafana: open a trace in Jaeger, use “Trace to logs” (or Loki query by `trace_id`) to see all logs for that request.

---

## Role Structure (Approach 3)

- **Role:** `roles/monitoring/`
- **Vars (defaults):** `monitoring_prometheus_enabled: true`, `monitoring_grafana_enabled: true`, `monitoring_loki_enabled: true`, `monitoring_jaeger_enabled: true`, `monitoring_traefik_tracing_enabled: true`. Set to `false` to skip a component.
- **Tasks:** `tasks/main.yml` includes task files per component (namespace, Prometheus, Grafana, Loki, Jaeger, Traefik tracing). Each block is guarded by the corresponding `*_enabled` var.
- **Integration with existing vars:** Reuse `monitoring_enabled`, `monitoring_namespace`, `vpn_internal_domain`, `grafana_admin_password` from `inventory/group_vars/all/vars.yml`. When `monitoring_enabled` is true, Traefik role already adds `monitoring` namespace to middlewares; we add Grafana/Jaeger VPN IngressRoutes and internal dashboard links.

---

## Internal Domain (Reuse)

- **Grafana:** `https://grafana.{{ vpn_internal_domain }}` (e.g. `https://grafana.blumefy.local`).
- **Jaeger:** `https://jaeger.{{ vpn_internal_domain }}` (e.g. `https://jaeger.blumefy.local`).
- **Hosts list:** Add `grafana.blumefy.local` and `jaeger.blumefy.local` to `vpn_internal_hosts` when monitoring is enabled (or in the monitoring role’s vars/templates so Traefik and dashboard get them).
- **TLS:** Same self-signed cert as other internal apps (`tls-blumefy-local`). IngressRoutes live in `monitoring` namespace for Grafana/Jaeger (service in same namespace as route, or cross-namespace as with ArgoCD).

---

## App-Side (Trace ID in Logs)

- **Not in scope of this role:** Application code changes remain in app repos.
- **Deliverable:** Short doc (or README section) describing how to read `traceparent` or `X-Trace-ID` from incoming requests and add it to log output (e.g. one middleware or log formatter). Optionally provide a minimal example (e.g. Node/Express or generic snippet). This enables “trace to logs” in Grafana once Loki has those logs.

---

## Error Handling & Testing

- **Helm:** Use `community.kubernetes.helm_release` with `wait: true` and reasonable timeouts; failed releases leave cluster in a known state so you can fix vars and re-run.
- **Traefik tracing:** If Jaeger is not ready, Traefik may log tracing errors; non-blocking. Ensure Jaeger is deployed before or with Traefik tracing enabled.
- **Verification:** After playbook run: connect via VPN, open `https://grafana.blumefy.local` and `https://jaeger.blumefy.local`, check data sources in Grafana, trigger a request and confirm one span in Jaeger and (after app changes) logs in Loki with same trace ID.

---

## Documentation Updates

- **VPN_INTERNAL_DASHBOARD.md:** Add Grafana and Jaeger to the table of internal URLs and to any “hosts” list.
- **wireguard-configs/add-vpn-hosts.sh:** Ensure `grafana` and `jaeger` are in the generated hosts list when monitoring is enabled (if that script is generated from vars; otherwise document manual step).
- **README or new docs/MONITORING.md:** How to enable the stack (`monitoring_enabled: true`, vault for `grafana_admin_password`), how to add trace ID to app logs, and how to use “Trace to logs” in Grafana.

---

## Out of Scope (For Later)

- Full OpenTelemetry instrumentation per service (optional future step for per-service spans).
- Prometheus/Loki retention and storage sizing (defaults first; tune later).
- Public or non-VPN access to Grafana/Jaeger (internal only by design).
