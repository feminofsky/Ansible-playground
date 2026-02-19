# K3s Production Infrastructure — Ansible Playbooks
# Automates everything: VPS setup → hardening → K3s HA → MetalLB → Traefik → Monitoring

## Prerequisites (on your local machine)
# - Ansible 2.12+: pip install ansible
# - SSH key pair already generated: ssh-keygen -t ed25519

## Project Structure

ansible/
├── inventory/
│   ├── hosts.yml              # Your node IPs live here
│   └── group_vars/
│       └── all/
│           ├── vars.yml        # Shared variables
│           └── vault.yml       # Encrypted secrets
├── roles/
│   ├── common/                # Base VPS setup (user, packages, kernel)
│   ├── security/              # SSH hardening, UFW, Fail2Ban
│   ├── k3s_server/            # K3s HA cluster install + etcd backups
│   ├── metallb/               # MetalLB bare-metal load balancer
│   ├── traefik/               # Traefik ingress + SSL + security middleware
│   ├── infisical/             # Infisical secrets management (no public ingress)
│   ├── argocd/                # Argo CD GitOps (submodule — own repo)
│   ├── namespaces/            # Phase 7: prod/dev namespaces, Redis + RabbitMQ in dev
│   ├── k8s_access/            # Grant team members kubectl access via ServiceAccount
│   └── monitoring/            # Prometheus + Grafana + alerts
└── playbooks/
    ├── site.yml               # MAIN: runs everything start to finish
    ├── update.yml             # Rolling zero-downtime updates
    └── drain-node.yml         # Safely drain a node

## Step 1 — Configure your nodes

# Edit inventory/hosts.yml — replace with your Contabo IPs
# Edit inventory/group_vars/all/vars.yml — set your domain, email, subdomains

## Step 2 — Set up Ansible Vault (for secrets)

# Create vault file with your secrets
ansible-vault create inventory/group_vars/all/vault.yml

# Add these to the vault file:
# vault_deploy_password: "your-strong-password"
# vault_k3s_token: "your-random-token-min-32-chars"
# vault_grafana_password: "your-grafana-password"
# vault_infisical_auth_secret: "$(openssl rand -base64 32)"    # For Infisical
# vault_infisical_encryption_key: "$(openssl rand -hex 16)"    # For Infisical
# vault_dev_redis_password: "dev-redis-xxx"                     # Phase 7: dev Redis
# vault_dev_rabbitmq_user: "user"
# vault_dev_rabbitmq_password: "dev-rabbitmq-xxx"              # Phase 7: dev RabbitMQ
# vault_prod_redis_password: "prod-redis-xxx"                   # Phase 7: prod Redis
# vault_prod_rabbitmq_user: "user"
# vault_prod_rabbitmq_password: "prod-rabbitmq-xxx"            # Phase 7: prod RabbitMQ
# vault_argocd_repo_ssh_key: |                                 # Argo CD: private repo deploy key
#   -----BEGIN OPENSSH PRIVATE KEY-----
#   ...
#   -----END OPENSSH PRIVATE KEY-----

# Generate a secure K3s token:
# openssl rand -hex 32

## Step 3 — Bootstrap (first-time only: root has no SSH key yet)

On fresh Contabo VPS, root login uses the password from your setup email. Run:

ansible-playbook playbooks/bootstrap.yml -i inventory/hosts.yml -k --ask-vault-pass

You'll be prompted for: `-k` (root SSH password) and `--ask-vault-pass` (vault secrets).

After bootstrap, update `inventory/hosts.yml` to use `ansible_user: deploy` and `ansible_port: 2222`. Then test connectivity and run the full setup.

## Step 4 — Test connectivity

ansible all -i inventory/hosts.yml -m ping

## Step 5 — Run full setup (takes ~10-15 minutes)

# One-shot (bootstrap inline; use root password for phases 1–2):
ansible-playbook playbooks/site.yml \
  -i inventory/hosts.yml \
  -k -e ansible_bootstrap=true \
  --ask-vault-pass

# Or, after bootstrap: key-based only
ansible-playbook playbooks/site.yml \
  -i inventory/hosts.yml \
  --ask-vault-pass

## Other playbooks

# Rolling update (K3s + OS) — zero downtime:
ansible-playbook playbooks/update.yml -i inventory/hosts.yml --ask-vault-pass

# Drain a specific node:
ansible-playbook playbooks/drain-node.yml -i inventory/hosts.yml -e "target_node=node3"

# Refresh UFW (after adding WireGuard or changing firewall vars):
ansible-playbook playbooks/refresh-ufw.yml -i inventory/hosts.yml

# Test cross-node pod communication (server on node1, client on node2 — DNS + HTTP):
ansible-playbook playbooks/test-cross-node-pods.yml -i inventory/hosts.yml

