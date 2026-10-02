# Official scaffolds by stack

Always use the official generator of the stack; never hand-write a skeleton it can produce. Commands evolve: run `<tool> --help` (or read its current docs) first, and prefer non-interactive flags.

| Need | Scaffold | Guardrails stack |
|---|---|---|
| Python app, script, API base | `uv init --app <name>` | python |
| Python library | `uv init --lib <name>` | python |
| Python CLI (installable) | `uv init --package <name>` | python |
| FastAPI API | `uv init --app <name>` then `uv add "fastapi[standard]"` | python |
| FastAPI + React + Postgres, full stack | `fastapi/full-stack-fastapi-template` (follow its README, it uses copier) | python node |
| Django | `uv init --app <name>`, `uv add django`, `uv run django-admin startproject config .` | python |
| Data or LLM demo UI | `uv init --app <name>` then `uv add streamlit` | python |
| React SPA | `npm create vite@latest <name> -- --template react-ts` | node |
| Vue / Svelte SPA | `npm create vite@latest <name> -- --template vue-ts` / `npx sv create <name>` | node |
| Next.js | `npx create-next-app@latest <name>` | node |
| Node API | `npm create hono@latest <name>` | node |
| API + front in one repo | `backend/` with `uv init --app`, `frontend/` with `npm create vite@latest` | python node |
| Terraform | No generator: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf` (HashiCorp standard module structure), then `terraform init` | terraform |
| Other (Go, Rust…) | The official tool (`go mod init`, `cargo new`…) | none yet: hooks and gates by hand |

## Setup after the scaffold
- Python: `uv add --dev ruff ty pytest`, and a first test so `pytest` has something to run.
- Node: make sure `prettier`, `eslint` and `typescript` are dev dependencies (`npm i -D prettier` if missing); delete the eslint or tsc hook in `.pre-commit-config.yaml` if the project has no such tool.
- Terraform: install `terraform` and `tflint` if missing (ask first).
- Several folders (`backend/`, `frontend/`): in `.pre-commit-config.yaml`, point the local hooks to their folder (`uv run --project backend ty check`, `npm --prefix frontend exec -- tsc --noEmit`).
- pre-commit itself: `uv tool install pre-commit` once per machine, then `pre-commit install` in each repo.
