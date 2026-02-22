# Full Monitoring Stack (Jaeger, Grafana, Loki, Prometheus) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a single Ansible role (with optional components) that deploys Prometheus, Grafana, Loki, and Jaeger to the `monitoring` namespace, configures Traefik tracing to Jaeger and trace-header propagation, and exposes Grafana/Jaeger on the internal domain (`*.blumefy.local`) VPN-only. Users can see requests and trace them to logs.

**Architecture:** One role `roles/monitoring/` with feature flags per component. Existing `monitoring` role is extended: refactor to optional Prometheus/Grafana/Loki/Jaeger/Traefik-tracing; switch Grafana (and add Jaeger) to internal domain and VPN IngressRoutes; add Loki and Jaeger Helm releases; configure Traefik Helm values for tracing. Traefik role gains Grafana/Jaeger VPN IngressRoutes and TLS secret in `monitoring` namespace when `monitoring_enabled`; internal dashboard and `vpn_internal_hosts` get Grafana/Jaeger entries.

**Tech Stack:** Ansible, Helm (prometheus-community/kube-prometheus-stack, grafana/loki, jaegertracing/jaeger), Traefik v3 (tracing), k3s.

---

## Task 1: Add monitoring feature flags and extend vars

**Files:**
- Modify: `inventory/group_vars/all/vars.yml` (append to monitoring section; add to vpn_internal_hosts)
- Create: `roles/monitoring/defaults/main.yml`

**Step 1:** Add optional component flags and Grafana/Jaeger internal hosts.

In `inventory/group_vars/all/vars.yml`, in the `# ─── Monitoring` section (around 110–115), after `grafana_admin_password`, add:

```yaml
# Component toggles (all true = full stack)
monitoring_prometheus_enabled: true
monitoring_grafana_enabled: true
monitoring_loki_enabled: true
monitoring_jaeger_enabled: true
monitoring_traefik_tracing_enabled: true
```

In the same file, in `vpn_internal_hosts` (around 168–177), add two entries so the WireGuard-generated `add-vpn-hosts.sh` includes them:

```yaml
  - grafana.blumefy.local
  - jaeger.blumefy.local
```

(Use `vpn_internal_domain` if you prefer: `grafana.{{ vpn_internal_domain }}` and `jaeger.{{ vpn_internal_domain }}` — but the list currently uses literal `blumefy.local`, so keep consistency.)

**Step 2:** Create `roles/monitoring/defaults/main.yml` with the same flags (so the role is self-contained) and chart versions:

```yaml
---
monitoring_prometheus_enabled: true
monitoring_grafana_enabled: true
monitoring_loki_enabled: true
monitoring_jaeger_enabled: true
monitoring_traefik_tracing_enabled: true

# Chart versions (override in group_vars if needed)
monitoring_kube_prometheus_stack_version: null   # use repo default
monitoring_loki_chart_version: null
monitoring_jaeger_chart_version: null
```

**Step 3:** Commit.

```bash
git add inventory/group_vars/all/vars.yml roles/monitoring/defaults/main.yml
git commit -m "feat(monitoring): add component flags and vpn hosts for grafana/jaeger"
```

---

## Task 2: Create TLS secret in monitoring namespace (Traefik role)

**Files:**
- Modify: `roles/traefik/tasks/main.yml` (block that creates TLS for VPN internal)

**Step 1:** In the block that creates `tls-blumefy-local` for infisical (around 221–230), add a similar task for the monitoring namespace, conditioned on `monitoring_enabled` and `vpn_internal_ui_enabled`.

After the "Create TLS secret for VPN internal (infisical namespace)" task, add:

```yaml
    - name: Create TLS secret for VPN internal (monitoring namespace)
      when: (monitoring_enabled | default(false)) and (vpn_internal_ui_enabled | default(false))
      shell: >
        kubectl create secret tls tls-blumefy-local
        --cert=/tmp/blumefy-local.crt --key=/tmp/blumefy-local.key
        -n {{ monitoring_namespace }} --dry-run=client -o yaml
        | kubectl apply -f -
      environment:
        KUBECONFIG: /etc/rancher/k3s/k3s.yaml
```

**Step 2:** Run playbook with traefik tag to verify (no error):

```bash
ansible-playbook playbooks/site.yml --tags traefik -l node1
```

**Step 3:** Commit.

```bash
git add roles/traefik/tasks/main.yml
git commit -m "feat(traefik): create VPN TLS secret in monitoring namespace when monitoring enabled"
```

---

## Task 3: Add Grafana and Jaeger VPN IngressRoutes (Traefik role)

