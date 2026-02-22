# Monitoring Stack (Prometheus, Grafana, Loki, Jaeger)

This document describes the in-cluster monitoring stack: how to enable it, access the UIs, and link traces to logs.

---

## Enabling the stack

1. Set in `inventory/group_vars/all/vars.yml`:
   - `monitoring_enabled: true`
   - Ensure `grafana_admin_password` is set in your vault (e.g. `vault_grafana_password`).

2. Run the playbook with the monitoring and Traefik tags (Traefik provides VPN routes and tracing):
   ```bash
   ansible-playbook playbooks/site.yml --tags traefik,monitoring -l node1
   ```

3. Connect via WireGuard and run `add-vpn-hosts.sh` from `wireguard-configs/` so `grafana.blumefy.local` and `jaeger.blumefy.local` resolve.

---

## Access (VPN only)

| URL | Description |
|-----|-------------|
| **https://prometheus.blumefy.local** | Prometheus — metrics and query UI. |
| **https://alertmanager.blumefy.local** | Alertmanager — alert routing and silencing. |
| **https://grafana.blumefy.local** | Grafana — dashboards, Prometheus, Loki, and Jaeger data sources. Login: `admin` / password from vault. |
| **https://jaeger.blumefy.local** | Jaeger — trace search and timeline. |

Both use the same self-signed TLS and VPN allowlist as the rest of the internal dashboard (see [VPN_INTERNAL_DASHBOARD.md](VPN_INTERNAL_DASHBOARD.md)).

**Provisioned dashboards:** After the monitoring role runs, Grafana automatically loads:

- **Applications & Infrastructure** — Cluster CPU/memory, pods by namespace, deployments, node metrics.
- **Traefik** — Request rate by entrypoint and service, status codes, request duration (requires Traefik metrics scraped by Prometheus).
- **Argo CD** — App sync/health, sync rate, reconciliation duration (requires Argo CD metrics scraped by Prometheus).

Open them from **Dashboards** in the left menu. If Traefik or Argo CD panels show “No data”, ensure Prometheus is scraping their metrics endpoints (Traefik: metrics service in `traefik` namespace; Argo CD: `argocd-metrics:8082` in `argocd` namespace).

---

## Trace-to-logs: from a request to its logs

Traefik sends a root span for each request to Jaeger and propagates trace headers (`traceparent`, or `X-Trace-ID` where applicable) to your backends. To link a trace to logs in Grafana:

1. **In your apps:** Read the trace ID from the request (e.g. `traceparent` or `X-Trace-ID` header) and add it to every log line (e.g. `trace_id=abc123` or a structured field).
2. **In Grafana:** Open a trace in Jaeger (Explore → Jaeger), then use “Trace to logs” (or in Loki, query by `trace_id`) to see all logs for that request.

See the section **Adding trace_id to your logs** below for a minimal app-side change.

---

## Optional: disable components

In `vars.yml` you can set (defaults are `true`):

- `monitoring_prometheus_enabled` — Prometheus + Alertmanager + Grafana (from kube-prometheus-stack)
- `monitoring_grafana_enabled` — Grafana (within the stack)
- `monitoring_loki_enabled` — Loki
- `monitoring_jaeger_enabled` — Jaeger
- `monitoring_traefik_tracing_enabled` — Traefik sending traces to Jaeger

Set any to `false` to skip installing or enabling that component.

---

## Adding trace_id to your logs

To correlate logs with traces, each service should log the trace ID on every request. Read the trace ID from the incoming HTTP request and add it to your logger (or log line).

**Example (Node.js / Express):** read the W3C `traceparent` header and attach the trace ID to the request logger:

```javascript
// Middleware: parse traceparent (e.g. "00-<trace_id>-<span_id>-01") and add to request
app.use((req, res, next) => {
  const traceparent = req.get('traceparent');
  const traceId = traceparent ? traceparent.split('-')[1] : undefined;
  req.traceId = traceId;
  if (traceId && req.log) {
    req.log = req.log.child({ trace_id: traceId });
  }
  next();
});

// When logging: ensure trace_id is included (e.g. via req.log or your logger's context)
app.get('/api/example', (req, res) => {
  req.log?.info({ path: req.path }, 'Request received');
  // ...
});
```

If your stack uses a different header (e.g. `X-Trace-ID`), read that instead. Once logs include `trace_id`, you can use Grafana’s “Trace to logs” from Jaeger or query Loki by `trace_id`.
