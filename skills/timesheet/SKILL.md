---
name: timesheet
description: Produce a read-only Toggl-to-Boond timesheet proposal by day and project, in 0.05-day steps, each worked day worth exactly 1. Use for timesheet and time allocation requests.
---

# timesheet

The script reads Toggl and `brain/.data/boond-mapping.json`; it never writes to Toggl or Boond. The owner enters the result manually. Never read or print `tools/.env` or a key: only the script loads its token. Never invent a Boond line. Keep client names and mappings in the private brain, outside this skill.

## Fast path

Run everything from the Work root.

1. **Period.** Default to the current week, Monday to Friday. Ask only when the request is unclear. `--offset 0` is the current week and `--offset -1` the previous one; otherwise pass `--from YYYY-MM-DD --to YYYY-MM-DD` (`--to` defaults to start + 4 days).
2. **Token check, without reading it:** `test -f tools/.env && echo ok`. If it is missing, ask the owner to recreate it from `tools/.env.example`; Git does not restore it.
3. **One fetch, saved for reuse.** Each call costs one Toggl request: the free plan allows about 30 per hour, and the remaining quota is printed on stderr. `agents/` is ignored scratch.

   ```bash
   uv run tools/toggl.py boond --offset 0 --json > agents/timesheet.json
   ```

4. **Render the grid.** The filter recomputes totals from the days shown, so a long period fetched once can be split into weekly tables:

   ```bash
   jq -rf skills/timesheet/grid.jq agents/timesheet.json
   jq -rf skills/timesheet/grid.jq --arg from 2026-09-07 --arg to 2026-09-11 agents/timesheet.json
   ```

   A working day is 7 h. Days more than 1 h short are flagged ⚠️; change this with `--arg base 7 --arg tol 1`.

5. **Report** the grid, then one line each for the Toggl hours per day, incomplete days, allocations rounded to zero, unmapped projects, and weekend time, all printed under the grid by the filter.

## JSON fields

`du`, `au`: period. `pas`: step in days (0.05, the Boond minimum; `--steps 20`). `jours[]`: `date`, `heures_s` (Toggl seconds that day), `minutes` (Boond line → Toggl minutes, before rounding), `jours` (Boond line → days). `totaux`: line → days. `non_mappe_s`: Toggl `client / project` → seconds without a Boond line. `week_end_s`: date → seconds. `ecrases[]`: `date`, `ligne`, `minutes` dropped below one step.

## Rules for the result

- Present a Boond-style grid: one exact Boond line per row, one working day per column, a total column, a daily total row, percentages, and the exact Toggl total and gap per line. Use 0.05-day steps and the owner's numeric locale (decimal comma by default).
- **Every worked day totals exactly 1**, split in proportion to its Toggl minutes. The rounding gap of each line is carried to the next day where it appears, so the period totals stay as close as possible to Toggl. Do not re-round by hand: if the owner wants a different split, show the `Toggl` and `Écart` columns and let them choose.
- **Incomplete day** (⚠️, under 6 h of Toggl time on a 7 h basis, for example a single half day or too few entries): the day is still split over 1, but report it explicitly with its hours and ask the owner to complete Toggl before entering it in Boond.
- **Days without Toggl entries**, including days still to come, stay at 0. Say so, and never invent time.
- **Rounded to zero:** with 0.05-day steps this is rare (under about 10 min on a 7 h day). Show the minutes and the line; never move time between lines by hand.
- **Unmapped project:** show the Toggl project and ask for the exact Boond line. Then add it to `brain/.data/boond-mapping.json` and to the project page. In the saved JSON it appears as the line `(non mappé) <client / project>`: rename that line and re-render rather than spending another request, unless the owner asks for a fresh fetch. Same-day values are merged.

  ```bash
  jq --arg k "(non mappé) <client / project>" --arg v "<exact Boond line>" 'def mv: to_entries | map(if .key == $k then .key = $v else . end) | reduce .[] as $e ({}; .[$e.key] += $e.value); .jours[] |= (.jours |= mv | .minutes |= mv)' agents/timesheet.json > agents/timesheet-fixed.json
  ```
- **Weekend time** is not spread over working days: report it separately.
- **`Absence` line:** remind the owner to pick the absence type in Boond.
