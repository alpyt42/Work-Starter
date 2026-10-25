# Outils

Scripts réutilisables de l'espace de travail, rangés par domaine. Toutes les commandes se lancent depuis la racine de `Work/` avec `uv run`. Les scripts retrouvent la racine de `Work/` à partir de leur propre emplacement (variables `WORK_DIR` et `BRAIN_DIR` pour pointer ailleurs).

Configuration locale partagée, ignorée par Git, qui reste à la racine de ce dossier : `.env` (jetons éventuels, créé à partir de [.env.example](.env.example) ; aucun outil livré n'en a besoin pour l'instant). Ne jamais le lire, le copier ni le citer.

## Mémoire (`brain/`)

Les outils agissent sur le brain par défaut `brain/`, ou sur un autre brain avec `BRAIN_DIR` (`--brain` pour `action.py` et `decision.py`) ; `new-brain.py`, `brain-state.py` et `check-links.py` connaissent aussi les brains `brain-<nom>`.

| Commande | Rôle | Guide |
|---|---|---|
| `uv run tools/brain/new-brain.py <dossier> [--scope S] [--description D] [--remote MOTIF] [--email MOTIF] [--no-git]` | Crée un brain vierge (`brain` ou `brain-<nom>`) depuis `kit/brain/seed/` : refuse d'écraser un dossier existant, lance `git init` (sauf `--no-git`), sans commit ni remote. Les quatre options remplissent la frontière du brain dans `.data/brain.json` | en-tête du script |
| `uv run tools/brain/check-links.py [--allow-missing-local]` | Vérifie que tous les liens Markdown d'un brain pointent vers un fichier existant ; un lien vers un autre brain échoue même si la cible existe ; `--allow-missing-local` signale à part les cibles absentes de `artifacts/` et `repos/` ; les modèles de `skills/<nom>/assets/` ne sont pas contrôlés | en-tête du script |
| `uv run tools/brain/brain-state.py brains` | Liste les brains présents (le brain par défaut d'abord) avec leur `scope`, leur `description` et les transcriptions suivies | en-tête du script |
| `uv run tools/brain/brain-state.py transcripts [--new \| --where <fichier>]` | Fusionne l'état des transcriptions de tous les brains ; `--new` : celles qu'aucun brain ne suit ; `--where` : le brain qui possède un fichier | en-tête du script |
| `uv run tools/brain/action.py board` | Affiche les registres d'actions par projet dans le terminal (`--write` pour un aperçu Markdown, `--watch` pour le tenir à jour) | [action.md](brain/action.md) |
| `uv run tools/brain/action.py <commande>` | Crée, lit, modifie, complète l'historique et supprime les actions (agents et tasks-web), range les registres par statut (`sweep`) et archive les clôtures de plus de 30 jours (`archive`) | [action.md](brain/action.md) |
| `uv run tools/brain/decision.py <commande>` | Liste, propose, valide, refuse ou remplace les décisions des registres `state/decisions.md` | [decision.md](brain/decision.md) |

## Interface locale (`tasks-web/`)

| Commande | Rôle | Guide |
|---|---|---|
| `uv run tools/tasks-web/tasks-web.py [--port N] [--brain DOSSIER]` | Interface web locale des actions (Liste, Kanban, Outils, Git, Recherche) sur `http://127.0.0.1:8765/` ; un sélecteur en haut à gauche passe d'un brain de l'espace à l'autre sans redémarrer (`?brain=<nom>`, `GET /api/brains` ; `--brain` fixe le brain par défaut) ; l'onglet Outils lance des commandes prédéfinies (liens, brains, transcriptions, actions, dépôts) | [README.md](tasks-web/README.md) |
| `./tools/tasks-web/build-dock-app.sh` | Construit l'application macOS « Actions Brain » à poser dans le Dock (macOS) | [README.md](tasks-web/README.md) |
| `tools/tasks-web/launcher.sh` | Lanceur appelé par l'application : démarre le serveur si besoin et ouvre la page | [README.md](tasks-web/README.md) |

## Dépôts (`repos/`)

| Commande | Rôle | Guide |
|---|---|---|
| `uv run tools/repos/client-repos.py list [<client> \| repos/<client>/<dépôt>]` | Liste les dépôts du catalogue privé `brain/.data/client-repos.json` | en-tête du script |
| `uv run tools/repos/client-repos.py check [<client> \| repos/<client>/<dépôt>]` | Compare les clones présents au catalogue (URL `origin`) et montre l'auteur et la clé effectifs de chacun, sans réseau | en-tête du script |
| `uv run tools/repos/client-repos.py clone <client> [--identity CLÉ --author-name N --author-email E]` | Clone les dépôts d'un client ; simple `git clone`, auteur et clé viennent de `~/.gitconfig` ; les trois options forment un contournement ponctuel | en-tête du script |

## Machine (`machine/`)

Installation, mise à jour, hooks Git et contrôles de l'espace sur une machine : voir [machine/README.md](machine/README.md). L'identité Git et SSH par frontière de confiance est détaillée dans [machine/GIT-IDENTITY.md](machine/GIT-IDENTITY.md).

| Commande | Rôle | Guide |
|---|---|---|
| `tools/machine/install.sh [--brain URL] [--brain-perso URL\|new] [--no-bootstrap]` | Point d'entrée après le clone : clone ou crée `brain/` (et `brain-perso/`), puis lance `bootstrap.sh` | [README.md](machine/README.md) |
| `tools/machine/bootstrap.sh` | Prépare un checkout neuf : dossiers locaux, hooks Git de Work et de chaque brain, skills, liens, contrôles | [README.md](machine/README.md) |
| `tools/machine/update.sh` | Régénère skills et liens depuis la configuration, enregistre l'empreinte de la configuration et signale l'état Git de Work et de chaque brain | [README.md](machine/README.md) |
| `uv run tools/machine/work_config.py <commande>` | Configuration des skills (`check`, `list-brains`, `list-own`, `list-third-party`, `list-catalog`, `lock`, `adopt [--brain B]`, `stamp`, `status`) | [README.md](machine/README.md) |
| `uv run tools/machine/doctor.py` | Diagnostic local en lecture seule de l'espace, des brains et de leurs frontières | [README.md](machine/README.md) |
| `tools/machine/check-links.sh` | Contrôle la configuration, les liens et copies de skills et les liens Markdown de chaque brain | [README.md](machine/README.md) |
| `tools/machine/check-no-client.sh [--staged \| --worktree]` | Scan manuel facultatif des noms de clients et de personnes connus du brain par défaut | [README.md](machine/README.md) |
