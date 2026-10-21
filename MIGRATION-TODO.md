# TODO — Industrialisation et migration de Work / Brain

Cette feuille de route transforme Work-Starter en produit public versionné et met à jour les brains privés sans écraser leurs données. Elle est la référence de planification de la migration ; les conventions détaillées restent dans les fichiers qu'elle cite.

## Résultat attendu

À terme :

- Work-Starter est l'unique source publique maintenue pour les conventions, outils, templates, schémas et migrations ; il ne livre aucun skill, chacun vit dans le brain dont il touche les données ;
- chaque brain (`brain/`, `brain-perso/`, `brain-<nom>/`) est un dépôt privé indépendant et une frontière de confiance déclarée (`.data/brain.json`), sauvegardé et versionné par son propriétaire ;
- une release met à jour le socle public et peut proposer une migration de structure, mais ne remplace jamais les contenus privés ;
- les skills installés, les réglages Obsidian, chemins machine, caches et secrets restent locaux ;
- un brain vierge est créé localement depuis `kit/brain/seed/` (`tools/brain/new-brain.py`) : brain-starter et le brain de démonstration n'existent plus, aucune copie n'est maintenue à la main ;
- toute mise à jour est vérifiable par un dry-run, réversible en cas d'échec et n'effectue jamais de commit ni de push.

## Garanties non négociables

- [ ] Une release ne remplace jamais `brain/me/`, `brain/people/`, `brain/projects/`, `brain/inbox.md`, `brain/inbox/` ni les workflows privés.
- [ ] Une migration ne réécrit jamais rétroactivement une source, un CR, une note, une décision ou un registre existant sans transformation explicitement documentée.
- [ ] Aucun secret ne va dans Git, même privé : tokens, mots de passe, clés privées, cookies et credentials restent dans le keychain, un gestionnaire de secrets, l'environnement ou un `.env` ignoré.
- [ ] Toute opération d'upgrade commence par un contrôle des deux dépôts et un aperçu des changements.
- [ ] Aucun updater ne commit, ne pousse, ne modifie la configuration home, SSH ou le keychain.
- [ ] Un conflit, une dérive locale d'un fichier géré ou une migration non reconnue arrête l'opération avec un diagnostic exploitable.

## Décision d'architecture

### Source de vérité

- [ ] Faire de Work-Starter l'unique source de vérité du produit.
- [x] Abandonner `brain-starter` : les conventions génériques vivent dans `kit/brain/` (`AGENTS.md`, `docs/`, `templates/`), un brain n'en garde qu'un `AGENTS.md` court qui y renvoie.
- [x] Supprimer `examples/brain/`, `tools/machine/demo.sh` et `.kit-options/` ; le seed d'un brain neuf est `kit/brain/seed/`, copié une fois par `tools/brain/new-brain.py`.
- [x] Ne livrer ni skill ni réglage personnel : `skills/`, `skills-catalog.json`, `.obsidian/` et `tools/timesheet/` (Boond, Toggl) sont retirés ; les skills vivent dans les brains, Obsidian se règle à la main (`kit/obsidian/README.md`).
- [x] Plusieurs brains : chacun est une frontière de confiance (`.data/brain.json`) avec ses skills (`<brain>/skills/`) et sa configuration (`.data/work-config.json`) ; aucun lien ni nom de client d'un brain à l'autre (`check-links.py`, `check-no-client.py --brain`, hook `brain-pre-commit`).
- [x] Test qui génère un brain depuis `kit/brain/seed/` et vérifie sa structure et ses liens (`tests/test_new_brain.py`).
- [ ] Lancer ces tests en CI et y vérifier aussi les actions et les décisions du brain généré.

### Arborescence cible