# Migrate cluster to full VPN (nodes use 10.10.10.x, lock firewall to VPN only):
# 1. Connect via WireGuard first
# 2. ansible-playbook playbooks/migrate-to-vpn.yml -i inventory/hosts.yml
# 3. Set wireguard_full_vpn: true in vars.yml
# 4. ansible-playbook playbooks/refresh-ufw.yml -i inventory/hosts.yml

# Run only specific roles (tags):
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags security
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags traefik
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags monitoring
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags infisical
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags namespaces
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags argocd
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --tags k8s_access

# Dry run (check mode — no changes made):
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --check

# Run with verbose output:
ansible-playbook playbooks/site.yml -i inventory/hosts.yml -vvv

## After setup — what you'll have

# - 3-node HA K3s cluster (any node can die, cluster keeps running)
# - SSH locked down (key-only, port 2222, no root)
# - UFW firewall with exact K3s port rules
# - Fail2Ban blocking brute force attempts
# - MetalLB assigning your node1 IP to Traefik
# - Traefik routing all 5 subdomains with auto SSL
# - Prometheus + Grafana monitoring at grafana.yourdomain.com
# - Daily etcd backups via systemd timer
# - Automatic security updates enabled

## Grant team member Kubernetes access (kubectl only — no SSH/server access)

Add team members to `vars.yml` under `k8s_team_members`:

```yaml
k8s_team_members:
  - name: alice
    role: cluster-admin   # or: edit (read+write), view (read-only)
```

Run: `ansible-playbook playbooks/site.yml --tags wireguard,k8s_access` (or full playbook)

**With WireGuard (default):** Cluster, etcd, and API use the VPN. No public exposure.
- Kubeconfigs: `kubeconfigs/<name>-kubeconfig.yml`
- WireGuard configs: `wireguard-configs/wg-<name>.conf`
- Share both. The team member installs WireGuard, imports their config, connects, then uses kubectl.
- Your own config: `wireguard-configs/wg-deploy.conf` — connect locally for admin access.

**Without WireGuard** (`wireguard_enabled: false`): Add each admin IP to `k3s_api_allowed_ips`, re-run security role.

## VPN-internal UIs (*.blumefy.local)

When `vpn_internal_ui_enabled: true` (default), Traefik exposes these UIs at `*.blumefy.local` **only** to WireGuard subnet. Uses self-signed TLS (accept once in browser).

**Automatic DNS:** dnsmasq on node1 resolves `*.blumefy.local` when you're connected. Just connect to WireGuard and open **https://dashboard.blumefy.local** — no scripts or `/etc/hosts` needed. (Re-import your WireGuard config after running the playbook to get the DNS setting.)

| URL | Service |
|-----|---------|
| **https://dashboard.blumefy.local** | **Internal dashboard** — landing page with links to all apps |
| https://traefik.blumefy.local/dashboard/ | Traefik dashboard |
| https://argocd.blumefy.local | Argo CD UI |
| https://infisical.blumefy.local | Infisical UI |
| metallb.blumefy.local | MetalLB has no UI; host resolves for convenience |

**Fallback** (if not using VPN DNS): Run `sudo ./add-vpn-hosts.sh` from `wireguard-configs/` to add hosts to `/etc/hosts`.

## Argo CD GitOps (GitHub → cluster)

Argo CD runs in the cluster and **pulls from GitHub** — no need to expose the K3s API.

**Note:** `argocd/` is a git submodule (its own repo). See [docs/ARGOCD_SUBMODULE.md](docs/ARGOCD_SUBMODULE.md) for setup.

**AppProjects:** `dev`, `prod` (each allows deploying to its namespace)

**ApplicationSet:** Watches `applications/*.yaml` in the Git repo and automatically creates Applications. Add a file → push → Application appears in Argo CD.

1. Set in `vars.yml`:
```yaml
argocd_gitops_repo_url: "git@github.com/YOUR_ORG/gitops-services.git"
```

2. For **private repos**: add `vault_argocd_repo_ssh_key` to vault.yml (SSH deploy key).

3. Run: `ansible-playbook playbooks/site.yml --tags argocd`

4. Add YAML files to `applications/` in your repo (see `argocd/applications/example-dev.yaml` format).

5. Access Argo CD: `https://argocd.blumefy.local` (when on VPN) or `kubectl port-forward -n argocd svc/argocd-server 8080:443` → https://localhost:8080

## Recovery — Locked out of a node?

If bootstrap fails and you can't SSH in, use Contabo's VNC console and follow **docs/RECOVERY.md**.

## Useful Ansible commands

# Check all nodes are reachable:
ansible all -i inventory/hosts.yml -m ping

# Run ad-hoc command on all nodes:
ansible all -i inventory/hosts.yml -a "df -h" --become

# Reboot all nodes (careful!):
ansible all -i inventory/hosts.yml -m reboot --become

# Check K3s status on all nodes:
ansible all -i inventory/hosts.yml -a "systemctl status k3s" --become

# Get K3s version on all nodes:
ansible all -i inventory/hosts.yml -a "k3s --version" --become
