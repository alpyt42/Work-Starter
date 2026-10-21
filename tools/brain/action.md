# Outil des actions

`tools/brain/action.py` est le seul outil qui écrit dans les registres d'actions (`projects/**/state/actions.md`). Les agents l'appellent en ligne de commande. L'interface locale `tasks-web` le lance pour chacune de ses écritures et importe son code pour lire. Une action s'écrit donc toujours de la même façon :

```markdown
- [ ] **DEM-101** — Propriétaire — Intitulé ⏫ ➕ 2026-10-13 📅 2026-10-20
    - source: [CR du 13/10](../sources/2026-10/2026-10-13-cr-demo.md)
    - créée : 2026-10-13 14:32
    - mise à jour : 2026-10-14 09:05
    - 14/10 : entrée d'historique
```

- **Création** : `➕ AAAA-MM-JJ` sur la ligne (lu par le plugin Tasks, qui ne connaît que les dates) et `créée : AAAA-MM-JJ HH:MM` en sous-puce (heure de Paris, à la minute, sans secondes). Posées une fois, à la création.
- **Mise à jour** : `mise à jour : AAAA-MM-JJ HH:MM`, réécrite par chaque modification faite avec l'outil (champs, statut, ajout ou suppression d'historique).
- **Échéance** : `📅 AAAA-MM-JJ` sur la ligne quand elle est connue ; une échéance nuancée (« avant… ») va en sous-puce `échéance:`.
- **Groupe (lot)** : étiquette facultative, pas une tâche parente. Au plus un tag `#lot/<slug>` à la fin de l'intitulé, juste avant les emojis Tasks : `- [ ] **DEM-097** — Propriétaire — Planifier l'atelier #lot/atelier-demo ➕ 2026-10-12 📅 2026-10-20`. Slug `[a-z0-9]+(-[a-z0-9]+)*`, 40 caractères au plus ; l'interface l'affiche « Atelier demo ». Une action sans tag reste valide et n'est jamais modifiée par la réécriture d'un autre champ. Le tag s'écrit avec `--group`, pas à la main dans `--title`.
- Les sous-puces `source`, `créée` et `mise à jour` ne se suppriment pas avec `history remove`. Les actions antérieures au 2026-10-13 n'ont pas ces dates : elles ne sont pas inventées.

## Commandes

Depuis la racine de Work ; la sortie est du JSON (codes de sortie : 0 fait, 2 requête invalide, 3 introuvable, 4 conflit).

```sh
uv run tools/brain/action.py list --project acme/demo --table
uv run tools/brain/action.py board                    # vue complète par projet (terminal)
uv run tools/brain/action.py board --write --watch    # agents/tasks-board.md tenu à jour (aperçu VS Code)
uv run tools/brain/action.py show DEM-099
uv run tools/brain/action.py create --project acme/demo --title "Relancer le contact" \
    --owner Propriétaire --source "[CR du 13/10](../sources/2026-10/2026-10-13-cr-demo.md)" --due 2026-10-20
uv run tools/brain/action.py update DEM-099 --state done --closed-on 2026-10-14
uv run tools/brain/action.py update DEM-099 --group atelier-demo   # --group "" retire le groupe
uv run tools/brain/action.py history add DEM-099 --text "relancé par mail" --date 2026-10-14
uv run tools/brain/action.py history edit DEM-099 --index 3 --text "relancé par mail et par chat"
uv run tools/brain/action.py history remove DEM-099 --index 3
uv run tools/brain/action.py move DEM-099 --to acme/autre-mission
uv run tools/brain/action.py check                    # format des registres (code 1 si erreur)
uv run tools/brain/action.py delete DEM-099
uv run tools/brain/action.py sweep --write            # range chaque action sous la section de son état
uv run tools/brain/action.py archive --write          # archive les clôtures de plus de 30 jours
uv run tools/brain/action.py sweep --archive --write  # les deux, rangement d'abord
```

