---
cssclasses:
  - tasks-dashboard
---

# Actions

Les prochaines actions, la liste par projet et le kanban, au même endroit. Tant que le propriétaire n'est pas renseigné dans le starter, les vues montrent tous les responsables.

> [!task-nav]
> [Pilotage](#pilotage) · [Liste par projet](#liste-par-projet) · [Kanban](#kanban) · [Historique](#historique) · [Inbox](inbox.md)

```meta-bind-button
label: Nouvelle action
icon: plus
style: primary
tooltip: Ajouter une tâche dans le registre du projet choisi
actions:
  - type: runTemplaterFile
    templateFile: kit/brain/templates/templater/nouvelle-action.md
```

Choisis le projet, puis renseigne l'action. Le formulaire la range au bon endroit avec son ID, sa priorité et son échéance.

> [!info]- Dans le navigateur
> Depuis la racine de l'espace de travail, lance `uv run tools/tasks-web/tasks-web.py`, puis ouvre `http://127.0.0.1:8765/`. Cette [interface locale](../tools/tasks-web/README.md) lit et modifie les mêmes registres.

## Pilotage

> [!task-focus]+ Aujourd'hui
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> status.name does not include attente
> (scheduled before tomorrow) OR (due before tomorrow)
> sort by priority
> sort by due
> sort by description
> ```

> Choisis jusqu'à trois actions avec le crayon 📝 : **Scheduled / Planifiée = aujourd'hui**. Les échéances du jour, les retards et les actions planifiées non terminées remontent ici.

> [!task-grid]
> > [!task-active]+ En cours
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is IN_PROGRESS
> > sort by priority
> > sort by due
> > sort by description
> > ```
>
> > [!task-next]+ À lancer
> > Les 8 premières par priorité, puis échéance. La liste complète reste dans les projets.
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is TODO
> > status.name does not include attente
> > (no scheduled date) OR (scheduled after today)
> > (no due date) OR (due after today)
> > (no start date) OR (starts before tomorrow)
> > sort by priority
> > sort by due
> > sort by description
> > limit 8
> > ```

> [!task-wait]+ À relancer
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> status.name includes attente
> sort by due
> sort by priority
> sort by description
> ```

> [!task-calendar]- Échéances · 7 prochains jours
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> due after today
> due on or before in 7 days
> sort by due
> sort by priority
> sort by description
> ```

## Liste par projet

> [!task-project]- [Setup du système](projects/internal/setup/setup.md)
> ```tasks
> path includes {{BRAIN}}/projects/internal/setup/state/actions.md
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> sort by status.type
> sort by status.name reverse
> sort by priority
> sort by due
> sort by description
> ```

> [!task-project]- Autres projets
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> path does not include {{BRAIN}}/projects/internal/setup/state/actions.md
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> sort by path
> sort by status.type
> sort by status.name reverse
> sort by priority
> sort by due
> sort by description
> ```

Ajoute un encadré dédié quand un projet doit rester visible, puis exclus son registre d'« Autres projets ».

## Kanban

Pour déplacer une action, fais un clic droit sur sa case ou utilise le crayon 📝. Les colonnes lisent directement les registres.

> [!board]
> > [!column] À faire
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is TODO
> > status.name does not include attente
> > sort by priority
> > sort by due
> > short mode
> > ```
>
> > [!column] En cours
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.type is IN_PROGRESS
> > sort by priority
> > sort by due
> > short mode
> > ```
>
> > [!column] En attente
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > status.name includes attente
> > sort by due
> > sort by priority
> > short mode
> > ```
>
> > [!column] Terminées récemment
> > ```tasks
> > path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions\.md$/
> > (status.type is DONE) OR (status.type is CANCELLED)
> > (has done date) OR (has cancelled date)
> > sort by done reverse
> > sort by cancelled reverse
> > limit 10
> > short mode
> > ```

## Historique

> [!task-history]- 15 dernières clôtures
> ```tasks
> path regex matches /^{{BRAIN}}\/projects\/.*\/state\/actions(-archive-\d{4})?\.md$/
> (status.type is DONE) OR (status.type is CANCELLED)
> (has done date) OR (has cancelled date)
> sort by done reverse
> sort by cancelled reverse
> limit 15
> ```

> [!help]- Les gestes utiles
> **Terminer** : cocher la case ; la date de fin est ajoutée au registre.
>
> **Commencer ou mettre en attente** : clic droit sur la case, ou crayon 📝, puis choisir l'état.
>
> **Prioriser** : choisir une priorité avec le crayon 📝. **Planifier** indique quand travailler ; **Due / Échéance** indique quand livrer.
>
> **Capturer sans classer** : écrire dans l'[Inbox](inbox.md), puis trier plus tard.
>
> Les dates simples sont lues par Tasks. Les formulations vagues restent dans le registre. Voir les [conventions](../kit/brain/docs/CONVENTIONS.md).
