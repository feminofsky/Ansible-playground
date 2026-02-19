# Applications (legacy — overlay-based discovery)

Applications are now **discovered automatically** from overlay files.

**No application YAML files needed.** The ApplicationSet scans `helm/overlays/*/*-values.yaml` and creates one Application per file:

| Overlay file | Application | Project | Namespace |
|--------------|-------------|---------|-----------|
| `helm/overlays/dev/example-values.yaml` | example-dev | dev | dev |
| `helm/overlays/prod/example-values.yaml` | example-prod | prod | prod |

**To deploy an app to an environment:** Add `helm/overlays/{env}/{app}-values.yaml`.

**To remove from an environment:** Delete the overlay file. The Application is removed automatically.

## Adding a new app

1. Create `services/{app}/values.yaml` (base values)
2. Add `helm/overlays/dev/{app}-values.yaml` (and/or prod)
3. Push to Git — Argo CD creates the Application(s)