**Files:**
- Modify: `roles/traefik/templates/ingressroute-vpn-internal.yml.j2` (append two new IngressRoute docs)
- Modify: `roles/traefik/tasks/main.yml` (ensure VPN internal IngressRoutes apply when monitoring_enabled)

**Step 1:** In `roles/traefik/templates/ingressroute-vpn-internal.yml.j2`, after the infisical block (after `{% endif %}` around line 164), add:

```yaml
{% if monitoring_enabled | default(false) and vpn_internal_ui_enabled | default(false) %}
---
apiVersion: {{ traefik_crd_api_group | default('traefik.io') }}/v1alpha1
kind: IngressRoute
metadata:
  name: grafana-vpn
  namespace: {{ monitoring_namespace }}
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`grafana.{{ vpn_internal_domain | default('blumefy.local') }}`)
      kind: Rule
      middlewares:
        - name: vpn-allowlist
          namespace: {{ traefik_namespace }}
      services:
        - name: prometheus-grafana
          port: 80
          namespace: {{ monitoring_namespace }}
  tls:
    secretName: tls-blumefy-local
---
apiVersion: {{ traefik_crd_api_group | default('traefik.io') }}/v1alpha1
kind: IngressRoute
metadata:
  name: jaeger-vpn
  namespace: {{ monitoring_namespace }}
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`jaeger.{{ vpn_internal_domain | default('blumefy.local') }}`)
      kind: Rule
      middlewares:
        - name: vpn-allowlist
          namespace: {{ traefik_namespace }}
      services:
        - name: jaeger-jaeger-query
          port: 16686
          namespace: {{ monitoring_namespace }}
  tls:
    secretName: tls-blumefy-local
{% endif %}
```

**Note:** Service name `jaeger-jaeger-query` is the default for the `jaegertracing/jaeger` Helm chart with release name `jaeger`. If your chart uses a different name, run `kubectl get svc -n monitoring` after installing Jaeger and update this template.

**Step 2:** Ensure the play that applies `ingressroute-vpn-internal.yml.j2` runs when `monitoring_enabled` is true (it likely already runs for `vpn_internal_ui_enabled`; confirm the file is applied in the same "Deploy VPN internal IngressRoutes" block). No change needed if the block only checks `vpn_internal_ui_enabled`.

**Step 3:** Commit (after replacing placeholder if done in same session as Jaeger).

```bash
git add roles/traefik/templates/ingressroute-vpn-internal.yml.j2
git commit -m "feat(traefik): add VPN IngressRoutes for Grafana and Jaeger on internal domain"
```

---

## Task 4: Add Grafana and Jaeger to internal dashboard

**Files:**
- Modify: `roles/traefik/templates/internal-dashboard-index.html.j2` (cards and nav)

**Step 1:** Add two cards for Grafana and Jaeger in the same style as Traefik/ArgoCD/Infisical. In the grid section where cards are (e.g. after Redis prod card), add:

- Card: Grafana — `https://grafana.{{ vpn_internal_domain }}/` (class `grafana`, label "Grafana")
- Card: Jaeger — `https://jaeger.{{ vpn_internal_domain }}/` (class `jaeger`, label "Jaeger")

**Step 2:** Add matching nav items in the sidebar/nav (data-app, data-url, data-label) so the iframe/list stays consistent.

**Step 3:** Add CSS for `.card.grafana .icon` and `.card.jaeger .icon` if you use per-app icon styling (reuse existing pattern).

**Step 4:** Commit.

```bash
git add roles/traefik/templates/internal-dashboard-index.html.j2
git commit -m "feat(traefik): add Grafana and Jaeger to internal dashboard"
```

---

## Task 5: Refactor monitoring role — namespace and Helm repos

**Files:**
- Modify: `roles/monitoring/tasks/main.yml`

**Step 1:** Keep "Add Prometheus community Helm repo" and "Update Helm repos" at the top (or move to a pre_tasks/include). Add "Add Grafana Helm repo" (for Loki) and "Add Jaeger Helm repo" so they run once. Use `when: monitoring_enabled | default(false)` on a block that wraps repo adds and namespace creation.

**Step 2:** Create monitoring namespace only when `monitoring_enabled` (already implied by play). Ensure namespace task runs when at least one of prometheus/grafana/loki/jaeger is enabled.

**Step 3:** Structure so next tasks can add separate task files or blocks: e.g. `include_tasks: prometheus.yml` when `monitoring_prometheus_enabled`, etc. For this task, only refactor so that:
- Repos: prometheus-community, grafana (for Loki), jaegertracing
- Namespace: create `monitoring_namespace` when `monitoring_enabled`

