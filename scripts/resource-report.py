#!/usr/bin/env python3
"""
Cluster resource report: parse kubectl output, compute totals and capacity.
Output: key=value lines for Ansible to parse.
"""
import json
import os
import subprocess
import sys

def parse_cpu(s):
    """Convert K8s CPU string to millicores. E.g. '100m'->100, '1'->1000."""
    if not s:
        return 0
    s = str(s).strip()
    if s.endswith('m'):
        return int(s[:-1])
    return int(float(s) * 1000)

def parse_memory_mi(s):
    """Convert K8s memory string to Mi. E.g. '64Mi'->64, '1Gi'->1024."""
    if not s:
        return 0
    s = str(s).strip()
    if s.endswith('Ki'):
        return int(s[:-2]) // 1024
    if s.endswith('Mi'):
        return int(s[:-2])
    if s.endswith('Gi'):
        return int(s[:-2]) * 1024
    if s.endswith('K'):
        return int(s[:-1]) // 1024
    if s.endswith('M'):
        return int(s[:-1])
    if s.endswith('G'):
        return int(s[:-1]) * 1024
    return 0

def main():
    kubeconfig = os.environ.get('KUBECONFIG', '')
    env = os.environ.copy()
    env.setdefault('PATH', '/usr/local/bin:/usr/bin:/bin')
    if kubeconfig:
        env['KUBECONFIG'] = kubeconfig

    per_pod_cpu = int(os.environ.get('DEFAULT_CPU_REQ_M', 100))
    per_pod_mem = int(os.environ.get('DEFAULT_MEM_REQ_MI', 64))
    dev_replicas = int(os.environ.get('DEV_REPLICAS', 1))
    prod_replicas = int(os.environ.get('PROD_REPLICAS', 3))

    # Get nodes
    r = subprocess.run(
        ['kubectl', 'get', 'nodes', '-o', 'json'],
        capture_output=True, text=True, env=env
    )
    if r.returncode != 0:
        print("ERROR: could not get nodes", file=sys.stderr)
        sys.exit(1)

    nodes = json.loads(r.stdout)
    total_alloc_cpu_m = 0
    total_alloc_mem_mi = 0
    for n in nodes.get('items', []):
        a = n.get('status', {}).get('allocatable', {})
        total_alloc_cpu_m += parse_cpu(a.get('cpu', 0))
        total_alloc_mem_mi += parse_memory_mi(a.get('memory', 0))

    # Get pods and sum requests
    r = subprocess.run(
        ['kubectl', 'get', 'pods', '-A', '-o', 'json'],
        capture_output=True, text=True, env=env
    )
    total_req_cpu_m = 0
    total_req_mem_mi = 0
    if r.returncode == 0:
        pods = json.loads(r.stdout)
        for p in pods.get('items', []):
            for c in p.get('spec', {}).get('containers', []):
                res = c.get('resources', {}).get('requests', {})
                total_req_cpu_m += parse_cpu(res.get('cpu'))
                total_req_mem_mi += parse_memory_mi(res.get('memory'))

    avail_cpu_m = max(0, total_alloc_cpu_m - total_req_cpu_m)
    avail_mem_mi = max(0, total_alloc_mem_mi - total_req_mem_mi)

    # DEV: 1 pod per service (100m, 64Mi)
    dev_cpu = avail_cpu_m // (per_pod_cpu * dev_replicas)
    dev_mem = avail_mem_mi // (per_pod_mem * dev_replicas)
    services_dev_fit = min(dev_cpu, dev_mem)

    # PROD: 3 pods per service (300m, 192Mi)
    prod_cpu = avail_cpu_m // (per_pod_cpu * prod_replicas)
    prod_mem = avail_mem_mi // (per_pod_mem * prod_replicas)
    services_prod_fit = min(prod_cpu, prod_mem)

    bottleneck = 'CPU' if dev_cpu < dev_mem else 'Memory'

    out = {
        "total_alloc_cpu_m": total_alloc_cpu_m,
        "total_alloc_mem_mi": total_alloc_mem_mi,
        "total_req_cpu_m": total_req_cpu_m,
        "total_req_mem_mi": total_req_mem_mi,
        "avail_cpu_m": avail_cpu_m,
        "avail_mem_mi": avail_mem_mi,
        "services_dev_fit": services_dev_fit,
        "services_prod_fit": services_prod_fit,
        "bottleneck": bottleneck,
    }
    print(json.dumps(out))

if __name__ == '__main__':
    main()
