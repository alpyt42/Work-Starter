# Actions — <mission>

> To copy to `<project>/state/actions.md` (links written for a client mission). This register is authoritative for ID, owner, due date and status; keep the client's ID prefix, including across missions. The action line keeps the ID, owner, title and Tasks metadata (priority, `📅` precise due date, `⏳` chosen work date); only due-date nuances, the source and the history go in sub-bullets. Do not duplicate a `📅` date in a sub-bullet. States: `[ ]` to do · `[/]` in progress · `[w]` waiting (reminded) · `[x]` done · `[-]` cancelled. The board [`tasks.md`](../../../../../../tasks.md) displays it with the Tasks plugin. An action closed for more than 30 days moves with its sub-bullets to `actions-archive-YYYY.md`, without asking (IDs stay reserved; see `docs/CONVENTIONS.md`).

## Open
- [ ] **<ID>** — <owner> — <concrete action> 📅 YYYY-MM-DD
    - due: <nuance if needed, otherwise remove this bullet>
    - source: [YYYY-MM-DD-<type>-<slug>](../sources/YYYY-MM/YYYY-MM-DD-<type>-<slug>.md)
    - created: YYYY-MM-DD HH:MM
    - updated: YYYY-MM-DD HH:MM
    - DD/MM: <state change, with its source>

## Done
- [x] **<ID>** — <owner> — <completed action> 📅 YYYY-MM-DD ✅ YYYY-MM-DD
    - source: [YYYY-MM-DD-<type>-<slug>](../sources/YYYY-MM/YYYY-MM-DD-<type>-<slug>.md)
    - done: <dated evidence, or box ticked by the brain owner in the board>

## Cancelled
- [-] **<ID>** — <owner> — <action> ❌ YYYY-MM-DD
    - cancelled: YYYY-MM-DD by <person> — [source](../sources/YYYY-MM/YYYY-MM-DD-<type>-<slug>.md)
