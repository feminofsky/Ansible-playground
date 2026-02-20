# VPN Internal Dashboard & Access Guide

This document explains how to connect to WireGuard VPN and access the internal dashboard and all VPN-only applications at `*.blumefy.local`.

---

## Quick Start: Connect & Access Dashboard

### 1. Get Your WireGuard Config

After running the Ansible playbook, your WireGuard config is in:

```
wireguard-configs/wg-deploy.conf    # For "deploy" user (your admin access)
wireguard-configs/wg-<name>.conf   # For each team member (e.g. alice)
```

### 2. Install WireGuard (if needed)

- **macOS**: `brew install wireguard-tools` or install [WireGuard for Mac](https://apps.apple.com/app/wireguard/id1451685025)
- **Linux**: `apt install wireguard wireguard-tools` (or equivalent)
- **Windows**: [WireGuard for Windows](https://www.wireguard.com/install/)
- **iOS/Android**: Install WireGuard from the App Store / Play Store

### 3. Import and Connect

**Using WireGuard GUI (Mac/Windows/iOS/Android):**
1. Open WireGuard
2. Click "Import tunnel(s) from file" or "Add empty tunnel"
3. Select `wg-deploy.conf` (or paste its contents)
4. Click "Activate" / "Connect"

**Using CLI (Linux/Mac):**
```bash
wg-quick up wg0   # If your config is /etc/wireguard/wg0.conf
# Or copy wg-deploy.conf to that location first
```

### 4. Add hosts (required when vpn_use_dnsmasq: false)

With the default config, `*.blumefy.local` resolves via `/etc/hosts` — run:

```bash
cd wireguard-configs
sudo ./add-vpn-hosts.sh
```

This keeps your normal DNS for Kubernetes (Open Lens), internet, etc. Only `*.blumefy.local` comes from the hosts file.

### 5. Access the Dashboard

1. Open your browser
2. Go to: **https://dashboard.blumefy.local**
3. Accept the self-signed certificate (one-time; click "Advanced" → "Proceed")
4. You'll see the internal dashboard with links to all apps

### 6. Disconnect

Click "Deactivate" in WireGuard (or `wg-quick down wg0` on CLI). To remove the hosts entries: `sudo ./remove-vpn-hosts.sh` from `wireguard-configs/`.

---

## What You Have: Internal Applications

When connected to WireGuard, these URLs are available at `*.blumefy.local`:

| URL | Service | Description |
|-----|---------|-------------|
| **https://dashboard.blumefy.local** | Internal Dashboard | Landing page with links to all internal apps |
| https://traefik.blumefy.local/dashboard/ | Traefik | Ingress controller dashboard; routes, services, TLS |
| https://argocd.blumefy.local | Argo CD | GitOps deployment UI; sync apps from GitHub |
| https://infisical.blumefy.local | Infisical | Secrets management; store and inject secrets into apps |
| https://rabbitmq-dev.blumefy.local | RabbitMQ (Dev) | Message broker management UI — dev namespace |
| https://rabbitmq.blumefy.local | RabbitMQ (Prod) | Message broker management UI — prod namespace |
| https://redis-dev.blumefy.local | Redis (Dev) | Redis Commander — browse keys, CLI |
| https://redis.blumefy.local | Redis (Prod) | Redis Commander — browse keys, CLI |
| metallb.blumefy.local | MetalLB | (No web UI; host resolves for kubectl / status checks) |

**Note:** Traefik dashboard requires the trailing slash: `/dashboard/`

---

## How It Works

### DNS: Hosts file (default) vs dnsmasq

- **Default (`vpn_use_dnsmasq: false`)**: Use `add-vpn-hosts.sh` for `*.blumefy.local`. Your normal DNS stays intact — Kubernetes (Open Lens), internet, etc. keep working. Recommended on Mac.
- **Optional (`vpn_use_dnsmasq: true`)**: WireGuard config gets `DNS = 10.10.10.1`. All DNS goes through dnsmasq on the VPN. Can break Open Lens and general traffic if dnsmasq is slow or unreachable.

### Security

- **VPN-only access**: IngressRoutes use `vpn-allowlist` middleware (WireGuard subnet `10.10.10.0/24`)
- Requests from outside the VPN are rejected (403)
- **Self-signed TLS**: `.local` domains can't use Let's Encrypt; a self-signed cert is used
- Accept the cert once in your browser; it's safe for internal use

### Architecture

Traefik runs on node1 (the WireGuard server) with `hostPort` 80/443, so it listens directly on 10.10.10.1. Traffic to `*.blumefy.local` (resolved to 10.10.10.1) hits Traefik; the vpn-allowlist middleware allows only the WireGuard subnet.

```
[Your laptop] --- WireGuard ---> [node1:10.10.10.1]
       |                              |
       | DNS (*.blumefy.local)        | dnsmasq (if vpn_use_dnsmasq)
       |-------------------------------> 10.10.10.1:53
       |
       | HTTPS (dashboard, traefik, argocd, infisical)
       |-------------------------------> 10.10.10.1:443 (Traefik hostPort)
                                            |
                                            | vpn-allowlist middleware
                                            | (only 10.10.10.0/24)
                                            v
                                       Internal services
```

---

## Fallback: Manual Hosts (No VPN DNS)

If you prefer not to use VPN DNS (e.g. you use a custom DNS config), you can add hosts manually:

```bash
cd wireguard-configs
sudo ./add-vpn-hosts.sh    # When connecting
# ... use the apps ...
sudo ./remove-vpn-hosts.sh # When disconnecting
```

---

## Re-import Config After Playbook Run

When you run the playbook with `--tags wireguard` (or full site.yml), the WireGuard configs are regenerated. If DNS was recently added or changed:

1. Re-fetch the config: run `ansible-playbook playbooks/site.yml --tags wireguard` (configs are fetched to `wireguard-configs/`)
2. Re-import `wg-deploy.conf` into your WireGuard app
3. Connect again

---

## Troubleshooting

### Open Lens / kubectl / internet stops when connected

- **Cause:** `DNS = 10.10.10.1` in WireGuard sends all DNS through the VPN. If dnsmasq is slow or unreachable, everything breaks.
- **Fix:** Set `vpn_use_dnsmasq: false` in vars.yml (default). Re-run `--tags wireguard` and re-import your config. Use `add-vpn-hosts.sh` for `*.blumefy.local` instead.
- **Important:** Fully remove the tunnel from the WireGuard app, re-import `wg-deploy.conf`, then connect again — the app may cache old settings.

**If you already have no DNS in config and traffic is still broken:**

1. **Verify config:** Open `wg-deploy.conf` — there must be no `DNS = 10.10.10.1` line.
2. **Quick diagnostics (while connected):**
   - `ping 8.8.8.8` — if this fails, general routing is wrong (not just DNS).
   - `ping 10.10.10.1` — if this fails, VPN routing to the cluster is broken.
3. **Open Lens / x509 cert error:** If Open Lens shows a certificate error like "x509: certificate is valid for ... not 10.10.10.1", run:
   ```bash
   ansible-playbook playbooks/add-vpn-tls-san.yml -i inventory/hosts.yml
   ```
   This adds `10.10.10.1` to the K3s API TLS certificate so kubectl and Open Lens work over VPN.
4. **Config now uses only `10.10.10.0/24`** — `*.blumefy.local` resolves to `10.10.10.1`, so no need for the public IP in AllowedIPs (which caused broken return traffic on some systems).

### "dashboard.blumefy.local" doesn't resolve (DNS_PROBE_FINISHED_BAD_CONFIG)

- **On macOS with wg-quick**: DNS from WireGuard config is often not applied. Use the hosts file:
  ```bash
  cd wireguard-configs && sudo ./add-vpn-hosts.sh
  ```
- **On Linux with WireGuard GUI**: DNS = 10.10.10.1 should work; ensure dnsmasq is running on node1
- If hosts file doesn't help: verify WireGuard is connected and you can ping `10.10.10.1`

### Browser says "Connection refused" or "Cannot reach this page"

- Verify you're on the VPN (ping `10.10.10.1` — you should get replies)
- Ensure Traefik runs on node1 with hostPort 80/443: when `vpn_internal_ui_enabled` is true, Traefik is pinned to the WireGuard node via `nodeSelector` and uses `hostPort` so it listens on 10.10.10.1. Re-run: `ansible-playbook playbooks/site.yml --tags traefik`
- **If your K8s node names differ** (e.g. not `node1`), set `traefik_vpn_node: "<actual-node-name>"` in vars.yml.
- **If Traefik pod won't schedule** (PVC stuck on another node): delete the PVC, then re-run the playbook — `kubectl delete pvc -n traefik -l app.kubernetes.io/name=traefik`

### Curling https://10.10.10.1 returns "404 page not found"

- **Expected:** Traefik has no route for the bare IP. Use hostnames: `https://dashboard.blumefy.local`, `https://traefik.blumefy.local/dashboard/`, etc. Run `add-vpn-hosts.sh` so `*.blumefy.local` resolves to 10.10.10.1.

### Certificate warning

- Expected: `.local` uses a self-signed cert
- Click "Advanced" → "Proceed to dashboard.blumefy.local" (wording varies by browser)

### 403 Forbidden on *.blumefy.local

- Traefik sees your request but the `vpn-allowlist` middleware rejected it (only `10.10.10.0/24` is allowed)
- **Cause:** Either traffic isn't going through the VPN, or Traefik doesn't see the real client IP (Kubernetes SNAT)
- **Fixes:**
  1. **Hosts file / DNS** must resolve `*.blumefy.local` to `10.10.10.1` (WireGuard IP), not the public IP. Run `sudo ./add-vpn-hosts.sh` from `wireguard-configs/`. With `10.10.10.1`, traffic stays inside the VPN (`AllowedIPs = 10.10.10.0/24`).
  2. **externalTrafficPolicy: Local** on the Traefik service preserves client IP. Re-run: `ansible-playbook playbooks/site.yml --tags traefik`
  3. **Verify:** When connected, `ping 10.10.10.1` should work. Check Traefik logs: `kubectl logs -n traefik -l app.kubernetes.io/name=traefik --tail=20` to see the client IP of recent requests.

### kubectl works but browser doesn't

- kubectl uses the Kubeconfig API endpoint (10.10.10.1:6443); browser uses Traefik (public IP:443)
- Both require VPN; if kubectl works, VPN is fine — check that Traefik has the VPN IngressRoutes and TLS secrets

---

## Configuration Reference

| Variable | Location | Purpose |
|----------|----------|---------|
| `vpn_internal_ui_enabled` | `vars.yml` | Enable/disable VPN-internal UIs (default: true) |
| `vpn_internal_domain` | `vars.yml` | Domain for internal URLs (default: blumefy.local) |
| `vpn_internal_hosts` | `vars.yml` | List of hostnames (dashboard, traefik, argocd, etc.) |
| `wireguard_subnet` | `vars.yml` | VPN subnet (10.10.10.0/24) — only this can access the UIs |
| `traefik_crd_api_group` | `vars.yml` | `traefik.io` (Traefik v3, default) — v2 used `traefik.containo.us` |
| `traefik_vpn_node` | `vars.yml` | K8s node name for Traefik when VPN internal enabled (default: node1). Override if your node has a different hostname. |
| `vpn_use_dnsmasq` | `vars.yml` | `false` (default) = use hosts file, keep normal DNS for K8s/Lens; `true` = all DNS via VPN (can break things) |
| `wireguard_node1_ip` | `vars.yml` | node1 VPN IP (10.10.10.1) — dnsmasq listens here; also where Traefik hostPort binds |

---

## Investigating 403 Forbidden

If you get Forbidden when accessing `*.blumefy.local`, run these from a machine that can reach the cluster (e.g. over SSH to node1):

```bash
# 1. Check which Traefik CRD API your cluster uses
kubectl get crd | grep -i traefik

# 2. Check the vpn-allowlist middleware (traefik.io for v3)
kubectl get middleware.v1alpha1.traefik.io vpn-allowlist -n traefik -o yaml

# 3. Check IngressRoutes for dashboard
kubectl get ingressroute -A | grep -E "dashboard|vpn"

# 4. Check what source IP Traefik sees (add a test IngressRoute with a custom response header, or check Traefik access logs)
kubectl logs -n traefik -l app.kubernetes.io/name=traefik --tail=50

# 5. Verify *.blumefy.local resolves to 10.10.10.1 (wireguard_node1_ip) — run add-vpn-hosts.sh
# AllowedIPs = 10.10.10.0/24 is enough (no public IP needed)
```

**Common cause:** Traffic to `*.blumefy.local` must go through the VPN. The hosts file now maps `*.blumefy.local` → `10.10.10.1` so traffic stays in the tunnel (`AllowedIPs = 10.10.10.0/24`). Run `add-vpn-hosts.sh` before accessing.

---

## Why "Not Secure" in the Browser?

`*.blumefy.local` uses a **self-signed TLS certificate**. Browsers show "Not Secure" because they don't trust certificates not issued by a public CA (like Let's Encrypt).

- **Let's Encrypt** cannot issue certs for `.local` domains (they're not publicly resolvable)
- **Self-signed** is the standard approach for internal `.local` domains
- **Safe to use:** Click "Advanced" → "Proceed to dashboard.blumefy.local" once; the connection is still encrypted, just not CA-verified
- **Traefik cannot "secure DNS"** — DNS and TLS are separate layers. Traefik terminates HTTPS; the "Not Secure" warning is about the certificate, not DNS

To remove the warning you would need to add the self-signed CA to your system trust store (more involved) or use a publicly resolvable domain with Let's Encrypt.

---

## Related Documentation

- [README.md](../README.md) — Full project overview
- [docs/ARGOCD_SUBMODULE.md](ARGOCD_SUBMODULE.md) — Argo CD submodule setup
- [docs/RECOVERY.md](RECOVERY.md) — Recovery when locked out