**Step 4:** Commit.

```bash
git add roles/monitoring/tasks/main.yml
git commit -m "refactor(monitoring): add grafana and jaeger helm repos; namespace when enabled"
```

---

## Task 6: Install Loki and Jaeger via Helm in monitoring role

**Files:**
- Create: `roles/monitoring/tasks/loki.yml`
- Create: `roles/monitoring/tasks/jaeger.yml`
- Modify: `roles/monitoring/tasks/main.yml` (include these when enabled)

**Step 1:** Add Grafana Helm repo (for Loki) in main.yml if not already:

```yaml
- name: Add Grafana Helm repo
  command: helm repo add grafana https://grafana.github.io/helm-charts
  environment:
    KUBECONFIG: /etc/rancher/k3s/k3s.yaml
  changed_when: false
```

Add Jaeger repo:

```yaml
- name: Add Jaegertracing Helm repo
  command: helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
  environment:
    KUBECONFIG: /etc/rancher/k3s/k3s.yaml
  changed_when: false
```

**Step 2:** Create `roles/monitoring/tasks/loki.yml`. Use `grafana/loki` or `grafana/loki-stack` (loki-stack includes Promtail; for trace-to-logs, Loki + Promtail is typical). Example for `grafana/loki` (single Loki):

```yaml
---
- name: Deploy Loki
  when: monitoring_loki_enabled | default(true)
  block:
    - name: Install Loki Helm release
      community.kubernetes.helm_release:
        name: loki
        chart_ref: grafana/loki
        chart_version: "{{ monitoring_loki_chart_version | default(omit) }}"
        release_namespace: "{{ monitoring_namespace }}"
        wait: true
        timeout: 5m
      environment:
        KUBECONFIG: /etc/rancher/k3s/k3s.yaml
```

(If using `helm` command instead of `community.kubernetes.helm_release`, use the same pattern with `command` and `environment` as in existing monitoring tasks.)

**Step 3:** Create `roles/monitoring/tasks/jaeger.yml`. Use `jaegertracing/jaeger` (all-in-one or production template). Example all-in-one:

```yaml
---
- name: Deploy Jaeger
  when: monitoring_jaeger_enabled | default(true)
  block:
    - name: Install Jaeger Helm release
      community.kubernetes.helm_release:
        name: jaeger
        chart_ref: jaegertracing/jaeger
        chart_version: "{{ monitoring_jaeger_chart_version | default(omit) }}"
        release_namespace: "{{ monitoring_namespace }}"
        wait: true
        timeout: 5m
      environment:
        KUBECONFIG: /etc/rancher/k3s/k3s.yaml
```

Look up the default service name for the Jaeger query UI (e.g. `jaeger-jaeger-query` or `jaeger-query`) and update Task 3’s IngressRoute template with that name.

**Step 4:** In `roles/monitoring/tasks/main.yml`, after namespace creation, add:

```yaml
- include_tasks: loki.yml
  when: monitoring_loki_enabled | default(true)
- include_tasks: jaeger.yml
  when: monitoring_jaeger_enabled | default(true)
```

**Step 5:** Fix Traefik template: set Jaeger service name in `ingressroute-vpn-internal.yml.j2` to the actual service (e.g. `jaeger-jaeger-query` or whatever `kubectl get svc -n monitoring` shows after a dry run).

**Step 6:** Run playbook with monitoring tag (will need vault and possibly to disable components for a quick test):

```bash
ansible-playbook playbooks/site.yml --tags monitoring -l node1
```

**Step 7:** Commit.

```bash
git add roles/monitoring/tasks/main.yml roles/monitoring/tasks/loki.yml roles/monitoring/tasks/jaeger.yml roles/traefik/templates/ingressroute-vpn-internal.yml.j2
git commit -m "feat(monitoring): install Loki and Jaeger via Helm; fix Jaeger VPN route service name"
```

---

## Task 7: Switch Grafana to internal domain and remove public IngressRoute

**Files:**
- Modify: `roles/monitoring/templates/grafana-ingressroute.yml.j2`
- Modify: `roles/monitoring/tasks/main.yml` (stop applying Grafana IngressRoute in monitoring role if Traefik now owns it)

**Step 1:** The Traefik role now owns the Grafana VPN IngressRoute (Task 3). So either:
- (A) Remove the monitoring role’s Grafana IngressRoute task and template (so only Traefik’s VPN route exists), or
- (B) Keep the monitoring template but change it to the internal domain and VPN middleware, and apply it from the monitoring role (TLS secret is in monitoring namespace).

