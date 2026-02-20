# Viewing Traefik request logs

## Where request logs appear

- **Traefik** — Yes. Every HTTP/HTTPS request that Traefik handles is logged (access log). This is where you see client IP, host, path, status, duration, etc.
- **MetalLB** — No. MetalLB only assigns an external IP to the Traefik Service (L2/L3). It does not see HTTP requests or produce request logs.

So **all request visibility is in Traefik**.

## How Traefik logging is configured

- **Access log** (each request): enabled, written to **`/tmp/traefik-access.log`** inside the Traefik pod.
- **Traefik’s own logs** (startup, errors, WARN): `--log.level=WARN`, sent to **stdout** (so they show in `kubectl logs`).

## View request logs (access log)

Access log is only in the file inside the pod. Use one of these.

**Tail the access log (follow):**

```bash
kubectl exec -n traefik -it deploy/traefik -- tail -f /tmp/traefik-access.log
```

**Last 100 lines:**

```bash
kubectl exec -n traefik deploy/traefik -- tail -100 /tmp/traefik-access.log
```

**Full file (can be large):**

```bash
kubectl exec -n traefik deploy/traefik -- cat /tmp/traefik-access.log
```

Use your Traefik namespace if you changed it (e.g. from `vars.yml`: `traefik_namespace`).

## View Traefik’s own logs (stdout)

Startup, errors, and WARN-level messages:

```bash
kubectl logs -n traefik -l app.kubernetes.io/name=traefik -f
```

`-f` follows the log stream. These logs do **not** include per-request lines; use the access log file above for that.

## Optional: send access logs to stdout

If you prefer to see request logs with `kubectl logs` (e.g. for a log aggregator), you can switch the Traefik role to write access logs to stdout instead of (or in addition to) the file. That would require changing the Traefik Helm values (e.g. remove `--accesslog.filepath` or set the chart’s access log to use stdout). Right now the role uses a file so logs persist in the container and don’t mix with Traefik’s WARN logs.
