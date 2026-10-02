---
name: brain-clean
description: Audit and reconcile the private brain, its kanban, sources, links, Git hygiene, and workspace routing. Use for requests to clean or check the brain.
---

# brain-clean

Read `brain/AGENTS.md`, `brain/today.md`, and `brain/kanban.md` first. This skill checks the memory and the placement of files in `repos/`, `artifacts/`, and `agents/`; it does not audit every code clone.

1. Record existing `git status`, staged paths, and unpushed commits in the brain repository before editing. Never overwrite unrelated work or read `.env` files.
2. Run `uv run skills/brain-clean/scripts/doctor.py` from the Work root; set `WORK_DIR` or `BRAIN_DIR` only to point at another location. Treat `REVIEW` findings as questions, not automatic edits. Run `uv run tools/check-links.py` and `git -C brain diff --check`.
3. Resolve clear structure and link errors. For ambiguous actions, decisions, identity, duplicate content, or file placement, present the evidence and ask the owner to decide. Leave unresolved items visible.
4. Reconcile `state/actions.md`, `kanban.md`, and `today.md` together when action status changes. Keep source entries historical; use addenda rather than silently rewriting them.
5. Never archive or delete a source without an explicit request. Propose changes to `about-me.md`, `voice.md`, or `topics/` before writing them.
6. Leave a short dated timeline entry in the relevant project, with remaining work. Check the final diff and links. Propose a commit; commit and push only on separate explicit requests.
