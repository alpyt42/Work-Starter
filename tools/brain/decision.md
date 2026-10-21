# Outil des décisions

`tools/brain/decision.py` est le seul outil qui écrit dans les registres de décisions (`projects/**/state/decisions.md`, à côté du `actions.md` du projet). Il réutilise `action.py` (résolution du projet, écriture atomique, dates, validation des textes). Une décision s'écrit donc toujours de la même façon :

```markdown
### Intitulé de la décision (2026-10-13, statut : proposée)
- **Contexte :** …
- **Décision :** …
- **Conséquences :** …
- **Source :** [CR du 13/10](../sources/2026-10/2026-10-13-cr-daily-migration.md)
- **Validation :** Propriétaire, 2026-10-14.
```

- Le registre a trois sections : `## Proposées`, `## Validées`, `## Refusées / remplacées`. Une proposition s'ajoute en fin de `Proposées` ; une décision validée, refusée ou remplacée passe en **haut** de sa section (la plus récente d'abord).
- Les blocs existants varient (statut absent du titre, `active`, `remplacée`, champs `Suite`, `Remplacée par`, `Source et validation`) : l'outil les lit tels quels et ne réécrit que le bloc qu'il déplace. Le contenu d'une décision validée ne se réécrit jamais ; une nouvelle décision la remplace.
- **Numéro** : rang de la décision dans le registre du projet (1..n, dans l'ordre du fichier). Il change quand une décision change de section : relancer `list` avant de s'en servir.

## Commandes

Depuis la racine de Work ; la sortie est du JSON (codes de sortie : 0 fait, 2 requête invalide, 3 introuvable, 4 conflit ou référence ambiguë).

```sh
uv run tools/brain/decision.py list --project acme/demo --status proposee --table
uv run tools/brain/decision.py show 12 --project acme/demo
uv run tools/brain/decision.py propose --project acme/demo --title "Démo enregistrée" \
    --decision "Vidéo enregistrée plutôt que démo en direct." --context "Risque d'accès AWS." \
    --source "[CR du 13/10](../sources/2026-10/2026-10-13-cr-demo.md)" --date 2026-10-13
uv run tools/brain/decision.py validate "Démo enregistrée" --project acme/demo --on 2026-10-14 --note "en comité"
uv run tools/brain/decision.py refuse 12 --project acme/demo --reason "hors périmètre"
uv run tools/brain/decision.py replace "Calendrier des ateliers" --by "Calendrier corrigé" --project acme/demo
```

- `list` : tous les projets par défaut ; `--status proposee|validee|refusee|all` (la section fait foi, pas le texte du statut) ; `--table` pour une ligne par décision.
- `REF` : numéro du `list` de ce projet, ou sous-chaîne du titre sans tenir compte de la casse. Plusieurs décisions correspondent : code 4 avec la liste des candidats ; aucune : code 3.
- `propose` : `--title`, `--decision`, `--source` obligatoires ; `--context`, `--consequences`, `--date` (défaut : aujourd'hui, heure de Paris) en option. Crée `state/decisions.md` (titre, citation, trois sections) s'il manque. Refuse un titre déjà présent.
- `validate` : seulement une décision proposée. Statut `validée` dans le titre (ajouté s'il manquait), ligne `- **Validation :** PROPRIÉTAIRE, DATE.` (`--by`, `--note`).
- `refuse` : seulement une décision proposée. Statut `refusée`, ligne `- **Refus :** PROPRIÉTAIRE, DATE (raison).` (`--by`, `--reason`). Sans `--by`, le nom vient de `BRAIN_OWNER` ou de `owner` dans `brain/.data/doctor.json`.
- `replace OLD --by NEW` : OLD (proposée ou validée) passe en haut de `Refusées / remplacées`, statut `remplacée`, ligne `- **Remplacée par :** « titre de NEW » (DATE).` ; NEW reste en place.
- `--project` accepte les mêmes formes que `action.py` (chemin du registre, dossier du projet, `client/mission`, libellé).
- Toute écriture accepte `--dry-run` et renvoie un `label` lisible (« validation de … ») avec le bloc obtenu.
- `--brain CHEMIN` ou `BRAIN_DIR` pour un autre brain ; `ACTION_NOW="AAAA-MM-JJ HH:MM"` fige l'horloge (tests).

## Quand l'agent l'utilise

- Un compte rendu ou une veille qui relève une décision la **propose** avec `propose` (source obligatoire) ; l'agent ne la valide pas.
- Seul le propriétaire du brain fait valider, refuser ou remplacer : `validate`, `refuse` et `replace` s'exécutent sur sa demande explicite, avec la date de sa décision (`--on`).
- Pour lire l'état des décisions d'un projet : `list` puis `show`, jamais une lecture du fichier à la main pour en déduire un statut.

## Garanties

- Écritures atomiques ; refus (code 4) si le registre a changé entre la lecture et l'écriture.
- Seuls le bloc déplacé et les lignes blanches de ses deux jonctions changent ; fins de ligne et retour final conservés.
- Les entrées doivent tenir sur une ligne, sans séparateur réservé, avec des dates réelles (`AAAA-MM-JJ`).
