# {{BRAIN}}

Private Markdown memory for agent-assisted work. This repository holds only its owner's data: profile, projects, people, sources, registers and skill states. The conventions, guides and templates live in the workspace, under [`../kit/brain/`](../kit/brain/AGENTS.md), and are updated with it.

## Get started

1. Declare the scope of this brain in [`.data/brain.json`](.data/brain.json) (what it holds and must never hold: agents use it to choose the brain to write to), fill in the profile and the voice in [`me/about-me.md`](me/about-me.md), then the owner's display name in [`.data/doctor.json`](.data/doctor.json).
2. Open the full workspace in Obsidian. [`tasks.md`](tasks.md) is the focus page; [`inbox/inbox.md`](inbox/inbox.md) and [`inbox/`](inbox/README.md) receive the captures to triage.
3. Create a first client or project from the [templates](../kit/brain/templates/README.md). The internal project [`setup`](projects/internal/setup/setup.md) tracks the maintenance of the system.
4. Configure a **private** remote before any publication: a brain accumulates professional context and must never become public.

## Map

- [`tasks.md`](tasks.md) — computed view of the actions of every project.
- [`inbox/inbox.md`](inbox/inbox.md) and [`inbox/`](inbox/README.md) — raw capture before filing.
- [`me/about-me.md`](me/about-me.md) — profile, preferences and voice of the owner.
- [`projects/`](projects/README.md) — clients, missions and internal projects.
- [`people/`](people/README.md) — sourced professional person pages.
- [`docs/LOCAL-WORKFLOWS.md`](docs/LOCAL-WORKFLOWS.md) — private paths and local exceptions.
- [`skills/`](skills/README.md) — private skills of this brain.
- [`.data/`](.data/README.md) — scope (`brain.json`), private states and settings.
