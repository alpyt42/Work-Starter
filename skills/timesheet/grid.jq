# Render `tools/toggl.py boond --json` as a Boond-style Markdown grid (French decimal comma).
# Totals are recomputed from the days shown, so a subset of days can be rendered:
#   jq -rf skills/timesheet/grid.jq agents/timesheet.json
#   jq -rf skills/timesheet/grid.jq --arg from 2026-09-07 --arg to 2026-09-11 agents/timesheet.json
# "Toggl" is the exact share of each day's minutes, before rounding; "Écart" is proposed minus Toggl.
# A working day is 7 h; a day more than 1 h short is flagged ⚠️ (--arg base 7 --arg tol 1 to change).
def r2: . * 100 | round / 100;
def fr: r2 | (if . == floor then floor else . end) | tostring | sub("\\."; ",");
def sfr: r2 | if . > 0 then "+" + fr elif . == 0 then "0" else fr end;
def dm: .[8:10] + "/" + .[5:7];
def h: (. / 360 | round) / 10 | fr;
($ARGS.named.from // "0000") as $a | ($ARGS.named.to // "9999") as $b
| ($ARGS.named.base // "7" | tonumber) as $base | ($ARGS.named.tol // "1" | tonumber) as $tol
| (($base - $tol) * 3600) as $min
| [.jours[] | select(.date >= $a and .date <= $b)] as $d
| (reduce ($d[].jours | to_entries[]) as $e ({}; .[$e.key] += $e.value)) as $tot
| (reduce ($d[] | (.minutes // {}) as $m | ([$m[]] | add // 0) as $s | $m | to_entries[] | {key, value: (.value / $s)}) as $e
    ({}; .[$e.key] += $e.value)) as $exact
| ([$tot[]] | add // 0) as $t
| (.ecrases | map(select(.date >= $a and .date <= $b))) as $x
| (.week_end_s | with_entries(select(.key >= $a and .key <= $b))) as $w
| "| Ligne Boond | " + ([$d[].date | dm] | join(" | ")) + " | Total | % | Toggl | Écart |",
  "|---|" + ([$d[] | "---"] | join("|")) + "|---|---|---|---|",
  (($tot | keys) + ($exact | keys) | unique | map({key: ., value: ($tot[.] // 0)}) | sort_by(-.value)[] as $l
   | ($exact[$l.key] // 0) as $ex
   | "| " + $l.key + " | " + ([$d[] | .jours[$l.key] | if . == null then "" else fr end] | join(" | "))
     + " | **" + ($l.value | fr) + "** | " + (if $t > 0 then (1000 * $l.value / $t | round) / 10 | fr else "0" end) + " % | "
     + ($ex | fr) + " | " + ($l.value - $ex | sfr) + " |"),
  "| **Total jour** | " + ([$d[] | (([.jours[]] | add // 0) | fr) + (if .heures_s < $min then " ⚠️" else "" end)] | join(" | ")) + " | **" + ($t | fr) + "** | 100 % | "
     + ([$exact[]] | add // 0 | fr) + " | |",
  "",
  "Heures Toggl : " + ([$d[] | (.date | dm) + " " + (.heures_s | h) + " h"] | join(" · ")),
  "⚠️ Journées incomplètes (moins de " + ($base - $tol | fr) + " h sur une base de " + ($base | fr) + " h) : "
    + ([$d[] | select(.heures_s < $min) | (.date | dm) + " " + (.heures_s | h) + " h"
        + (if .heures_s == 0 then " (aucune entrée, laissé à 0)" else " (réparti sur 1 j, écart " + (.heures_s / 3600 - $base | sfr) + " h)" end)]
       | join(" · ") | if . == "" then "aucune" else . end),
  "Écrasés à 0 : " + ([$x[] | (.date | dm) + " " + (.minutes | tostring) + " min " + .ligne] | join(" · ") | if . == "" then "aucun" else . end),
  "Non mappés (toute la période) : " + ([.non_mappe_s | to_entries[] | .key + " " + (.value | h) + " h"] | join(" · ") | if . == "" then "aucun" else . end),
  "Week-end : " + ([$w | to_entries[] | (.key | dm) + " " + (.value | h) + " h"] | join(" · ") | if . == "" then "aucun" else . end)
