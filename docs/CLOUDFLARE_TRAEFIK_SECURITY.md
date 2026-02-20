# Cloudflare → Traefik: Best Security Setup

When pointing DNS from Cloudflare to Traefik, follow these steps for strong security.

## Internal DNS (*.blumefy.local) — Unaffected

**Cloudflare and Traefik proxy settings do not affect your internal DNS or VPN-only UIs.**

- **dnsmasq** on node1 resolves `*.blumefy.local` to the WireGuard IP (10.10.10.1) only for VPN clients. It is not changed by the Traefik or Cloudflare configuration.
- **VPN internal UIs** (dashboard, Traefik, Argo CD, Infisical at `*.blumefy.local`) are reached over the VPN; traffic goes client → WireGuard → Traefik on 10.10.10.1. That path never goes through Cloudflare or the public internet.
- Traefik’s Cloudflare options (forwarded headers, Authenticated Origin Pulls) only affect requests that hit the **public** entrypoints (80/443 on the node’s public IP). Routing by hostname is unchanged: `*.blumefy.local` still uses the VPN-only IngressRoutes and allowlist; public domains still use your public IngressRoutes.

## 1. Cloudflare Dashboard

### Proxy (orange cloud)
- **Turn proxy ON** (orange cloud) for your A/AAAA records that point to Traefik.
- Traffic will go: Client → Cloudflare → Traefik. You get DDoS mitigation, WAF, and your origin IP is hidden.

### SSL/TLS
- **SSL/TLS mode: Full (strict)**  
  Encrypts Cloudflare ↔ origin and requires a valid certificate on the origin (your Traefik Let’s Encrypt cert is fine).

### Authenticated Origin Pulls (recommended)
- **SSL/TLS → Origin Server → Authenticated Origin Pulls: On**
- Cloudflare will present a **client certificate** to Traefik. Traefik can be configured to **require and verify** that certificate so that **only Cloudflare** can reach your origin on 443.
- Prevents direct-to-origin attacks even if someone discovers your origin IP.
- Zone-level (shared) AOP is available on all plans; per-hostname uses custom certs.

### Optional: WAF, rate limiting, Bot Fight Mode
- Use Cloudflare WAF and rate limiting for extra protection at the edge.

---

## 2. Traefik: Trust Cloudflare IPs (real client IP)

With the proxy on, Traefik sees **Cloudflare’s IPs**, not the real client. To keep correct client IPs (for logs, rate limiting, VPN allowlists):

- Configure **forwarded headers** so Traefik trusts `X-Forwarded-For` / `CF-Connecting-IP` only from Cloudflare IP ranges.

This repo can do that for you when **Cloudflare proxy is enabled** (see below). Traefik will then use the real client IP from the headers.

---

## 3. Traefik: Authenticated Origin Pulls (optional but strong)

To accept **only** requests that present Cloudflare’s Origin Pull client certificate:

1. **Get Cloudflare’s CA certificate**  
   - Zone-level: [Cloudflare Origin Pull CA](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/set-up/zone-level/) (download the PEM).
2. **Store it in a Kubernetes Secret** in the `traefik` namespace (e.g. `cloudflare-origin-pull-ca` with key `ca.crt` or `tls.ca`).
3. **Create a Traefik TLSOption** that:
   - References that secret.
   - Sets `clientAuthType: RequireAndVerifyClientCert`.
4. **Attach that TLSOption** to the `websecure` entrypoint (or to the Helm `websecure` port TLS options).

After this, only connections that present a valid client cert signed by Cloudflare’s CA will be accepted on 443; direct hits to your origin will fail TLS.

---

## 4. ACME / Let’s Encrypt with Cloudflare in front