```text
Work/
├── AGENTS.md, CLAUDE.md              # carte de l'espace, gérée
├── work-config.example.json          # défauts publics de la configuration des skills
├── kit/
│   ├── brain/
│   │   ├── AGENTS.md                 # conventions communes à tous les brains
│   │   ├── docs/                     # CONVENTIONS, WORKFLOWS, GIT, REPOSITORIES
│   │   ├── templates/
│   │   ├── seed/                     # copié une fois dans un brain neuf
│   │   ├── schemas/                  # à venir
│   │   │   ├── v1.md                 # immuable après publication
│   │   │   └── v2.md
│   │   └── migrations/               # à venir
│   ├── obsidian/                     # guide de réglage manuel, tasks-board.css
│   └── manifests/                    # à venir
├── tools/                            # outils gérés (brain/, machine/, repos/, tasks-web/)
│   └── machine/                      # installation, update, doctor, hooks
├── tests/
├── brain/                            # brain par défaut, dépôt privé séparé
│   ├── .brain/instance.json          # version de schéma (à venir)
│   ├── AGENTS.md                     # pointeur court vers kit/brain/AGENTS.md
│   ├── AGENTS.local.md               # règles privées (à venir)
│   ├── me/
│   ├── projects/
│   ├── people/
│   ├── inbox/
│   ├── skills/                       # skills propres au brain
│   └── .data/                        # brain.json, work-config.json, états
├── brain-perso/, brain-<nom>/        # autres brains, même structure, un dépôt privé chacun
├── repos/                            # clones, chacun son dépôt
├── artifacts/                        # local, sauvegarde externe
└── agents/                           # scratch jetable
```

Local et ignoré, hors de l'arbre versionné : `.agents/`, `.claude/skills/`, `.obsidian/`, `work-config.local.json`, `skills-lock.json`, `.work-state.json`, `tools/.env`.

## Modèle de propriété des fichiers

Créer un manifeste versionné qui classe chaque chemin dans une seule catégorie :

| Catégorie | Propriétaire | Comportement lors d'une release |
|---|---|---|
| `managed` | Work-Starter | Remplacé seulement s'il n'a pas dérivé localement |
| `generated` | Générateur | Régénéré depuis les defaults et la configuration locale |
| `seed` | Instance après création | Créé uniquement s'il n'existe pas, jamais remplacé |
| `migrated` | Instance | Transformé uniquement par une migration explicite |
| `private` | Utilisateur | Jamais modifié automatiquement |
| `local` | Machine | Ignoré par Git et jamais publié |

- [x] Déclarer la frontière de chaque brain dans un manifeste (`.data/brain.json` : `scope`, `description`, `remote`, `email`, `allow`) et la contrôler (doctor, `check-links.py`, `check-no-client.py`, hook `brain-pre-commit`).
- [ ] Définir un schéma de manifeste de propriété lisible par l'humain et la machine.
- [ ] Vérifier qu'un chemin ne peut appartenir à deux catégories incompatibles.
- [ ] Ajouter un test qui échoue pour tout fichier public non classé.
- [ ] Ajouter un test qui échoue si un chemin privé ou local apparaît dans les fichiers à remplacer.
- [ ] Enregistrer les checksums des fichiers gérés pour détecter une dérive avant écrasement.
- [ ] Documenter la procédure permettant de promouvoir une personnalisation utile vers le socle public.

Exemple indicatif :

```yaml
managed:
  - AGENTS.md
  - kit/**
  - tools/**
  - work-config.example.json

generated:
  - .agents/**
  - .claude/skills/**
  - skills-lock.json
  - .work-state.json

seed:
  - brain/me/about-me.md
  - brain/AGENTS.local.md
  - brain/inbox.md
  - brain/tasks.md
  - brain/.data/brain.json

migrated:
  - brain/.brain/instance.json
  - brain/projects/**/state/**

private:
  - brain/me/**
  - brain/people/**
  - brain/projects/**
  - brain/inbox/**
  - brain/skills/**
  - brain/.data/work-config.json

local:
  - .obsidian/**
  - work-config.local.json
  - brain/.data/local-paths.local.json
  - tools/.env
```

