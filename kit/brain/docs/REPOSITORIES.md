# Dépôts client à cloner

Le catalogue privé `.data/client-repos.json` versionne **uniquement les chemins locaux et les URLs `origin`** des dépôts client. Il ne fixe ni branche ni commit. Les URLs client ne vont jamais dans un dépôt d'outillage personnel ou public : seulement ici, dans le brain privé.

Format d'une entrée : `{"path": "repos/<client>/<repo>", "url": "<url-git>"}` dans la liste `repositories`. L'état réel du catalogue reste exclusivement dans `.data/client-repos.json`.

Si l'espace de travail fournit `tools/repos/client-repos.py`, il lit ce catalogue :

```bash
uv run tools/repos/client-repos.py list                 # tous les chemins et URLs
uv run tools/repos/client-repos.py check                # origin + auteur et clé appliqués, sans réseau
uv run tools/repos/client-repos.py clone <client>       # simple git clone, identité héritée de ~/.gitconfig
```

Avant le premier clone d'un client, enregistrer sa clé publique et vérifier la clé d'hôte du serveur (voir [`GIT.md`](GIT.md)). Si un dépôt change d'URL, vérifier le nouveau remote avec le client, corriger le catalogue, puis relancer `check`.
