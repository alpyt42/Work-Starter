# .claude/

Configuration Claude Code du projet `Work/`.

- `settings.json` — réglages partagés et suivis par Git (permissions, hooks) ; vide dans le starter. Les réglages personnels vont dans `settings.local.json`, ignoré.
- `skills/` — entièrement généré et ignoré par Git : liens vers les skills des brains (`<brain>/skills/<nom>/`) et vers les skills tiers installés dans `../.agents/skills/`, copies des skills marqués `.install-as-copy`. Le starter ne livre aucun skill. Régénérer avec `tools/machine/update.sh` ; ne rien y éditer.
