# tools/

Scripts réutilisables appelés par les skills et par toi, lancés avec `uv run tools/<script>` depuis la racine `Work/`. Ils trouvent `brain/` à côté de `tools/` ; `BRAIN_DIR` force un autre brain (par exemple `brain-perso/`). Leurs données privées vivent dans `brain/.data/`, jamais ici.

| Fichier | Rôle |
|---|---|
| `check-links.py` | Vérifie que tous les liens Markdown du brain pointent vers un fichier existant. |
| `brain-state.py` | Fusionne les états des skills de tous les brains (`brain/`, `brain-perso/`, `brain-*/`) : `transcripts --new` liste ce qu'aucun brain ne suit, `--where` dit quel brain possède un transcript. |
| `client-repos.py` | Liste, vérifie (`check`) ou clone les dépôts client du catalogue privé `brain/.data/client-repos.json`. |
| `toggl.py` | Lit Toggl en lecture seule et propose une feuille de temps Boond (skill `timesheet`). |
| `toggl_projects.py` | Aligne les projets Toggl sur les lignes Boond ; `--apply` seulement sur GO explicite. |
| `.env.example` | Noms des variables attendues. Le vrai `tools/.env` est ignoré par Git et ne se lit jamais dans une session agent. |
