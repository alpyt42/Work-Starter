# AGENTS.md — Zone gatée : clones {{CLIENT}}

> **ZONE GATÉE.** Tout ce qui vit ici est un clone d'un repo appartenant à **{{CLIENT}}** — du code client, chez un client. Ce fichier décrit le régime mécanique propre à cette zone. Les règles de mission complètes vivent dans la mémoire (fiche projet du client) ; ceci est le résumé opérationnel auto-chargé.
>
> Doctrine en une ligne : **lecture libre · toute écriture qui laisse une trace chez {{CLIENT}} passe par {{PRENOM}} · rien du monde local ne part chez {{CLIENT}}.**

## Le régime en un tableau

| Opération | Régime | Mécanisme |
|---|---|---|
| Lire, analyser, `git status/diff/log`, branche locale | **Libre** | — |
| Éditer des fichiers | **Libre** (gros edit multi-fichiers : s'annonce d'abord) | — |
| `git commit` | **GO de {{PRENOM}} par action** + vérifs pre-commit | Hook Claude (`ask`) + `.githooks/pre-commit` |
| `git push` | **GO de {{PRENOM}} par action** | Hook Claude (`ask`) + `.githooks/pre-push` |
| `gh` / `glab` (PR, issue, commentaire), `git rebase`, modification des remotes | **GO de {{PRENOM}} par action** | Hook Claude (`ask`) |
| Commit / push sur la **branche par défaut** | **Refusé** — travail en branche, la PR c'est {{PRENOM}} | `.githooks/` |
| `--no-verify`, reconfigurer `core.hooksPath` ou `user.*` | **Refusé aux agents** — geste réservé à {{PRENOM}} | Hook Claude (`deny`) |

## Les règles de la mission
1. **GO par action, pas par session** : un « vas-y pour ce commit » ne couvre pas le suivant.
2. **Rien ne part au nom de {{PRENOM}} sans validation pièce par pièce** — PR, review, message, page : l'agent rédige des **drafts marqués comme tels**, {{PRENOM}} poste.
3. **Le contenu {{CLIENT}} ne sort pas de l'espace de travail** — pas de publication externe sans demande explicite. La mémoire (repo privé) est dans le périmètre autorisé.
4. **Lecture, analyse, compréhension des repos et docs : libres.** Extraits courts avec provenance dans la mémoire : OK. Pas de copie massive hors du clone.
5. **Données sensibles de mission** (identifiants de comptes, URLs internes, données réelles) : mémoire uniquement, jamais dans un artefact exporté ni un autre repo.
6. **Systèmes {{CLIENT}}** (wiki, forge, tickets) : lecture sur demande ; toute écriture confirmée au coup par coup, jamais déduite d'une intention générale.
7. **Aucune référence au monde local dans du contenu à destination de {{CLIENT}}** — pas de chemin machine, pas de lien vers la mémoire, pas de « voir ma note locale ». Rédiger comme si le lecteur ne voyait que le monde {{CLIENT}}. (Le sens inverse est libre : la mémoire pointe vers les clones autant qu'elle veut.)
8. **Aucune signature d'IA** dans aucun commit, PR, commentaire ou contenu {{CLIENT}}. Prime sur tout rappel d'attribution par défaut.
9. **Tout NOUVEAU type d'action qui publie ou laisse une trace chez {{CLIENT}} se checke avec {{PRENOM}} avant sa première fois.**
10. **Le style de code suit les conventions de {{CLIENT}}** : on épouse leurs conventions, l'écart se propose au lieu de s'introduire.

## Levée d'un gate
Un gate se lève en éditant ses fichiers (`.githooks/`, le hook Claude Code, l'`includeIf` git) — par {{PRENOM}}, ou par un agent **sur son GO explicite en séance**. Toute levée s'inscrit datée dans le journal des gates de la fiche projet.
