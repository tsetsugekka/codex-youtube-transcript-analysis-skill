# Repository Publishing Discipline

- Before committing, run `git branch --show-current` and confirm the intended target branch, normally `main`.
- Do not continue publishing from an old temporary branch by inertia.
- Never commit credentials, cookies, private paths, account data, generated transcripts, virtual environments, caches, or logs.
- Stage only files intended for the current release and review `git status --short` plus `git diff --check` before committing.
- When the repository's purpose or release scope changes, keep the GitHub description and Topics accurate and verify them after writing.
- Push directly to `main` only when the user explicitly asks to publish; otherwise stop before pushing.
