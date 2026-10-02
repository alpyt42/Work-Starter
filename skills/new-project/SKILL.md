---
name: new-project
description: "Start a new project from scratch: frame the problem, write a short spec, pick the stack, plan vertical slices, find specialized skills, and create the repo with agent guardrails."
---

# New project

Take an idea to a ready repo in seven steps, with the user's OK at each checkpoint. Do not write application code before step 7 is done.

**Pace.** Ask up front whether time is tight (interview, demo). If it is, run steps 1 to 6 in about 10 minutes: one batch of questions, short answers, your recommendation first. Otherwise take the time the project needs.

**Language.** Talk with the user in their language; write the repo files (SPEC.md, PLAN.md, AGENTS.md) in English unless they ask otherwise.

## 1. Frame the problem
Ask, in a single batch, only what you cannot infer: who it is for, what problem it solves, what "done" looks like, and hard constraints (time, stack imposed, APIs, data). Then state back:
- 3 to 5 **acceptance criteria**, observable and testable;
- the **non-goals** (what we will not build).

**Checkpoint:** the user confirms or corrects.

## 2. Write the spec
Draft `SPEC.md` from [references/spec-template.md](references/spec-template.md): problem, users and main journey, acceptance criteria, non-goals. Keep it to one page. Show it; the user decides.

## 3. Choose the stack and architecture
Propose the simplest stack that meets the criteria, with one sentence of reasoning, and one alternative. Name the components (front, API, storage, external APIs) and how they talk. Pick the scaffold from [references/scaffolds.md](references/scaffolds.md).

Then **fetch specialized skills** for this stack:
1. List the installed skills that already cover it (for example `uv`, `ruff`, `fastapi`, `pydantic`, `frontend-design`, `webapp-testing`).
2. For each uncovered part (framework, database, cloud, testing tool), search: `npx skills find <keywords>`; check well-known sources first (`anthropics/skills`, `vercel-labs/agent-skills`, the framework's own org).
3. Vet each candidate: official or reputable source, 1K+ installs, and read its `SKILL.md` and scripts. Drop anything off-topic.
4. Propose a short list: skill, source, installs, why. **After the user's OK**, install at project level for both agents: `npx skills add <owner/repo> --skill <name> -a claude-code -a codex -y`. Tell the user a new session may be needed before a new skill shows up.

Also check that the Context7 MCP server is available for current library docs.

**Checkpoint:** the user approves the stack and the skills.

## 4. Remove the unknowns
List what could sink the project: an API never used, an uncertain data format, a quota, a model choice. For each serious one, plan a **spike**: a throwaway test of a few minutes, run before the slice it unblocks. Add them to the spec's risks.

## 5. Plan vertical slices
Draft `PLAN.md` from [references/plan-template.md](references/plan-template.md). Slice 0 is the **walking skeleton**: the app starts and one trivial path crosses every layer. Each next slice adds one feature that works end to end and says how it is checked. Note which slices need a skill not yet installed; fetch it (as in step 3) when that slice starts.

**Checkpoint:** the user approves the plan.

## 6. Define how we verify
For each acceptance criterion, name the proof: a test, a command, or a demo step. Put the commands in the plan. The quality gates come from the guardrails (step 7).

## 7. Create the repo
1. Run the official scaffold (non-interactive flags, `--help` first).
2. From the repo root, install the guardrails for its stacks:
   `bash <this skill's folder>/scripts/install-guardrails.sh <python|node|terraform>...`
   It adds `AGENTS.md`, `CLAUDE.md`, the hooks (`.agents/hooks/format.sh`, `.agents/hooks/guard.sh`), `.claude/settings.json`, `.codex/hooks.json`, `.pre-commit-config.yaml`, `.env.example` and the `.gitignore` lines, and never overwrites an existing file. Merge by hand whatever it reports as kept.
3. Finish the setup of [references/scaffolds.md](references/scaffolds.md#setup-after-the-scaffold): dev tools, `pre-commit install`.
4. Write `SPEC.md` and `PLAN.md`, and fill the **Project** section of `AGENTS.md` from the real scaffold (like `/init`, but into `AGENTS.md`).
5. Verify: the quality gates pass, `pre-commit run --all-files` passes, the app starts.
6. Tell the user: in Codex, run `/hooks` once to trust the project hooks.
7. Propose the first commit (`chore: scaffold <name> with agent guardrails`) and, if wanted, the GitHub repo (`gh repo create <name> --private --source . --remote origin`). Do both only after the user's OK; the guard blocks `git push`, so the user pushes.

Then hand over: summary of the repo, the skills installed, and slice 0 as the next step.