- `--project` accepte le chemin du registre, le dossier du projet, `client/mission`, le nom d'un projet interne ou le libellé du tableau (`acme / demo`).
- `create` : ID suivant du plus grand trouvé dans tout le dossier du client ou du projet, sources comprises ; ajout à la fin de `Ouvertes` ; `--source` obligatoire ; options `--state` (todo, en-cours, en-attente), `--priority` (haute, moyenne, basse), `--due`, `--scheduled`, `--due-note`, `--group` (slug du groupe), `--prefix` (registre encore vide).
- `update` : seuls les champs donnés changent ; une valeur vide efface `--due`, `--scheduled` ou `--group` (option absente : groupe inchangé). Un changement d'état range l'action dans sa section ; une clôture prend `✅`/`❌` à la date du jour, ou `--closed-on` pour la date de la preuve ; une réouverture retire la date de clôture.
- `--group` : slug validé (message `Groupe invalide…`, code 2). Un `--title` qui se termine lui-même par un tag `#lot/<slug>` valide est refusé (code 2) : passer le groupe par `--group`. Un tag invalide, en double ou placé au milieu du titre reste dans l'intitulé tel quel (rien n'est perdu à la réécriture) et `check` le signale. `list --table` ajoute `[lot: slug]` ; le JSON de `list` et `show` porte `group`, et `title`/`raw_title` sont sans le tag. `sweep`, `archive`, `move`, `delete` et `history` déplacent la ligne telle quelle et gardent le tag.
- `history add` : sous-puce `JJ/MM : texte` à la fin du bloc (`--date` pour la date de l'événement). `history edit --index N --text T` réécrit une entrée en gardant sa date (ou `--date`) et ses sous-lignes. `history remove --index N` la supprime. Le rang N est donné par `show`.
- `move --to P` : déplace l'action et son bloc vers un autre registre du même client ou projet interne (l'ID ne change pas, les liens relatifs sont réécrits, une entrée « déplacée depuis … » est ajoutée).
- `check [--register R]` : erreurs bloquantes (ligne d'action mal formée, ID en double dans tout le client archives comprises, date invalide, action ouverte avec une date de clôture, marque de clôture incohérente) et avertissements (close sans date, pas de sous-puce source, slug de groupe invalide, plusieurs tags `#lot/`, tag qui n'est pas en fin d'intitulé).
- Toute écriture accepte `--dry-run`, et les verrous `--expect-version` (ligne) et `--expect-details-version` (bloc) utilisés par l'interface.
- `--brain CHEMIN` ou `BRAIN_DIR` pour un autre brain ; `ACTION_NOW="AAAA-MM-JJ HH:MM"` fige l'horloge (tests).

## Tableau (`board`)

Vue complète, en lecture seule, de tous les registres par projet : À faire du propriétaire (`BRAIN_OWNER` ou `owner` de `brain/.data/doctor.json`), En cours et En attente de tous, triés par ID, puis les 15 clôtures les plus récentes. Chaque ligne renvoie à sa ligne du registre. `--write [CHEMIN]` écrit aussi le tableau (défaut `agents/tasks-board.md`) ; `--watch` le réécrit quand un registre change (tâche VS Code du brain, au lancement du dossier).

## Rangement (`sweep`)

| État | Section |
|---|---|
| `[ ]` `[/]` `[w]` | `## Ouvertes` (en fin de section) |
| `[x]` | `## Terminées` (clôture la plus récente d'abord) |
| `[-]` | `## Annulées` (idem) |

Cas couverts : une action cochée dans le tableau Tasks d'Obsidian (elle reste dans Ouvertes), une action rouverte, une action rangée dans la mauvaise section close. Le rangement ne crée ni date, ni état, ni ID : une action close sans `✅`/`❌` est déplacée et signalée. Il laisse en place, avec un avertissement, un état inconnu ou une section inconnue ou absente.

## Archive (`archive`)

Une action `[x]` ou `[-]` datée, sous `## Terminées` ou `## Annulées`, dont la clôture est strictement antérieure à `aujourd'hui - --days` (30 par défaut), passe avec ses sous-puces dans `state/actions-archive-AAAA.md` (année de clôture), section de son état, clôture la plus récente d'abord. Son ID reste réservé. Un ID déjà archivé arrête ce registre sans rien écrire.

Options communes à `sweep` et `archive` : `--dry-run` (défaut) / `--write` / `--check` (code 1 si quelque chose est à déplacer), `--register CHEMIN` (répétable), `--days N`, `--today AAAA-MM-JJ` (ou `ARCHIVE_TODAY`), `--quiet`.

## Hooks Git

Versionnés dans `tools/machine/hooks/` et installés par `tools/machine/bootstrap.sh` dans chaque brain présent ; ils valident sans jamais écrire :

- **brain, `pre-commit`** : sur une copie exacte de l'index (ce que le commit contiendra, pas le dossier de travail) : actions mal rangées (`sweep --check`) et format des registres stagés (`check`), liens Markdown morts ou pointant vers un autre brain si un `.md` est stagé, noms de clients d'un autre brain (`check-no-client.py --brain … --staged`, hors liste `allow` du `.data/brain.json`) ; puis secrets dans les ajouts stagés.
- **Work, `pre-commit`** : secrets dans les ajouts stagés.
- **Work et brain, `commit-msg`** : sujet Conventional Commits (types de `kit/brain/docs/GIT.md`, minuscule, sans point final, 100 caractères au plus, avertissement au-delà de 72) et aucune mention d'IA.
- **Secrets** (`check-staged-secrets.py`) : noms de fichiers d'identifiants et lignes ajoutées qui ressemblent à une clé ou un jeton ; valeurs jamais affichées ; `secret-scan: ignore` sur la ligne neutralise un faux positif.

## Quand l'agent l'utilise

- Pour créer, modifier, compléter l'historique ou supprimer une action : toujours cet outil, jamais une édition à la main du registre.
- Quand le doctor de `brain-clean` signale des actions à archiver, ou au début d'un nouveau mois : `archive --write`, sans demander si les conventions du brain le prévoient. Après une passe sur les registres : `sweep --write`.

## Garanties

- Écritures atomiques ; refus si le registre a changé entre la lecture et l'écriture ; l'archive est écrite avant le registre et restaurée si l'écriture du registre échoue.
- Fins de ligne et retour final conservés ; idempotent pour `sweep` et `archive`.
- Les liens symboliques et tout ce qui sort du brain sont ignorés.
