# Traefik: running 2+ replicas (HA)

Traefik uses a **persistent volume** for ACME/Let’s Encrypt certificate storage (`/data/acme.json`). The default storage class usually provides **ReadWriteOnce (RWO)**, so only one pod can mount the volume and a second replica cannot schedule.

## Option: use ReadWriteMany (RWX) storage

To run **2 or more replicas**, the persistence volume must use a storage class that supports **ReadWriteMany (RWX)** so all replicas can mount the same volume and share the same certs.

### 1. Install an RWX-capable storage class (if you don’t have one)

Examples:

- **Longhorn** (common on K3s): provides RWX via NFSv4. Install Longhorn, then create a StorageClass (or use the default) that uses Longhorn with `accessMode: ReadWriteMany`.
- **NFS subdir external provisioner**: point at an NFS server; provisioned volumes can be RWX.

Check existing storage classes and access modes:

```bash
kubectl get storageclass
kubectl get sc <name> -o yaml   # check provisioner and allowed access modes
```

### 2. Set vars and re-run Traefik

In `inventory/group_vars/all/vars.yml`:

```yaml
traefik_replicas: 2
traefik_persistence_storage_class: "longhorn"   # or your RWX storage class name
```

Then:

```bash
ansible-playbook playbooks/site.yml --tags traefik -l node1
```

- If you had a **single-replica** Traefik with an existing RWO PVC, delete the old PVC after scaling to 2 with a new storage class (Traefik will create a new PVC with the new class). Certs will be re-issued by ACME on first start.
- With **VPN internal UI** and **2 replicas**, the role does **not** pin Traefik to a single node, so pods can spread across nodes; each node’s pod will bind hostPort 80/443 on that node. VPN access via `10.10.10.1` still hits only the node that has the WireGuard endpoint; for HA on VPN you’d need both nodes reachable (e.g. second WireGuard address or LoadBalancer in front).

### 3. If you stay on 1 replica

Leave `traefik_replicas: 1` and `traefik_persistence_storage_class: ""`. No changes needed.
