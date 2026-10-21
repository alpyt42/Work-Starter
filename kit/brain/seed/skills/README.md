# skills/

Skills **privés** de ce brain : des procédures d'agent qui touchent à ses données (comptes rendus, tri, outils propres à l'employeur ou à un client). Elles vivent ici, dans le dépôt privé du brain, jamais dans le starter public. Les états qu'elles produisent vont dans le [`.data/`](../.data/README.md) de ce même brain.

Un skill = un dossier `skills/<nom>/` :

- `SKILL.md` — nom, description (quand l'utiliser) et procédure.
- `scripts/`, `references/`, `assets/` — facultatifs : code, documentation à ouvrir au bon moment, fichiers modèles.
- `.install-as-copy` — fichier marqueur à ajouter pour un skill qui doit être **copié** chez l'agent plutôt que lié à ce dossier.

Les skills de tiers (catalogue public) ne sont pas copiés ici : ils sont listés dans [`.data/work-config.json`](../.data/work-config.json) (`skills.thirdParty`) et installés par `tools/machine/update.sh` ; `skills.disabled` liste ceux qu'on désactive. Pour reprendre dans ce brain un skill déjà présent dans l'espace : `uv run tools/machine/work_config.py adopt --brain <brain>`.
