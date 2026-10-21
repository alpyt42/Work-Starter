# {{BRAIN}}

Mémoire Markdown privée pour le travail assisté par agents. Ce dépôt ne contient que les données de son propriétaire : profil, projets, personnes, sources, registres et états des skills. Les conventions, guides et modèles vivent dans l'espace de travail, sous [`../kit/brain/`](../kit/brain/AGENTS.md), et se mettent à jour avec lui.

## Démarrer

1. Déclarer le périmètre de ce brain dans [`.data/brain.json`](.data/brain.json) (ce qu'il contient et ne doit jamais contenir : les agents s'en servent pour choisir le brain où écrire), renseigner le profil et la voix dans [`me/about-me.md`](me/about-me.md), puis le nom d'affichage du propriétaire dans [`.data/doctor.json`](.data/doctor.json).
2. Ouvrir l'espace de travail complet dans Obsidian. [`tasks.md`](tasks.md) est la page de pilotage ; [`inbox.md`](inbox.md) et [`inbox/`](inbox/README.md) reçoivent les captures à trier.
3. Créer un premier client ou projet à partir des [modèles](../kit/brain/templates/README.md). Le projet interne [`setup`](projects/internal/setup/setup.md) suit la maintenance du système.
4. Configurer un remote **privé** avant toute publication : un brain accumule du contexte professionnel et ne doit jamais devenir public.

## Carte

- [`tasks.md`](tasks.md) — vue calculée des actions de tous les projets.
- [`inbox.md`](inbox.md) et [`inbox/`](inbox/README.md) — capture brute avant classement.
- [`me/about-me.md`](me/about-me.md) — profil, préférences et voix du propriétaire.
- [`projects/`](projects/README.md) — clients, missions et projets internes.
- [`people/`](people/README.md) — fiches professionnelles sourcées.
- [`docs/LOCAL-WORKFLOWS.md`](docs/LOCAL-WORKFLOWS.md) — chemins privés et exceptions locales.
- [`skills/`](skills/README.md) — skills privés de ce brain.
- [`.data/`](.data/README.md) — périmètre (`brain.json`), états et réglages privés.