- **HTTP-01**: Usually still works: Cloudflare forwards `/.well-known/acme-challenge/*` to your origin, so Traefik can complete the challenge. Ensure “Always Use HTTPS” and any “Block” rules don’t block that path.
- **DNS-01** (optional): For maximum reliability and to avoid depending on HTTP reachability, use a DNS-01 solver with the [Cloudflare API](https://developers.cloudflare.com/api/) (e.g. with `CF_API_TOKEN` and a cert-manager or Traefik DNS challenge). Then validation doesn’t need to hit Traefik at all.

---

## 5. UFW: Restrict 80/443 to Cloudflare + VPN

When `traefik_cloudflare_proxy_enabled: true`, the **refresh-ufw** playbook and the **security** role restrict **80 and 443** so that:

- **80 and 443** are allowed only from **Cloudflare IP ranges** and from your **WireGuard subnet** (so VPN internal UIs at `*.blumefy.local` still work).
- **SSH** remains allowed from anywhere (unchanged).
- Direct hits to your origin from other IPs are dropped at the firewall.

Run after enabling the Cloudflare proxy:

```bash
ansible-playbook playbooks/refresh-ufw.yml -i inventory/hosts.yml
```

The same logic is applied when you run the security role (e.g. in `site.yml`). The Cloudflare IP list is shared with Traefik (see **Ansible variables** below).

## 6. Checklist

| Step | Where | Action |
|------|--------|--------|
| Proxy | Cloudflare DNS | Orange cloud ON for records pointing to Traefik |
| SSL mode | Cloudflare SSL/TLS | **Full (strict)** |
| AOP | Cloudflare SSL/TLS → Origin Server | **Authenticated Origin Pulls: On** |
| Real IP | Ansible/Traefik | Set `traefik_cloudflare_proxy_enabled: true` (see below) so Traefik trusts Cloudflare IPs for forwarded headers |
| UFW | Ansible | Run `refresh-ufw.yml` (or security role) so 80/443 are allowed only from Cloudflare + VPN |
| AOP on origin | Ansible/Traefik | Optional: enable Authenticated Origin Pulls in Traefik (CA secret + TLSOption) |
| WAF / bots | Cloudflare | Enable WAF / Bot Fight Mode as needed |

---

## 7. Ansible variables (this repo)

In `inventory/group_vars/all/vars.yml` (or your override):

```yaml
# Cloudflare proxy in front of Traefik (orange cloud)
traefik_cloudflare_proxy_enabled: true
```

When `traefik_cloudflare_proxy_enabled` is `true`, the Traefik role will:

- Set **forwardedHeaders.trustedIPs** on the `web` and `websecure` entrypoints to Cloudflare’s published IPv4 and IPv6 ranges, so Traefik uses the real client IP from `X-Forwarded-For` / `CF-Connecting-IP`.

Optional (Authenticated Origin Pulls on Traefik):

```yaml
traefik_cloudflare_origin_pull_enabled: true
```

Then download the [Cloudflare Origin Pull CA](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/set-up/zone-level/) PEM and place it at **`roles/traefik/files/cloudflare-origin-pull-ca.pem`**. Run the Traefik role; it will create the secret and TLSOption. If AOP is enabled but the file is missing, the role will fail with a clear message.

---

## 8. Restricting origin access (optional)

- **Authenticated Origin Pulls** (above) is the strongest: only Cloudflare can complete TLS.
- Alternatively (or in addition), at the **firewall** (e.g. UFW), allow 80/443 only from [Cloudflare IP ranges](https://www.cloudflare.com/ips/). That requires keeping the list updated when Cloudflare changes it; this repo’s Cloudflare trusted IP list is used for forwarded headers and can be aligned with firewall rules if you choose to restrict by IP.

---

## 9. References

- [Cloudflare: Authenticated Origin Pulls](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/)
- [Cloudflare IP ranges](https://www.cloudflare.com/ips/) (IPv4 / IPv6)
- [Traefik: Forwarded headers (trustedIPs)](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/)
- [Traefik: TLS options (clientAuth)](https://doc.traefik.io/traefik/reference/routing-configuration/http/tls/)
