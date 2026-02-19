# Argo CD GitOps — Services

All services use the shared **helm/base** chart. Dev and prod overlays customize per environment.
Push to GitHub; Argo CD pulls and syncs to the cluster.

**Git:** Initialized as its own repo. Push to GitHub:
```bash
cd argocd
git add .
git commit -m "Initial Argo CD services"
git remote add origin git@github.com:YOUR_ORG/gitops-services.git
git branch -M main
git push -u origin main
```

## Structure

```
argocd/
├── helm/
│   ├── base/                    # Shared Helm chart (all services)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   └── overlays/
│       ├── dev/                 # Dev-specific overrides
│       │   └── example-values.yaml
│       └── prod/                # Prod-specific overrides
│           └── example-values.yaml
├── services/
│   └── example/
│       └── values.yaml          # Base values for example service
├── applications/                # Argo CD Application manifests
│   ├── example-dev.yaml
│   └── example-prod.yaml
└── README.md
```

## Flow

1. **helm/base** — shared chart; each service defines values under `app.<name>`
2. **services/example/values.yaml** — base values for the example service
3. **helm/overlays/{dev,prod}/** — env-specific overrides (replicas, namespace, etc.)
4. **applications/** — YAML files that ApplicationSet reads to create Applications automatically

## ApplicationSet (automatic)

Ansible installs Argo CD with:
- **AppProjects:** `dev`, `prod` (each allows its namespace)
- **ApplicationSet:** Watches `applications/*.yaml` in the Git repo and creates Applications. Uses multiple sources so changes to `helm/overlays/*` and `services/*` trigger syncs.

Set in Ansible vars.yml:
```yaml
argocd_gitops_repo_url: "git@github.com:YOUR_ORG/gitops-services.git"
```

Each file in `applications/` uses this format. `valueFiles` are derived from the convention: `services/<releaseName>/values.yaml` + `helm/overlays/<namespace>/<releaseName>-values.yaml`.
```yaml
app:
  name: example-dev
  project: dev          # must match an AppProject
  source:
    path: helm/base
    helm:
      releaseName: example
  destination:
    namespace: dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

Add a file → push to GitHub → ApplicationSet creates the Application within ~3 minutes.

## Add a new service

1. Create `services/MY-SERVICE/values.yaml` (model after example)
2. Create `helm/overlays/dev/MY-SERVICE-values.yaml` and `helm/overlays/prod/MY-SERVICE-values.yaml`
3. Copy `applications/example-dev.yaml` → `applications/MY-SERVICE-dev.yaml` (update name, valueFiles paths)
4. Commit and push
