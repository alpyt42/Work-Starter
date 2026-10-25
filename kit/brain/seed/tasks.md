---
cssclasses:
  - tasks-dashboard
---

# Actions

Next actions, the list by project and the kanban, in one place. Until the owner is set in the starter, the views show every owner.

> [!task-nav]
> [Focus](#focus) · [By project](#by-project) · [Kanban](#kanban) · [History](#history) · [Inbox](inbox/inbox.md)

```meta-bind-button
label: New action
icon: plus
style: primary
tooltip: Add a task to the register of the chosen project
actions:
  - type: runTemplaterFile
    templateFile: kit/brain/templates/templater/new-action.md
```

Choose the project, then fill in the action. The form files it in the right place with its ID, priority and due date.

> [!info]- In the browser
> From the Work root, run `uv run tools/tasks-web/tasks-web.py`, then open `http://127.0.0.1:8765/`. This [local interface](../tools/tasks-web/README.md) reads and edits the same registers.

## Focus

> [!task-focus]+ Today
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> (scheduled before tomorrow) OR (due before tomorrow)
> sort by priority
> sort by due
> sort by description
> ```

> Pick up to three actions with the pencil 📝: **Scheduled = today**. Today's due dates, overdue actions and unfinished scheduled actions show up here.

> [!task-grid]
> > [!task-active]+ In progress
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is IN_PROGRESS
> > sort by priority
> > sort by due
> > sort by description
> > ```
>
> > [!task-next]+ Up next
> > The first 8 by priority, then due date. The full list stays in the projects.
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is TODO
> > (no scheduled date) OR (scheduled after today)
> > (no due date) OR (due after today)
> > (no start date) OR (starts before tomorrow)
> > sort by priority
> > sort by due
> > sort by description
> > limit 8
> > ```

> [!task-wait]+ Follow up
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> status.type is ON_HOLD
> sort by due
> sort by priority
> sort by description
> ```

> [!task-calendar]- Due · next 7 days
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> (status.type is TODO) OR (status.type is IN_PROGRESS) OR (status.type is ON_HOLD)
> due after today
> due on or before in 7 days
> sort by due
> sort by priority
> sort by description
> ```

## By project

> [!task-project]- [System setup](projects/internal/setup/setup.md)
> ```tasks
> path includes {{BRAIN}}/projects/internal/setup/state/actions.md
> (status.type is TODO) OR (status.type is IN_PROGRESS) OR (status.type is ON_HOLD)
> sort by status.type
> sort by status.name reverse
> sort by priority
> sort by due
> sort by description
> ```

> [!task-project]- Other projects
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> path does not include {{BRAIN}}/projects/internal/setup/state/actions.md
> (status.type is TODO) OR (status.type is IN_PROGRESS) OR (status.type is ON_HOLD)
> sort by path
> sort by status.type
> sort by status.name reverse
> sort by priority
> sort by due
> sort by description
> ```

Add a dedicated box when a project must stay visible, then exclude its register from “Other projects”.

## Kanban

To move an action, right-click its checkbox or use the pencil 📝. The columns read the registers directly.

> [!board]
> > [!column] To do
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is TODO
> > sort by priority
> > sort by due
> > short mode
> > ```
>
> > [!column] In progress
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is IN_PROGRESS
> > sort by priority
> > sort by due
> > short mode
> > ```
>
> > [!column] Waiting
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is ON_HOLD
> > sort by due
> > sort by priority
> > short mode
> > ```
>
> > [!column] Recently done
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > (status.type is DONE) OR (status.type is CANCELLED)
> > (has done date) OR (has cancelled date)
> > sort by done reverse
> > sort by cancelled reverse
> > limit 10
> > short mode
> > ```

## History

> [!task-history]- Last 15 closed
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions(-archive-\d{4})?\.md$/
> (status.type is DONE) OR (status.type is CANCELLED)
> (has done date) OR (has cancelled date)
> sort by done reverse
> sort by cancelled reverse
> limit 15
> ```

> [!help]- How to
> **Finish**: tick the checkbox; the done date is added to the register.
>
> **Start or put on hold**: right-click the checkbox, or use the pencil 📝, then choose the state.
>
> **Prioritise**: choose a priority with the pencil 📝. **Scheduled** says when to work on it; **Due** says when to deliver.
>
> **Capture without filing**: write in the [Inbox](inbox/inbox.md), then triage it later.
>
> Plain dates are read by Tasks. Vague wordings stay in the register. See the [conventions](../kit/brain/docs/CONVENTIONS.md).
