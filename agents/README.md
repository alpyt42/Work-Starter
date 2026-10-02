# agents/ — espace de travail des agents

> Le scratch des agents IA. Diaries de session, logs, plans, scripts de fabrication, brouillons, notes intermédiaires — tout ce qui sert à l'agent pendant qu'il bosse et qui n'est **pas destiné à être lu par un humain**. Ce n'est ni du contexte durable (→ `brain/`), ni du code pérenne (→ `repos/`), ni un output pour quelqu'un (→ `artifacts/`).

## Structure

Un dossier par projet, puis un dossier par session quand la session mérite d'être isolée :

```
agents/
├── <projet>/
│   └── YYYY-MM-DD-<slug-de-session>/
│       ├── diary.md
│       ├── plan.md
│       └── …
└── _cross/          # ce qui n'appartient à aucun projet
```

Le nom de projet suit celui du repo ou du projet de la mémoire concerné, pour que le rapprochement soit évident.

## Ici ou dans le repo ?

- **Par défaut : ici.** Le cas le plus fréquent — le travail touche plusieurs endroits.
- **Dans le repo** si le WIP est vraiment spécifique à un seul repo : alors un dossier gitignoré **dans** ce repo (`.agents/`, `scratch/`), clairement séparé du code.
- Les plans, scripts de build et rendus intermédiaires d'un livrable humain restent ici pendant l'itération ; seul le livrable et sa provenance vont dans `artifacts/`. Si le code de génération doit rester reconstructible après nettoyage de `agents/`, le promouvoir dans un repo adapté.

Dans les deux cas, ne jamais laisser traîner du scratch à la racine de l'espace de travail ni dans `brain/`.

## Rétention — **promote or lose it**

À part ce README suivi par Git, le contenu de ce dossier est **jetable** : il est ignoré par le dépôt `Work` et n'est pas garanti de survivre à un nettoyage.

Corollaire, la seule règle qui compte : **si quelque chose écrit ici devient durable, il faut le promouvoir avant la fin de la session** — une décision ou un compte-rendu vers la fiche projet ou un dossier de notes de `brain/`, de la doc technique vers le repo, un livrable vers `artifacts/`. Ce qui reste ici est considéré comme perdu d'avance.

Sans cette règle, cet espace redevient exactement le bordel qu'il est censé absorber — juste rangé dans un dossier.
