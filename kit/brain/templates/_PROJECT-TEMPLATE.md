# Project: (Nom)

> À copier vers `projects/internal/<name>/<name>.md`. Pour un client ou une mission client, utiliser plutôt `kit/brain/templates/_CLIENT-TEMPLATE.md` et `_MISSION-TEMPLATE.md`. C'est un INDEX : il résume, pointe vers le repo et les notes, tient la timeline.
>
> Les `../../../` des liens valent pour `projects/<axe>/<name>/`. En cas de doute, lancer `uv run tools/brain/check-links.py` depuis la racine de l'espace de travail.

- **Status:** active | paused | done
- **Goal:** (une phrase — à quoi ressemble « terminé »)
- **Suivi du temps:** (référence confirmée par le propriétaire, jamais devinée ; facultatif, à retirer si inutile)
- **Repo:** `../../../repos/(dossier)` ← le territoire que ce projet indexe (vide si pas de code)
- **Stakeholders:** [nom-personne](../../../people/nom-personne.md)
- **Tableau :** [tasks](../../../tasks.md)

## Context
(contexte et contraintes — le pourquoi, pas le comment)

## Notes
- [YYYY-MM-DD-sujet](notes/YYYY-MM-DD-sujet.md) — (de quoi il s'agit ; notes de travail datées dans `notes/`, à côté de `state/`)
- Handoffs : `handoffs/`

## Registres
> Créer `state/actions.md` à partir de [`_ACTIONS-TEMPLATE.md`](../../../../kit/brain/templates/_ACTIONS-TEMPLATE.md), en adaptant ses liens à ce projet interne ; `state/decisions.md` (depuis `_DECISIONS-TEMPLATE.md`) et `state/glossary.md` au besoin. Ces registres sont le seul endroit où écrire actions et décisions ; ne pas les recopier dans cette fiche.
- [Registre des actions](state/actions.md)
- [Décisions](state/decisions.md) — proposées, validées, refusées, remplacées
- [Glossaire](state/glossary.md) — facultatif : termes, sigles et erreurs de transcription du projet

## Timeline
> Un item par jour ou par session, une ligne chacun — de quoi reconstituer *comment on en est arrivé là* sans relire le détail. Seul le mois en cours reste ici : dès qu'il écrit un nouveau mois, l'agent déplace sans demander les entrées antérieures, inchangées, dans `journal/YYYY-MM.md` (convention du brain) et liste les mois archivés ci-dessous (ligne à retirer tant que rien n'est archivé).
Mois précédents : [YYYY-MM](journal/YYYY-MM.md)
- (date) — création de la fiche