Design: reuse internal domain and Traefik role for consistency. So delete or disable the existing `Apply Grafana IngressRoute` and `Apply Grafana route to cluster` tasks in `roles/monitoring/tasks/main.yml`, and remove or archive `roles/monitoring/templates/grafana-ingressroute.yml.j2` so Grafana is only exposed via Traefik’s VPN IngressRoute.

**Step 2:** In `roles/monitoring/tasks/main.yml`, remove the two tasks that template and apply `grafana-ingressroute.yml.j2`.

**Step 3:** Update the "Show Grafana access info" debug to use internal domain:

```yaml
- name: Show Grafana access info
  when: monitoring_grafana_enabled | default(true)
  debug:
    msg: "Grafana (VPN): https://grafana.{{ vpn_internal_domain | default('blumefy.local') }} — user: admin / pass: (vault)"
```

**Step 4:** Commit.

```bash
git add roles/monitoring/tasks/main.yml
git rm roles/monitoring/templates/grafana-ingressroute.yml.j2
git commit -m "feat(monitoring): expose Grafana via Traefik VPN only; remove public IngressRoute"
```

---

## Task 8: Configure Traefik tracing to Jaeger

**Files:**
- Modify: `roles/traefik/templates/traefik-values.yml.j2` (add tracing section)
- Optional: `roles/traefik/tasks/main.yml` (ensure tracing is applied when monitoring_enabled and traefik_tracing)

**Step 1:** In `roles/traefik/templates/traefik-values.yml.j2`, add a `tracing` section so Traefik sends spans to Jaeger. Traefik v3 supports OpenTelemetry or Jaeger. Example for Jaeger (check Traefik v3 docs for exact key names):

```yaml
# Tracing (when monitoring stack with Jaeger is enabled)
{% if monitoring_enabled | default(false) and monitoring_traefik_tracing_enabled | default(true) %}
tracing:
  jaeger:
    samplingType: const
    samplingParam: 1.0
    localAgentHostPort: "jaeger-jaeger-agent.monitoring.svc:6831"
{% endif %}
```

Use the actual Jaeger agent service name and port from the Jaeger Helm chart (often `6831` for compact thrift). If the chart deploys a collector and no agent, use the collector endpoint instead (e.g. HTTP `http://jaeger-collector.monitoring.svc:14268/api/traces`). Adjust namespace to `monitoring_namespace` if you use a variable.

**Step 2:** Enable propagation of trace headers to backends (so apps can log trace_id). In Traefik, this is often enabled with the same tracing config or via middleware. Document in MONITORING.md that backends receive `traceparent` when tracing is enabled.

**Step 3:** Run Traefik play to apply:

```bash
ansible-playbook playbooks/site.yml --tags traefik -l node1
```

**Step 4:** Commit.

```bash
git add roles/traefik/templates/traefik-values.yml.j2
git commit -m "feat(traefik): enable tracing to Jaeger when monitoring and traefik_tracing enabled"
```

---

## Task 9: Configure Grafana data sources (Prometheus, Loki, Jaeger)

**Files:**
- Modify: `roles/monitoring/templates/monitoring-values.yml.j2` (kube-prometheus-stack Grafana datasources)
- Or create: `roles/monitoring/templates/grafana-datasources.yml.j2` and apply as ConfigMap/Secret if the chart supports extra datasources

**Step 1:** In kube-prometheus-stack, Grafana datasources can be added via `grafana.additionalDataSources`. Add Prometheus (usually already default), Loki (URL: `http://loki.monitoring.svc:3100` or the actual Loki service name), and Jaeger (URL: `http://jaeger-jaeger-query.monitoring.svc:16686` or the actual Jaeger query service). Use the real service names from your Loki/Jaeger releases.

**Step 2:** In `roles/monitoring/templates/monitoring-values.yml.j2`, add:

```yaml
grafana:
  additionalDataSources:
    - name: Loki
      type: loki
      url: http://loki-gateway.monitoring.svc:80
      # or url: http://loki.monitoring.svc:3100 depending on chart
    - name: Jaeger
      type: jaeger
      url: http://jaeger-jaeger-query.monitoring.svc:16686
      # adjust service name to match Helm release
```

**Step 3:** Commit.

```bash
git add roles/monitoring/templates/monitoring-values.yml.j2
git commit -m "feat(monitoring): add Loki and Jaeger as Grafana data sources"
```

---

## Task 10: Guard monitoring role tasks by component flags

