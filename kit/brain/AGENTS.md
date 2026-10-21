# AGENTS.md — Mémoire brain

La mémoire est l'index du travail de son propriétaire ; les repos sont le territoire. Markdown pur, liens relatifs avec extension `.md`, dépôt Git privé. Répondre dans la langue du propriétaire ; conserver en anglais les noms de dossiers et mots-clés structurels. Ces conventions valent pour tous les brains de l'espace (`brain/`, `brain-perso/`, `brain-*/`) et sont gérées par Work dans `kit/brain/` ; le `AGENTS.md` de chaque brain ne garde que ses règles propres. Lire aussi le `AGENTS.md` à la racine de l'espace avant toute modification. Sauf mention contraire, les chemins ci-dessous partent de la racine du brain.

## S'orienter avant d'écrire

- Pour les tâches : les registres `state/actions.md` font foi ; `tasks.md` réunit le pilotage quotidien, la liste par projet et le kanban, et ne se lit pas comme un fichier de données. Hors Obsidian : `uv run tools/brain/action.py board` en terminal ou `uv run tools/tasks-web/tasks-web.py` pour l'interface locale.
- Pour un client : `projects/clients/<client>/<client>.md`, puis `missions/<mission>/<mission>.md` et seulement les fichiers `state/`, `workstreams/` ou `sources/` utiles. Pour l'outillage du brain : `projects/internal/setup/setup.md`. Pour une personne : `people/<prenom-nom>.md`.
- Avant de rédiger sous le nom du propriétaire, lire la section Voix de `me/about-me.md`, choisir son registre, livrer un brouillon en code block et ne jamais envoyer sans demande explicite.

## Ce qui fait foi

