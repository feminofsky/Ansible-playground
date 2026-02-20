# Playbooks

| Playbook | Purpose |
|----------|---------|
| **site.yml** | Main playbook — full setup from scratch (or apply config changes). Run this first. |
| **bootstrap.yml** | One-time base setup on fresh VPS (user, SSH, packages). Run before `site.yml` on new nodes. |
| **update.yml** | Rolling zero-downtime updates (K3s + OS). |
| **drain-node.yml** | Safely drain a node for maintenance. Use `-e target_node=node1` or `node2` (must exist in inventory). |
| **refresh-ufw.yml** | Refresh UFW rules (after WireGuard or firewall var changes). |
| **test-cross-node-pods.yml** | Test cross-node pod communication (DNS + HTTP). |
| **migrate-to-vpn.yml** | Migrate cluster to full VPN (nodes use 10.10.10.x). |
| **prepare-for-vpn-migration.yml** | Prep steps before VPN migration. |
| **rollback-vpn-config.yml** | Rollback VPN configuration. |
| **add-vpn-tls-san.yml** | Add VPN SAN to K3s TLS cert. |
| **k3s-rotate-cert-vpn.yml** | Rotate K3s cert for VPN. |
| **cleanup-k3s.yml** | Remove K3s from cluster. |
| **infisical-unlock-migrations.yml** | Unlock Infisical migrations. |
| **cluster-resource-report.yml** | Cluster CPU/memory report + capacity for dev/prod services (helm/base). |

## Usage

```bash
# From project root
ansible-playbook playbooks/site.yml -i inventory/hosts.yml --ask-vault-pass
```

See root [README.md](../README.md) for full documentation.
