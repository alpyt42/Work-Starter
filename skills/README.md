# skills/

Les skills maison, versionnés ici et découverts par les agents via des liens : `.claude/skills/` pour Claude, `.agents/skills/` pour Codex. Chaque dossier contient son `SKILL.md`, qui décrit quand et comment l'utiliser. Les skills tiers ne sont pas ici : ils s'installent dans `.agents/skills/` (ignoré) depuis `skills-lock.json`.

| Skill | Rôle |
|---|---|
| `brain-clean` | Audit et réconciliation du brain (kanban, sources, liens, Git) avec arbitrage humain. |
| `cr-reunion` | Transcripts de réunion → CR Markdown sourcés dans le brain, après confirmation du rattachement. |
| `veille-messages` | Tri des mails et messages d'équipe, validé avant mise à jour de la mémoire. |
| `timesheet` | Proposition de feuille de temps Toggl → Boond, en lecture seule. |
| `brand-deck` | Decks PowerPoint à partir d'un template de marque et du moteur `deck-kit`. |
| `new-project` | Cadrage et création d'un nouveau dépôt avec garde-fous agents ; copié, jamais lié. |

Leurs états et réglages privés (curseurs, chemins d'entrée, mappings) vivent dans `brain/.data/`.
