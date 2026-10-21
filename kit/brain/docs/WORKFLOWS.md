# Workflows — comment utiliser cette mémoire concrètement

Le système, c'est juste des fichiers markdown. La valeur vient de quelques habitudes simples. À lire une fois ; ça répond à « qu'est-ce que j'édite, quand, et quand je demande à l'agent ? »

## Les fichiers centraux

| Fichier | Ce que c'est | Qui écrit dedans | Fréquence |
|---|---|---|---|
| `inbox.md` | Scratchpad de capture brute | Toi tu balances ; l'agent vide | Toi : toute la journée |
| `inbox/` | Notes entières à retraiter (un fichier par note) | Toi tu déposes ; l'agent dispatche et supprime | Au besoin |
| `state/actions.md` | Registre des actions d'un projet, seul endroit où une action s'écrit | L'agent (et toi) | Au fil du travail |
| `tasks.md` | Pilotage quotidien, liste par projet et kanban sur tous les registres | Personne : il se calcule | Tu crées, planifies et changes l'état des actions |

En une ligne : **inbox = les pensées atterrissent · registres = les actions, une seule fois · tasks = la vue pour piloter.** Les décisions font foi dans `state/decisions.md` (voir [`AGENTS.md`](../AGENTS.md) § « Ce qui fait foi »).

## Utiliser la liste et le kanban dans Obsidian

