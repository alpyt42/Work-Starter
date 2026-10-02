# Option — zone gatée pour du code client (Niveau 3)

> Option pour un nouveau périmètre client, à proposer une fois et à installer seulement après accord. Respecter les décisions déjà enregistrées dans la mémoire, sans relancer une option refusée. Doctrine en une ligne : **lecture libre · toute écriture qui laisse une trace chez le client passe par la personne, par action · rien du monde local ne part chez le client.**
>
> Ce n'est pas de la défiance envers l'agent : c'est qu'un « vas-y » donné une fois ne doit pas couvrir la fois suivante, et qu'une règle écrite ne vaut rien sans le mécanisme qui la fait respecter. Trois mécanismes se complètent ; aucun ne suffit seul.

## Les trois mécanismes

| Mécanisme | Ce qu'il fait | Où il vit |
|---|---|---|
| **Hook Claude Code** (`gate-zone.py`) | Avant chaque commande shell de l'agent, si elle opère dans la zone gatée : `git commit` / `push` / `rebase` / modif des remotes / `gh` → **demande un GO** ; `--no-verify`, reconfigurer les hooks ou l'identité → **refusé** ; tout le reste (lecture, `status`, `diff`, `log`, edits) → libre | `<racine>/.claude/hooks/gate-zone.py` + `<racine>/.claude/settings.json` |
| **Hooks git** (`githooks/`) | Valent pour **tout le monde, la personne incluse** : identité git = celle attendue chez le client · pas de commit direct sur la branche par défaut · scan de secrets · aucune référence au monde local · aucune signature d'IA | `<zone>/.githooks/` (chaque clone : `git config core.hooksPath ../.githooks` ou copie dans `.git/hooks/`) |
| **`AGENTS.md` de zone** | Les règles humaines, auto-chargées quand l'agent touche au dossier | `<zone>/AGENTS.md` |

## Installation (à dérouler avec la personne)

1. **Choisir la zone** : un dossier de `repos/` qui ne contiendra QUE des clones client, ex. `repos/<client>/clones/` ou `repos/<client>-github/`. Les repos internes du même client (le code qu'on écrit soi-même, chez soi) vivent **à côté**, pas dedans — pas de friction inutile.
2. **Le hook Claude Code** : copier `gate-zone.py` dans `<racine>/.claude/hooks/`, remplacer `GATE_PATH` par le chemin de la zone **relatif à la racine** (ex. `repos/acme/clones`), puis fusionner `settings.json` dans `<racine>/.claude/settings.json` (remplacer `{{ABS_HOOK_PATH}}` par le chemin absolu du script). Redémarrer Claude Code.
3. **Les hooks git** : copier `githooks/` dans `<zone>/.githooks/`, rendre exécutable (`chmod +x`), remplir les deux variables en tête de `pre-commit` (email attendu, motifs locaux à interdire). Dans chaque clone : `git config core.hooksPath ../.githooks`. Installer `gitleaks` (scan de secrets) — sans lui, le pre-commit **refuse** de commiter, c'est voulu.
4. **L'identité git** : un `~/.gitconfig-<client>` avec le `user.email` client, inclus conditionnellement depuis `~/.gitconfig` (`[includeIf "gitdir:<zone>/"] path = ~/.gitconfig-<client>`). C'est la personne qui le fait — un agent ne touche pas aux dotfiles.
5. **L'`AGENTS.md` de zone** : copier `AGENTS.md` dans `<zone>/`, remplacer les placeholders, ajuster les règles à la mission. Ajouter le bloc `sensitivity:3` déjà prévu dans `<racine>/AGENTS.md` et `repos/README.md` (il y est si le Niveau 3 a été retenu à la génération).
6. **La checklist de test à blanc** (ci-dessous). Ne pas la sauter : un gate non testé est un gate qu'on croit avoir.

## Checklist au premier clone
- [ ] `git config user.email` DANS le clone retourne bien l'identité client (l'`includeIf` a pris)
- [ ] Un commit test sur la branche par défaut est **refusé**
- [ ] Un commit test contenant un chemin local (`~/`, `/Users/`) est **refusé**
- [ ] Un commit test contenant un faux secret (ex. une chaîne `AKIA…` de 20 caractères) est **refusé** par gitleaks
- [ ] Un commit test avec un trailer `Co-Authored-By: Claude` est **refusé**
- [ ] Le hook Claude Code déclenche bien une demande de GO sur un vrai `git commit` en session
- [ ] `git commit --no-verify` est **refusé** à l'agent
- [ ] En touchant un fichier du clone, l'agent charge bien l'`AGENTS.md` de zone (lui demander « quelles règles s'appliquent ici ? »)

## Lever un gate
Un gate se lève en éditant ses fichiers — par la personne, ou par un agent **sur son GO explicite en séance**. Toute levée ou modification s'inscrit datée dans une note de la mémoire (le journal des gates du projet client), pour qu'on sache dans six mois pourquoi telle règle a sauté.
