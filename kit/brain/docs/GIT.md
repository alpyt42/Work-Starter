# Git et publication du brain

À lire avant de préparer un commit, un push ou une modification de remote. Les interdictions essentielles restent dans [`AGENTS.md`](../AGENTS.md) et dans l'`AGENTS.md` de l'espace de travail.

## Commits

- Conventional Commits : `type(scope facultatif): sujet`, impératif minuscule sans point final, environ 72 caractères. Types autorisés : `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `perf`, `build`, `ci`, `style`, `revert`. La zone va dans le scope, jamais à la place du type. Le corps explique pourquoi, pas la liste des fichiers.
- La langue du sujet suit l'historique du dépôt. Dans le brain : nouvelle note/fiche → `feat(notes):`, `feat(projects):`, `feat(people):` ; passe de tri ou grooming → `chore(brain):` ; convention ou `AGENTS.md` → `docs(…):`.
- Aucun commit ni push sans demande explicite du propriétaire, un GO distinct pour chaque action. En fin de session, proposer fichiers et message ; signaler les commits locaux non poussés. Stager uniquement les chemins touchés (`git add <chemins>`), jamais `git add -A`. Vérifier `git diff --cached --name-only` avant de commiter ; si l'index contient le travail du propriétaire, utiliser `git commit -- <chemins>` pour n'inclure que les chemins de la passe autorisée.
- Jamais de secret, `.env`, clé ou credential dans un commit, même dans le message. Aucune signature d'IA dans commit, PR, commentaire ou description. Jamais `push --force`, `--amend` ou rebase d'un commit déjà partagé.

## Identités Git et clés SSH

Une identité (auteur + clé SSH) par frontière de confiance : perso, employeur, chaque client. Elle se choisit une fois dans la configuration home, jamais dans chaque clone : `~/.gitconfig` porte `user.useConfigOnly = true` et inclut un `~/.gitconfig-<frontière>` par dossier (`includeIf "gitdir:…"`) et par remote (`includeIf "hasconfig:remote.*.url:…"`, qui s'applique aussi pendant `git clone`).

Chaque brain déclare dans `.data/brain.json` le `remote` et l'`email` attendus (motifs `fnmatch`) : le doctor de la machine compare ces motifs à l'identité effective du clone. Les correspondances propres à une machine ou à un compte ne se remplissent pas dans ce guide géré par le starter. Les garder dans le `docs/LOCAL-WORKFLOWS.md` du brain si elles doivent être documentées dans le brain privé, sans clé privée, phrase de passe ni chemin de clé.

- Un hôte qui sert plusieurs comptes (par exemple `github.com`) impose sa clé par `core.sshCommand` dans le fichier inclus ; un hôte à compte unique, par un bloc `Host` + `IdentityFile` + `IdentitiesOnly yes` dans `~/.ssh/config`.
- Vérifier l'empreinte de la clé d'hôte d'un serveur auprès d'une source sûre avant la première connexion ; ne jamais l'accepter à l'aveugle.
- Ne jamais ajouter de `user.*` ou `core.sshCommand` local dans un clone : il écrase silencieusement les règles home.

Contrôle (aucune de ces commandes ne lit de clé privée) :

```bash
git config --file ~/.gitconfig --list                                    # useConfigOnly et règles includeIf
git -C <clone> config --show-origin --get-regexp '^(user|core\.sshcommand)'
env | grep -E '^GIT_SSH' || echo "aucun GIT_SSH*"
ssh -G <hôte> | grep -E '^(identityfile|identitiesonly) '                # clé choisie par ~/.ssh/config
ssh -T git@<hôte>                                                        # compte authentifié
```

## Publication du brain

- Le brain contient du contexte client et doit rester privé ; sa destination : (à compléter, remote privé). Ne rien copier vers un dépôt public sans anonymisation explicite.
- Publier un instantané initial avec un historique neuf.
- Le hook pre-commit du brain (`tools/machine/hooks/brain-pre-commit`) refuse un commit qui contient un lien vers un autre brain ou un nom de client d'un autre brain (hors `allow` de `.data/brain.json`), en plus des registres mal formés, des liens morts et des secrets. Il ne fait que valider.

## Repos partagés et clones client

- Un repo partagé reste neutre et autoportant : aucun chemin machine (`~/`, `/Users/…`), pointeur vers `brain/` ou `repos/`, ni contexte propre au propriétaire. Porter les décisions utiles dans le repo et citer les autres repos par URL. Avant de pousser, chercher `brain/`, `~/`, `/Users/`.
- Lire `repos/<client>/AGENTS.md` avant de toucher un clone client. Dans un clone client, GO distinct pour commit, push, rebase, remote et opérations `gh`/`glab`. Aucune signature d'IA ni référence locale dans ce qui part chez le client.