## Personnalisation et confidentialité

### Privé et versionné dans le brain

Ces fichiers doivent être restaurables sur une autre machine et bénéficier de l'historique Git privé :

- [ ] Conserver `brain/me/about-me.md` dans le dépôt privé ; il porte l'identité professionnelle, la façon de travailler, les préférences de collaboration et la voix.
- [ ] Créer `brain/AGENTS.local.md` pour les règles privées qui complètent le socle public : autonomie, validations, frontières de confidentialité et exceptions propres à l'organisation.
- [ ] Conserver `brain/docs/LOCAL-WORKFLOWS.md` pour les procédures propres au propriétaire ou à son organisation.
- [ ] Conserver dans `brain/.data/` les mappings, catalogues privés, curseurs partagés et états nécessaires pour éviter de retraiter les mêmes éléments sur plusieurs machines.
- [ ] Faire de `about-me.md` la source humaine de l'identité ; éviter une seconde copie du nom, du fuseau ou des langues dans plusieurs fichiers.
- [ ] Si un outil a besoin de champs structurés, préférer un front matter validé dans `about-me.md` ou générer l'état technique depuis cette source.

### Local et ignoré

- [x] Garder `work-config.local.json` pour les choix propres à la machine (skills désactivés, entrée tierce remplacée).
- [ ] Scinder `.data/local-paths.json` en données logiques privées (brains attendus) et chemins propres à la machine (dossiers d'entrée).
- [ ] Créer `brain/.data/local-paths.example.json`, puis générer ou demander `brain/.data/local-paths.local.json`, ignoré.
- [x] Garder `.agents/`, `.claude/skills/`, `.obsidian/` (réglé à la main), les caches et les fichiers générés hors Git.
- [ ] Ajouter au doctor une alerte si un fichier censé être local devient suivi par Git.

### Répartition recommandée

```text
brain/me/about-me.md                    privé, versionné
brain/AGENTS.local.md                   privé, versionné (à venir)
brain/docs/LOCAL-WORKFLOWS.md           privé, versionné
<brain>/.data/brain.json                privé, versionné (frontière du brain)
<brain>/.data/work-config.json          privé, versionné (skills tiers, désactivés)
<brain>/skills/                         privé, versionné (skills propres au brain)
brain/.data/local-paths.json            privé, versionné (brains attendus ; chemins à scinder)
brain/.data/client-repos.json           privé, versionné
<brain>/.data/*-state.json              privé, versionné
brain/.data/local-paths.local.json      local, ignoré (à venir)
work-config.local.json                  local, ignoré
tools/.env                              secret, ignoré
```

## Conventions et documents immuables

- [x] Déplacer les conventions génériques hors du dépôt privé, dans `kit/brain/`.
- [x] Réduire `<brain>/AGENTS.md` à un pointeur court vers `../kit/brain/AGENTS.md`, suivi des seules règles propres au brain.
- [ ] Déplacer ces règles dans `AGENTS.local.md`, lu après le socle, si le pointeur doit rester identique d'un brain à l'autre.
- [x] Pointer Obsidian et les outils vers les templates gérés dans Work-Starter (`kit/brain/templates/`).
- [ ] Distinguer les conventions courantes des spécifications immuables.
- [ ] Publier chaque schéma sous un nom versionné (`schemas/v1.md`, `schemas/v2.md`) et ne jamais modifier une version publiée.
- [ ] Utiliser les tags Git et les releases comme références historiques stables.
- [ ] Enregistrer la version du template utilisée lors de la création d'un document si cette provenance est utile.
- [ ] Appliquer les nouveaux templates uniquement aux futurs documents ; ne pas réécrire les documents historiques.

## Configuration locale résolue

Le fichier local ne doit pas être une copie figée de toutes les valeurs par défaut.

- [x] Défauts publics versionnés dans `work-config.example.json`, maintenus par les releases.
- [x] Limiter `work-config.local.json` aux choix et overrides de la machine.
- [x] Configuration résolue = défauts, puis `.data/work-config.json` de chaque brain, puis override local (`work_config.py`) ; fichiers générés ignorés : `skills-lock.json` et `.work-state.json` (empreinte de la configuration résolue).
- [ ] Définir les clés de sécurité non surchargeables.
- [ ] Faire évoluer le schéma de configuration (`version: 1` posé, clés inconnues refusées) et fournir ses migrations.
- [x] Signaler les skills installés mais inconnus (`doctor.py`, `work_config.py adopt`) et une configuration modifiée depuis le dernier `update.sh`.
- [ ] Signaler les clés devenues obsolètes et les skills retirés d'une couche.
- [x] `work_config.py check` (validation) et `status` (changement depuis le dernier `update.sh`).
- [ ] Prévoir `work config diff` et une commande unifiée `work config`.

## Skills et plugins

### Skills des brains

- [x] Aucun skill dans le starter : la source d'un skill propre est `<brain>/skills/<nom>/`, dans le brain dont il touche les données.
- [x] Matérialiser les points de découverte Codex et Claude localement (`link-skills.sh`, `sync-house-skills.py`, marqueur `.install-as-copy`).
- [x] Ne jamais exposer un skill désactivé (`skills.disabled`, union de toutes les couches).

### Skills tiers

- [x] Chaque entrée porte `source`, `sourceType`, `skillPath` et `computedHash` dans le `.data/work-config.json` d'un brain (`adopt` après `npx skills add`).
- [ ] Compléter chaque entrée avec le commit Git exact et la licence.
- [ ] Pinner la version de l'outil d'installation appelé par `npx`.
- [x] Générer le lock local uniquement à partir des couches de configuration (`work_config.py lock`, qui refuse les skills inconnus).
- [ ] Refuser une installation dont le contenu ne correspond pas au hash attendu.
- [ ] Afficher les skills ajoutés, retirés ou modifiés avant installation.
- [x] Conserver les copies installées hors Git.

### Obsidian

- [x] Le starter ne gère plus `.obsidian/` : ignoré, réglé à la main par machine (`kit/obsidian/README.md`).
- [ ] Vérifier le guide à chaque release (IDs des plugins, réglages, statuts des actions).

## Initialisation

- [x] Garder une commande unique d'installation (`tools/machine/install.sh`).
- [x] Utiliser le seed canonique (`kit/brain/seed/`) pour créer un brain neuf (`tools/brain/new-brain.py`, avec `--scope`, `--description`, `--remote`, `--email` pour sa frontière).
- [x] Créer un historique Git neuf pour le brain sans lui donner de remote.
- [ ] Créer uniquement les fichiers `seed` absents d'un brain existant (aujourd'hui `new-brain.py` refuse un dossier existant).
- [ ] Générer `brain/.brain/instance.json` avec la version du schéma et la release d'origine.
- [x] Laisser le propriétaire ajouter et vérifier lui-même son remote privé.
- [ ] Proposer un mode consommateur où le dépôt Work garde Work-Starter comme `origin` et reste en avance rapide (aujourd'hui `install.sh` renomme `origin` en `starter` ; mise à jour par `git pull starter main`).
- [ ] Documenter séparément le mode contributeur, avec fork et remote `upstream`.

Copier peut servir à l'initialisation et aux scaffolds. Il ne doit pas être l'unique barrière protégeant les données privées : le manifeste de propriété reste l'autorité.

## Updater et migrations

### Existant

Mise à jour manuelle : `git pull starter main` dans Work, `git pull` dans chaque brain, puis `tools/machine/update.sh` ; `doctor.py` signale une configuration modifiée depuis le dernier `update.sh`. Ni dry-run, ni migration, ni rollback.

### Interface cible

```bash
uv run tools/machine/work.py version
uv run tools/machine/work.py update --check
uv run tools/machine/work.py update --dry-run
uv run tools/machine/work.py update --apply
uv run tools/machine/work.py migrate --dry-run
uv run tools/machine/work.py doctor
```

### Préflight

- [ ] Identifier la version Work installée, la dernière release compatible et le schéma de chaque brain.
- [ ] Vérifier les états Git de Work et de chaque brain sans lire de secret.
- [ ] Refuser une mise à jour destructive si le dépôt concerné est sale.
- [ ] Détecter les commits locaux non poussés et les signaler sans bloquer les contrôles en lecture seule.
- [ ] Vérifier la provenance et les checksums de la release.
- [ ] Calculer le plan complet avant toute écriture.

### Dry-run

- [ ] Afficher les versions avant et après.
- [ ] Lister les fichiers gérés ajoutés, modifiés et supprimés.
- [ ] Lister les fichiers générés qui seront régénérés.
- [ ] Lister chaque migration structurelle et son effet attendu.
- [ ] Garantir et afficher `données privées remplacées : 0`.
- [ ] Produire un diff consultable.

### Application

- [ ] Télécharger ou extraire la release dans un répertoire temporaire.
- [ ] Mettre à jour uniquement les fichiers classés `managed` et sans dérive locale.
- [ ] Exécuter les migrations nécessaires dans l'ordre des versions.
- [ ] Rendre chaque migration idempotente ou détecter clairement son application préalable.
- [ ] Régénérer les fichiers `generated` depuis la configuration résolue.
- [ ] Exécuter les contrôles de liens, actions, décisions, configuration et confidentialité.
- [ ] Restaurer l'état initial si une étape échoue.
- [ ] Écrire un rapport local de migration sans secret.
- [ ] Ne jamais commit ni push automatiquement.

### Version de l'instance

Créer dans chaque brain privé :

```json
{
  "schemaVersion": 1,
  "createdWith": "1.0.0",
  "lastMigratedWith": "1.0.0"
}
```

- [ ] Ne stocker aucune donnée personnelle dans ce fichier.
- [ ] Vérifier que le kit courant sait lire le schéma du brain avant d'exécuter un outil.
- [ ] Bloquer proprement un brain créé par une version future inconnue.

## Releases

Adopter SemVer :

- `patch` : correction de convention, template, outil, test ou documentation sans changement de schéma ;
- `minor` : ajout compatible, nouveau template, skill, type de document ou champ optionnel ;
- `major` : changement incompatible de structure ou de format nécessitant une migration.

Chaque release doit fournir :

- [ ] un changelog orienté utilisateur ;
- [ ] la version du schéma du brain ;
- [ ] le manifeste de propriété ;
- [ ] les migrations nécessaires ;
- [ ] les checksums des assets ;
- [ ] les notes de compatibilité et de rollback ;
- [ ] le résultat des tests ;
- [ ] un tag immuable.

## CI et qualité

- [ ] Tester l'installation vierge sur les plateformes supportées.
- [ ] Tester l'upgrade depuis chaque version supportée vers la dernière.
- [ ] Tester une mise à jour avec contenu privé réaliste et vérifier qu'aucun fichier privé ne change.
- [ ] Tester la détection d'une dérive d'un fichier géré.
- [ ] Tester le rollback après échec de migration.
- [ ] Tester deux exécutions successives d'une même migration.
- [ ] Générer un brain depuis `kit/brain/seed/` et le tester en CI.
- [ ] Vérifier les liens Markdown, registres d'actions et décisions.
- [ ] Scanner les chemins publics pour les noms privés, chemins machine et secrets évidents.
- [ ] Vérifier que `git status` ne montre aucun fichier généré après les tests.
- [ ] Produire une matrice claire des versions de Python, Git, Node, Obsidian et systèmes supportés.

## Phases de réalisation

### Phase 0 — Stabiliser l'existant

- [ ] Publier l'état actuel comme baseline testée.
- [ ] Ajouter les tags et un changelog.
- [ ] Documenter les chemins actuellement gérés, privés, locaux et générés.
- [ ] Ajouter les vérifications de reproductibilité du lock des skills tiers.

**Terminé quand :** une installation vierge passe tous les contrôles depuis un tag.

### Phase 1 — Une seule source de vérité

- [x] Créer `kit/brain/`.
- [x] Y déplacer les conventions et templates génériques (schémas : à venir avec la phase 3).
- [x] Remplacer brain-starter par `kit/brain/seed/` et `tools/brain/new-brain.py`.
- [x] Supprimer la démo `examples/` et `tools/machine/demo.sh`.
- [x] Retirer du starter les skills, `.obsidian/` et l'outillage Boond/Toggl ; chaque brain porte ses skills et sa configuration.

**Terminé quand :** aucune convention ou structure générique n'est maintenue manuellement à deux endroits.

### Phase 2 — Propriété et personnalisation

- [x] Déclarer la frontière de chaque brain (`.data/brain.json`) et la contrôler.
- [ ] Introduire le manifeste de propriété des fichiers.
- [ ] Ajouter `AGENTS.local.md` et le modèle seed.
- [ ] Séparer les chemins machine des états privés partagés.
- [x] Passer à `defaults + overrides + resolved config`.

**Terminé quand :** chaque fichier est classé et les personnalisations survivent à une mise à jour simulée.

### Phase 3 — Versions et migrations

- [ ] Ajouter `.brain/instance.json`.
- [ ] Définir le format des migrations et leur registre.
- [ ] Implémenter dry-run, application transactionnelle et rollback.
- [ ] Ajouter les tests d'upgrade interversions.

**Terminé quand :** un brain de schéma précédent migre vers le schéma courant sans modification de ses données privées hors transformations annoncées.

### Phase 4 — Expérience de mise à jour

- [ ] Fournir la commande `work update`.
- [ ] Gérer le canal stable et, si utile, un canal preview.
- [ ] Ajouter un résumé lisible, les diffs et les instructions post-update.
- [ ] Simplifier le mode consommateur et documenter le mode contributeur.

**Terminé quand :** un utilisateur non contributeur peut installer puis mettre à jour Work avec deux commandes et comprendre exactement ce qui change.

### Phase 5 — Industrialisation publique

- [ ] Ajouter licence, politique de sécurité, contribution et support.
- [ ] Publier des releases GitHub avec assets et checksums.
- [ ] Ajouter une documentation de migration par version majeure.
- [ ] Mesurer les installations et erreurs uniquement si cela peut être fait sans télémétrie implicite ni donnée privée.

**Terminé quand :** le projet peut être utilisé, mis à jour, audité et contribué sans connaissance de l'environnement du mainteneur.

## Hors périmètre volontaire

- Synchroniser ou sauvegarder automatiquement les artifacts.
- Publier un brain ou une donnée personnelle.
- Gérer les identités Git, clés SSH, comptes cloud ou secrets de l'utilisateur (règles : `tools/machine/GIT-IDENTITY.md`).
- Livrer des skills ou générer `.obsidian/` : un skill vit dans le brain dont il touche les données, Obsidian se règle à la main.
- Installer silencieusement un skill ou une capacité non sélectionnée.
- Transformer automatiquement un contenu historique uniquement parce qu'un template a changé.

## Ordre recommandé pour la prochaine itération

1. Écrire le manifeste de propriété de l'arborescence actuelle.
2. Introduire `.brain/instance.json` sans changer la structure.
3. Scinder `local-paths.json` entre données logiques privées et chemins machine.
4. Implémenter `update --check` et `update --dry-run` avant toute commande d'application.
5. Ajouter la première migration réelle seulement après validation du rollback et des tests d'intégrité.