- **Fait historique :** la source datée (CR, mail, message d'équipe) dit ce qui a été dit ou transmis ; elle ne donne pas à elle seule le statut actuel.
- **Action :** `state/actions.md` est le seul endroit où une action s'écrit : ID, responsable, échéance, statut, source et historique. La ligne garde ID, responsable, intitulé et métadonnées Tasks ; les nuances, la source, les horodatages `créée` et `mise à jour` et l'historique vont en sous-puces. Toute écriture d'action passe par `uv run tools/brain/action.py`. États : `[ ]` à faire, `[/]` en cours, `[w]` en attente, `[x]` faite, `[-]` annulée. Une preuve datée est nécessaire pour fermer une action ; une case cochée par le propriétaire dans le tableau en est une. En cas de divergence, demander et laisser l'écart visible.
- **Décision :** `state/decisions.md` porte le statut et la source ; il s'écrit avec `uv run tools/brain/decision.py` (`propose`, `validate`, `refuse`, `replace`). Une décision évoquée en réunion reste proposée jusqu'au classement confirmé par le propriétaire ; garder la trace des décisions refusées ou remplacées.
- **Personne :** `people/` fait foi pour l'identité et les alias ; la mission garde son rôle propre. Ne jamais créer une fiche sans prénom et nom ni inventer de fait. Chaque ajout cite une source datée ou une information datée du propriétaire.

## Ranger l'information

**Un projet = un dossier qui contient `state/actions.md`** : pour un client, le dossier de la mission (`projects/clients/<client>/missions/<mission>/`) ; en interne, `projects/internal/<projet>/`. Seuls les axes `clients` et `internal` existent dans ce starter. Chaque projet a sa fiche `<projet>.md` et `state/` ; `notes/`, `journal/`, `workstreams/`, `sources/YYYY-MM/`, `handoffs/` et `scripts/` se créent au besoin. Un dossier client ne contient que `<client>.md`, `missions/` et, au besoin, `archive/`. Le tableau ci-dessous est la seule carte « où va quoi » ; les formats détaillés sont dans [`kit/brain/docs/CONVENTIONS.md`](docs/CONVENTIONS.md).

| Information | Où | Nommage | Règle clé |
|---|---|---|---|
| Action | `<projet>/state/actions.md` ; sans mission, `projects/internal/setup/` (`SET`) | `**<ID>**`, préfixe du projet | Seul endroit où une action s'écrit |
| Décision | `<projet>/state/decisions.md` | Proposées · Validées · Refusées / remplacées | Proposée tant que le propriétaire ne l'a pas classée |
| Glossaire | `<projet>/state/glossary.md` | — | Facultatif : termes, sigles, erreurs de transcription |
| Source datée | `<projet>/sources/YYYY-MM/`, listée dans `index.md` | `YYYY-MM-DD-<type>-<slug>.md` | Ce qu'un tiers a dit ou transmis ; jamais réécrite, addendum daté |
| Note de travail | `<projet>/notes/` | `YYYY-MM-DD-<sujet>.md` | Idée, analyse ou préparation du propriétaire ; modifiable |
| Leçon réutilisable, config machine | `projects/internal/setup/notes/` | `YYYY-MM-DD-<sujet>.md` | Critères dans les conventions ; une leçon d'une seule mission reste dans son `notes/` |
| Doc de référence de mission | `<projet>/workstreams/` | `<sujet>.md`, jamais daté | Tenue à jour |
| Événement du mois | `## Timeline` de `<projet>.md` | `- AAAA-MM-JJ — … (modèle)` | Une ligne par événement, mois en cours seulement |
| Mois passés | `<projet>/journal/` | `YYYY-MM.md` | Déplacés sans demander ; un événement tardif va dans le journal de son mois |
| Actions closes depuis plus de 30 jours | `<projet>/state/` | `actions-archive-AAAA.md` | Déplacées sans demander ; ID réservés |
| Handoff | `<projet>/handoffs/` | `YYYY-MM-DD-handoff-<slug>.md` | Autoportant |
| Script qui fabrique un livrable | `<projet>/scripts/<sujet>/` | `README.md` obligatoire | Aucun fichier généré ni secret dans Git |
| Profil et voix | `me/about-me.md` | — | Lu par l'agent ; modifié seulement après proposition |
| Personne | `people/` à plat | `prenom-nom.md` | Prénom et nom confirmés |
| Capture brute | `inbox.md` | — | Vidée par tri |
| Note brute à retraiter | `inbox/` | `YYYY-MM-DD-<slug>.md` | Défaut de toute note sans projet ; supprimée après dispatch |
| Contenu d'un autre périmètre | l'autre brain, choisi d'après sa `description` (§ Plusieurs brains) | — | Ne pas mélanger les périmètres |
| Livrable montré à quelqu'un | `../artifacts/` | dossier + `README.md` de provenance | Aucun `build/` dans le brain |
| Scratch, builds intermédiaires | `../agents/` | — | Jetable |
| Code et documentation technique | `../repos/` | — | La fiche pointe, ne recopie pas |

- **Mouvements mensuels, sans demander.** Dès qu'un agent écrit dans un projet un nouveau mois, ou que le doctor `brain-clean` le signale, il déplace les entrées des mois passés de la timeline dans `journal/YYYY-MM.md`, lance `uv run tools/brain/action.py archive --write` et le mentionne dans son résumé. Tout autre archivage attend une demande explicite du propriétaire.
- Les conventions et guides sont dans `kit/brain/docs/`, les modèles dans `kit/brain/templates/` (`../kit/brain/` depuis un brain) ; ils ne reçoivent jamais de note de projet, et le `docs/` d'un brain ne garde que `LOCAL-WORKFLOWS.md`. Toute nouvelle fiche part de `kit/brain/templates/_<TYPE>-TEMPLATE.md`. `kit/brain/templates/templater/` contient des commandes Templater, pas des modèles de fiche à copier.
- Le CR se fait via `cr-reunion`, les messages via `veille-messages`, le tri de `inbox.md` et `inbox/` via `inbox`, avec leurs validations. Si le rattachement est incertain, poser la question dans `inbox.md`.
- Aucun Markdown ne cite un document situé hors de l'espace de travail : ni chemin local, ni nom de fichier. Les liens web peuvent rester pour la trace. Copier un document qui doit rester cité dans `../artifacts/` avec son README de provenance ; sinon, décrire sa provenance en mots. Les dossiers d'entrée des skills vivent dans `.data/local-paths.json`.
- Ne pas ingérer de secrets.
- Dans Obsidian, le brain se lit depuis le coffre ouvert à la racine de l'espace de travail ; ne pas créer de coffre `brain/.obsidian/`.
- Les liens sont Markdown relatifs avec extension `.md`, sans wikilinks. Après un déplacement, réparer les backlinks et lancer `uv run tools/brain/check-links.py` depuis la racine de l'espace.

## Plusieurs brains

- Chaque brain (`brain/`, `brain-perso/`, `brain-<nom>/`) est un dépôt Git privé distinct et une frontière de confiance, déclarée dans `.data/brain.json` : `scope` (perso, employeur, client…), `description` (ce qu'il contient et ne doit jamais contenir), `remote` et `email` (motifs `fnmatch` vérifiés par le doctor de la machine), `allow` (noms de clients d'un autre brain qui peuvent y figurer). Chaque brain peut avoir ses skills privés (`skills/<nom>/`) et sa config (`.data/work-config.json`). `brain/` est le brain par défaut : il porte aussi les réglages de la personne (`.data/local-paths.json` : brains attendus, dossiers d'entrée).
- Avant d'écrire du contenu nouveau, lire la `description` de chaque brain (`uv run tools/brain/brain-state.py brains` les liste avec leur `scope`) et choisir le brain d'après elle. Si le contenu peut aller dans deux brains, ou dans aucun, demander au propriétaire.
- Aucun lien Markdown d'un brain vers un autre, aucun nom de client d'un autre brain (dossiers de son `projects/clients/`) dans le contenu, sauf ceux de `allow`. `check-links.py` et le hook pre-commit du brain refusent les deux.
- L'état d'un skill s'écrit dans le `.data/` du brain où l'on écrit, jamais dans celui d'un autre.

## Finir le travail

- Laisser une entrée datée courte dans la timeline du projet, mois en cours seulement, avec le modèle entre parenthèses ; mettre à jour l'action dans son registre. Une session doit laisser une trace utile sans recopier les sources.
- Vérifier les liens, le diff et l'état Git. Signaler au début les modifications déjà présentes et ne pas les écraser. **Aucun commit ni push sans demande explicite distincte** : proposer les fichiers et un message Conventional Commits ; signaler les commits locaux non poussés. Ne jamais lire un `.env` ni ajouter une mention d'IA à un commit ou une PR. Le brain reste privé.

## Références à ouvrir au bon moment

- [`kit/brain/docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — formats des sources, registres, décisions, timelines, journal, notes, personnes, handoffs et archives ; tableau `tasks`.
- [`kit/brain/docs/WORKFLOWS.md`](docs/WORKFLOWS.md) — tri de l'inbox, réconciliation, capitalisation et fin de session.
- `docs/LOCAL-WORKFLOWS.md`, dans le brain — chemins privés et exceptions locales.
- [`kit/brain/docs/REPOSITORIES.md`](docs/REPOSITORIES.md) — URLs Git client privées, vérification des remotes et clonage reproductible.
- [`kit/brain/docs/GIT.md`](docs/GIT.md) — format des commits, sélection des fichiers, remote et règles des repos partagés ; à lire avant toute opération Git qui écrit ou publie.
- `brain-clean` — audit ou nettoyage global du brain, avec arbitrage du propriétaire sur les ambiguïtés.
