# Example service

Uses `helm/base` with dev/prod overlays.

**Note:** The base chart mounts AWS Secrets Store. For local/dev without AWS:
- Add `secrets: ["DUMMY"]` and ensure the base's SecretProviderClass can be satisfied, or
- Modify `helm/base/templates/deployment.yaml` to make the secrets volume conditional when `secrets` is omitted
