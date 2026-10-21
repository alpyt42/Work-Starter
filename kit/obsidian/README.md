# Obsidian

Guide de réglage manuel d'Obsidian pour lire les brains et piloter les actions (`tasks.md`). Le starter ne gère pas `.obsidian/` : le dossier est ignoré par Git, local à chaque machine, et n'est donc pas sauvegardé. À refaire une fois par machine. Ne jamais versionner `workspace.json` ni `workspace-mobile.json` : ils listent les notes ouvertes.

## Coffre

Ouvrir `Work/` comme **seul** coffre. Ne jamais ouvrir un brain (`brain/`, `brain-*/`) comme coffre : les liens relatifs vers `../repos/` et `../artifacts/`, les chemins des modèles et le bouton de `tasks.md` partent de la racine de `Work/`. Les brains y apparaissent comme de simples dossiers.

## Plugins communautaires

Paramètres → Plugins communautaires → désactiver le mode restreint, puis installer et activer :

- **Tasks** (`obsidian-tasks-plugin`) : les requêtes de `tasks.md` ;
- **Meta Bind** (`obsidian-meta-bind-plugin`) : le bouton **Nouvelle action** ;
- **Templater** (`templater-obsidian`) : le formulaire derrière ce bouton, et le modèle d'une fiche personne ;
- **Obsidian Git** (`obsidian-git`), facultatif : un seul brain à la fois. Dans ses réglages, mettre le dossier de base (`basePath`) à celui du brain (par exemple `brain`) ; prudence suggérée : push désactivé, pas de pull au démarrage, pas de sauvegarde automatique après modification.

Ne pas activer l'exécution de JavaScript dans Tasks ni dans Meta Bind.

## Réglages à poser à la main

| Où | Réglage | Valeur |
| --- | --- | --- |
| Fichiers et liens | Utiliser les [[Wikiliens]] | désactivé (liens Markdown, qui gardent l'extension `.md`) |
| Fichiers et liens | Format des nouveaux liens | Chemin relatif au fichier |
| Fichiers et liens | Mettre à jour automatiquement les liens internes | activé (les liens suivent un déplacement ou un renommage) |
| Fichiers et liens | Fichiers exclus | `repos/`, `agents/`, `kit/brain/seed/` (hors recherche et graphe) |
| Fichiers et liens | Emplacement des nouvelles notes, facultatif | dans le dossier `brain/inbox` |
| Fichiers et liens | Emplacement des nouvelles pièces jointes, facultatif | dossier du fichier courant |
| Plugins de base → Modèles | Dossier des modèles | `kit/brain/templates` |
| Plugins de base → Modèles | Format de date | `YYYY-MM-DD` |
| Templater | Dossier des modèles | `kit/brain/templates` |
| Templater | Modèles de dossier (activés) | dossier `brain/people` → `kit/brain/templates/_PERSON-TEMPLATE.md` |
| Meta Bind | Dossiers exclus | `templates` |

Adapter `brain/inbox` et `brain/people` si le brain porte un autre nom. Les plugins de base Modèles, Signets et Propriétés doivent être activés. Le formulaire d'ajout d'action est lancé par le bouton de `tasks.md`, ou par `Cmd+P` → `nouvelle-action` → **Templater: Insert** ; ne pas l'insérer avec le plugin Modèles de base, qui recopierait son code.

### Statuts des actions (Tasks)

Paramètres → Tasks → Statuts personnalisés. Les registres utilisent cinq états, dont trois à ajouter :

| Symbole | Nom | Statut suivant | Type |
| --- | --- | --- | --- |
| `/` | In Progress (en cours) | `x` | IN_PROGRESS |
| `w` | En attente | `x` | TODO |
| `-` | Cancelled (annulée) | espace | CANCELLED |

`[ ]` à faire et `[x]` faite sont les statuts de base de Tasks. Le nom du statut `w` doit contenir « attente » : les requêtes de `tasks.md` s'appuient dessus pour séparer les actions en attente des actions à faire.

### Extrait CSS

Copier `kit/obsidian/tasks-board.css` dans `.obsidian/snippets/` (à la racine de `Work/`), puis Paramètres → Apparence → Extraits CSS → activer `tasks-board`. Il dessine les états `[/]` et `[w]`, le kanban et la mise en page de `tasks.md`.

## Signets (suggestion)

Plugin de base Signets : épingler `<brain>/tasks.md` et `<brain>/inbox.md`, un groupe par brain si plusieurs sont présents.

## Graphe (facultatif)

Un groupe de couleur par brain, avec la requête `path:<brain>/`.
