# .kit-options/

Options installables à la demande, jamais actives par défaut.

- [`gated-zone/`](gated-zone/README.md) — zone gatée pour les clones client : hooks Git qui refusent les références locales et les publications non demandées. À proposer une fois avant le premier commit d'un nouveau client.
- `check-no-local-refs.sh` — cherche les chemins machine et les pointeurs vers `brain/` ou `repos/` avant de pousser un dépôt partagé.
