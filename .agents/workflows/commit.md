---
description: How to commit and push changes after each implementation step
---

# Commit Workflow

After completing an implementation step:

// turbo-all

1. Stage all changes:
```bash
git add -A
```

2. Check what's staged:
```bash
git status --short
```

3. Commit with a descriptive message:
```bash
git commit -m "type: description"
```

Where `type` is one of:
- `feat:` — New feature or functionality
- `fix:` — Bug fix
- `refactor:` — Code restructuring (no behavior change)
- `docs:` — Documentation changes only
- `chore:` — Build, config, or tooling changes

4. Push to remote:
```bash
git push
```

5. Verify push succeeded (exit code 0, no errors).
