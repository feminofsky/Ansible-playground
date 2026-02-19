# Argo CD as Git Submodule

The `argocd/` folder is a **git submodule** — its own repo, nested in this project.

## Status

`argocd` is initialized as its own git repo. To complete the submodule setup:

### 1. Create the argocd repo on GitHub

Create a new repository, e.g. [feminofsky/ansible-argocd](https://github.com/new?name=ansible-argocd) (or `gitops-services`).

### 2. Push argocd content

```bash
cd argocd
git remote add origin git@github.com:feminofsky/ansible-argocd.git   # or set-url if already added
git push -u origin main
cd ..
```

### 3. Convert to submodule in main repo

```bash
# Remove argocd from main repo tracking (files stay on disk)
git rm -r --cached argocd

# Add as submodule (clones from the URL you just pushed to)
git submodule add git@github.com:feminofsky/ansible-argocd.git argocd

git add .gitmodules argocd
git commit -m "Convert argocd to git submodule"
git push
```

Or run the script (after creating the repo):

```bash
./scripts/setup-argocd-submodule.sh [git@github.com:YOUR_ORG/your-repo.git]
```

## Using the submodule

```bash
# Clone main repo (argocd will be empty until initialized)
git clone --recurse-submodules git@github.com:feminofsky/Ansible-playground.git

# Or, if already cloned:
git submodule update --init --recursive

# Update argocd to latest
cd argocd && git pull && cd ..
# Or from project root:
git submodule update --remote argocd
```

## Changing the submodule URL

```bash
git submodule set-url argocd git@github.com:YOUR_ORG/your-repo.git
```
