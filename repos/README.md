# repos/ — dépôts de code locaux

Les clones de code vivent ici. Chaque clone est un dépôt Git indépendant ; son contenu est ignoré par le dépôt `Work`. Seuls ce README et `workspaces/README.md` sont suivis par `Work`.

## Organisation

- `<client-ou-sujet>/<depot>/` : travail principal, avec un dossier par client ou sujet.
- `personal/` : projets personnels.
- `sandbox/` : expériences jetables.
- `workspaces/` : fichiers `.code-workspace` locaux ; voir `workspaces/README.md`.

Garder les clones peu profonds et des noms descriptifs en lowercase-kebab. Un clone peut porter son propre `AGENTS.md` et son pointeur `CLAUDE.md` ; les lire avant de le modifier.

## Dépôts clients

Le catalogue privé `brain/.data/client-repos.json` contient leurs URL. Utiliser `uv run tools/client-repos.py check` pour contrôler les clones présents et `uv run tools/client-repos.py clone <client>` pour les recréer. Les URL, l'inventaire, les faits de mission et les décisions propres à un client restent dans le brain privé.

Avant une opération Git distante, vérifier l'identité Git et SSH selon `AGENTS.md` et respecter les décisions du client consignées dans le brain. Chaque clone suit aussi les règles de son propre dépôt.

## Frontières

Le code et la documentation technique durables restent dans leur dépôt. Le brain conserve le contexte et les liens vers les dépôts ; `agents/` reçoit le travail jetable et `artifacts/` les livrables destinés aux humains. Un dépôt partagé ne doit pas contenir de chemin machine ni de référence à un dossier privé local.