**Files:**
- Modify: `roles/monitoring/tasks/main.yml`

**Step 1:** Wrap existing Prometheus/Grafana install (Helm kube-prometheus-stack) in `when: monitoring_prometheus_enabled | default(true)`. Grafana is part of that stack; if you split them later, guard Grafana separately. For now, kube-prometheus-stack install only when `monitoring_prometheus_enabled` (and the stack includes Grafana when `monitoring_grafana_enabled` — or always install stack with grafana enabled when prometheus_enabled). Simplest: install kube-prometheus-stack when `monitoring_prometheus_enabled`; inside the stack, enable/disable Grafana via `grafana.enabled: "{{ monitoring_grafana_enabled }}"` in monitoring-values.yml.j2.

**Step 2:** In `monitoring-values.yml.j2`, set `grafana.enabled: {{ monitoring_grafana_enabled }}` (and optionally disable alertmanager when not needed). Ensure alert rules and any Grafana-specific config are conditional.

**Step 3:** Ensure Loki and Jaeger includes run only when their flags are true (already in Task 6).

**Step 4:** Commit.

```bash
git add roles/monitoring/tasks/main.yml roles/monitoring/templates/monitoring-values.yml.j2
git commit -m "feat(monitoring): guard Prometheus/Grafana by component flags"
```

---

## Task 11: Document monitoring and trace-to-logs

**Files:**
- Create: `docs/MONITORING.md`
- Modify: `docs/VPN_INTERNAL_DASHBOARD.md` (add Grafana and Jaeger to table and any hosts list)

**Step 1:** Create `docs/MONITORING.md` with:
- How to enable: `monitoring_enabled: true`, set `grafana_admin_password` in vault.
- URLs: Grafana at `https://grafana.{{ vpn_internal_domain }}`, Jaeger at `https://jaeger.{{ vpn_internal_domain }}` (VPN only).
- How to add trace ID to app logs: read `traceparent` or `X-Trace-ID` from request headers and add to every log line; link to Grafana “Trace to logs” and Loki query by `trace_id`.
- Optional: minimal code snippet (e.g. Node.js middleware or log formatter).

**Step 2:** In `docs/VPN_INTERNAL_DASHBOARD.md`, add to the table of internal URLs:

| https://grafana.blumefy.local | Grafana | Dashboards, Prometheus/Loki/Jaeger |
| https://jaeger.blumefy.local | Jaeger | Distributed tracing UI |

And note that `add-vpn-hosts.sh` (generated when WireGuard/traefik runs) includes `grafana` and `jaeger` when those hosts are in `vpn_internal_hosts`.

**Step 3:** Commit.

```bash
git add docs/MONITORING.md docs/VPN_INTERNAL_DASHBOARD.md
git commit -m "docs: add MONITORING.md and update VPN dashboard doc for Grafana/Jaeger"
```

---

## Task 12: Optional — Trace-to-logs app snippet

**Files:**
- Modify: `docs/MONITORING.md` (add subsection with example)

**Step 1:** Add a short “Adding trace_id to your logs” section with a generic example: read `traceparent` header (or `X-Trace-ID` if Traefik sets it), parse trace ID, add to structured log or log line. Example for Node/Express:

```javascript
app.use((req, res, next) => {
  const traceparent = req.get('traceparent');
  const traceId = traceparent ? traceparent.split('-')[1] : undefined;
  req.traceId = traceId;
  if (traceId) req.log = req.log?.child({ trace_id: traceId }) || logger.child({ trace_id: traceId });
  next();
});
```

**Step 2:** Commit.

```bash
git add docs/MONITORING.md
git commit -m "docs(monitoring): add example for logging trace_id in apps"
```

---

## Execution summary

- **Tasks 1–4:** Vars, TLS, Traefik VPN routes and dashboard (internal domain).
- **Tasks 5–7:** Monitoring role refactor, Loki/Jaeger Helm, Grafana only on VPN.
- **Tasks 8–10:** Traefik tracing, Grafana datasources, component flags.
- **Tasks 11–12:** Documentation.

After implementation, run:

```bash
ansible-playbook playbooks/site.yml --tags wireguard,traefik,monitoring -l node1
```

Then connect via VPN, run `add-vpn-hosts.sh`, and open https://grafana.blumefy.local and https://jaeger.blumefy.local.

---

**Plan complete and saved to `docs/plans/2026-02-22-monitoring-observability-implementation.md`.**

Two execution options:

1. **Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — Open a new session with executing-plans and run the plan task-by-task with checkpoints.

Which approach do you want?