1. **Créer** : ouvre Tasks (`tasks.md`), puis clique sur **Nouvelle action**. Choisis le projet (préfixé du nom du brain quand l'espace en compte plusieurs : le formulaire liste les registres de tous les brains), l'intitulé, le responsable, l'état, la priorité et l'échéance éventuelle. Le formulaire ajoute l'action dans le bon registre avec son ID ; Annuler interrompt la création.
2. **Préparer ta journée** : consulte « Aujourd'hui » et « En cours ». Dans « À lancer » ou un projet, utilise le crayon 📝 pour définir **Scheduled / Planification** à aujourd'hui sur les actions que tu veux travailler. `⏳` dit quand tu travailles ; `📅` dit quand tu dois livrer. Tu peux choisir jusqu'à trois actions pour garder une journée lisible.
3. **Avancer** : depuis la liste ou le kanban (`tasks.md`), clic droit sur la case ou crayon 📝 → état `[/]` pour commencer, `[w]` après une relance quand tu attends une réponse. Les colonnes se recalculent ; elles ne se déplacent pas par glisser-déposer.
4. **Terminer** : coche la case. Tasks écrit `[x]` et la date de fin dans le registre ; la prochaine passe de maintenance range la ligne dans `Terminées`. Pour annuler, choisis `[-]` et conserve la raison dans le registre.
5. **Revoir** : « À relancer » rassemble toutes les attentes ; les projets montrent les actions ouvertes de tous les responsables. Les échéances textuelles (« avant… », « à confirmer… ») se consultent dans le registre.

Les [conventions](CONVENTIONS.md#tableau-tasks-et-inbox) détaillent les filtres et les plugins nécessaires ; le guide `kit/obsidian/README.md` explique comment régler Obsidian sur une autre machine.

Dans un navigateur local, `uv run tools/tasks-web/tasks-web.py` ouvre les onglets Liste, Kanban, Outils, Git et Recherche, avec les boutons **+ Task** et **+ Note** ([guide](../../../tools/tasks-web/README.md)). L'interface modifie les mêmes registres ; actualise la page après une édition faite ailleurs.

## Les deux façons d'interagir (utilise les deux)

### Workflow A — Éditer les fichiers, puis demander à l'agent (l'ossature quotidienne)
1. Toute la journée, balance n'importe quoi dans `inbox.md` — vite, brouillon, sans trier. Une note entière (réunion prise à la main, texte collé) va plutôt dans un fichier de `inbox/`.
2. Une fois par jour, ouvre l'agent à la racine et dis **« trie mon inbox »** avec le skill `inbox` de l'espace de travail : il montre d'abord un tableau « élément → destination » à valider, puis applique.
3. Il lit chaque ligne de `inbox.md`, puis chaque note de `inbox/`, et range chaque élément selon la [table « où va quoi »](../AGENTS.md) : action → registre du projet (hors mission : `projects/internal/setup/`) · personne → `people/` · fait de mission → ligne de timeline (mois en cours), registre `state/` ou note datée `notes/` ; `workstreams/` seulement pour mettre à jour une doc de référence · fait durable sur toi → `me/about-me.md` (proposé) · idée sans mission → `projects/internal/setup/notes/` · urgent → priorité ou échéance explicite conservée, état `[/]` seulement si le travail a commencé · poubelle → supprimé. Une note de `inbox/` peut produire plusieurs éléments ; un compte rendu d'un tiers ou d'une réunion devient une source datée. Puis il vide l'inbox, supprime les notes traitées de `inbox/` (sauf son `README.md`) et te montre ce qui a bougé où.

### Workflow B — Demander directement, l'agent édite les fichiers (pour l'intention immédiate)
- « Ajoute une tâche : relancer X sur le devis » → ajoute l'action au registre du projet
- « Note que Y a validé la maquette » → met à jour la mission et la fiche personne si cette position y est utile, avec la source
- « Prends une note : … » sans projet précisé → crée la note dans `inbox/`, à dispatcher au prochain tri (convention de collecte)
- « Passe la tâche Z en cours » → met `[/]` sur sa ligne dans le registre
- « C'est quoi mon programme ? » → lance `uv run tools/brain/action.py board` (tableau complet par projet ; le pilotage quotidien est dans `tasks.md`), résume
- « Démarre une nouvelle mission chez X » → crée `projects/clients/<client>/missions/<mission>/<mission>.md` et la relie à l'index client

**Règle du pouce :** en plein flow et pas envie de penser à la structure → l'inbox (A). Tu sais exactement ce que tu veux changer → dis-le (B). Les deux gardent le markdown comme source de vérité.

### « Traite mon brain / mon inbox / mes actions » — la réconciliation
Un troisième réflexe, au-dessus de A et B : tu as bricolé des fichiers à la main dans la journée (coché des cases, jeté des lignes, déplacé des trucs), et tu demandes à l'agent de **remettre d'équerre ton travail manuel** : nettoyer la forme, ranger les actions cochées dans `Terminées` de leur registre, dispatcher ce qui traîne. Ça **n'archive pas** une mission ou un dossier tout seul — ranger dans `archive/` reste un geste que tu demandes.

## Rythme — à la demande
Pas de rituel fixe : les passes se lancent quand tu les demandes. L'agent ne les déclenche pas de lui-même, mais peut **suggérer** une passe quand il voit que ça s'accumule (inbox qui déborde, actions échues, actions cochées encore dans `Ouvertes`). Seule exception : les deux mouvements mensuels (timeline → `journal/`, actions closes depuis plus de 30 jours → archive), que l'agent fait sans demander dès qu'il écrit dans un projet un nouveau mois ou que le doctor les signale, et qu'il te mentionne dans son résumé.
- **Au fil de la journée :** capture dans `inbox.md` ; Workflow B pour tout ce qui est concret.
- **Quand tu veux t'orienter :** « fais le point » → lecture des registres, résumé.
- **Quand l'inbox se remplit** (ligne ou note dans `inbox/`) **:** « trie mon inbox ».
- **Quand le tableau devient flou :** « fais le point sur mes actions » — états à jour, actions faites rangées, attentes relancées revues.

## Où vivent les choses
La seule carte est la [table « où va quoi »](../AGENTS.md) (« Ranger l'information »). Deux réflexes : une action ne s'écrit que dans son registre `state/actions.md` (jamais dans `tasks.md` ni `inbox.md`) ; ce qui est froid ou terminé s'archive à l'endroit prévu par les [conventions](CONVENTIONS.md#liens-handoffs-et-archives), sur ta demande.

## Exécuter du vrai travail
Les tâches de code tournent contre le vrai repo sous `../repos/` + git. Une action du registre est un POINTEUR vers ce travail, pas le travail lui-même. Lance l'agent depuis la racine pour qu'il voie la mémoire et le repo, mets à jour l'action, et logge dans la fiche projet dans la même session.

## Gestes de maintenance pour l'agent

- **« Traite mon brain / mon inbox / mes actions »** signifie réconcilier les modifications manuelles du propriétaire : forme, cases cochées et classement du brut. `inbox` = tri seul ; `actions` = forme et états des registres ; `brain` = passe complète. Ne pas archiver au passage, hors mouvements mensuels. Résumer précisément ce qui a bougé.
- **Avant de vider une inbox modifiée et non commitée** (`inbox.md` ou notes de `inbox/`), proposer au propriétaire un commit de la capture brute seule pour que ses mots restent dans l'historique ; l'exécuter uniquement sur son GO. Puis traiter chaque ligne comme au Workflow A et laisser une courte ligne datée en bas de l'inbox indiquant le dispatch.
- **Tenir les registres** selon l'avancement rapporté : une action cochée depuis le tableau (`[x]` + `✅ date`) rejoint `Terminées` de son registre ; un nouvel état s'écrit sur la ligne, un nouveau fait en sous-puce datée. Une action d'un repo pointe vers le vrai travail ; l'implémentation reste dans le repo.
- **Maintenir les liens** dès qu'un fichier est créé ou déplacé ; contrôler avec `uv run tools/brain/check-links.py` depuis la racine de l'espace. Un lien vers un autre brain est refusé (chaque brain est une frontière de confiance). Les fichiers orphelins doivent être reliés ou explicitement classés, sans déduction automatique de suppression.
- **Capitaliser au bon moment** : fin de phase, débrief, handoff, incident de plus de 30 minutes ou « la prochaine fois, je… » sont les moments où se demander s'il y a une leçon. Si oui, proposer une courte note datée selon les [critères des conventions](CONVENTIONS.md#personnes-notes-et-voix) ; ne pas créer de note vide ni modifier la section Voix de `me/about-me.md` sans proposition.
- **Changement de mois** (sans demander) : déplacer les entrées des mois passés vers `journal/YYYY-MM.md` et lancer `uv run tools/brain/action.py archive --write`, selon les [conventions](CONVENTIONS.md#sources-état-et-journal) ; le mentionner dans le résumé. Ne jamais réécrire une source.
- **Fin de session** : une entrée datée courte dans la timeline du projet concerné (mois en cours seulement), avec le modèle entre parenthèses ; actions mises à jour dans leur registre ; contrôles utiles ; commit de la mémoire proposé (fichiers et message), jamais exécuté sans GO. Signaler tout commit local non poussé.
