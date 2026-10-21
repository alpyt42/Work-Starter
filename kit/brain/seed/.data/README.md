# .data/

États et réglages privés de ce brain et de ses skills. Versionnés avec le brain, jamais cités dans un dépôt d'outillage public. Aucun secret ici : les jetons vont dans un `.env` ignoré de l'espace de travail.

| Fichier | Rôle | Skill ou outil |
|---|---|---|
| `brain.json` | périmètre du brain : `scope`, `description` (ce qu'il contient et ne doit jamais contenir), `remote` et `email` attendus (motifs `fnmatch`), `allow` (noms de clients d'un autre brain autorisés ici) | agents, `brain-state.py brains`, `check-no-client.py`, doctor de la machine |
| `work-config.json` | skills de tiers à installer (`skills.thirdParty`) et skills désactivés (`skills.disabled`) | `tools/machine/work_config.py`, `update.sh` |
| `doctor.json` | nom d'affichage du propriétaire, utilisé par les contrôles et outils de pilotage | `brain-clean`, outils du brain |
| `local-paths.json` | brains attendus et dossiers d'entrée hors de l'espace, relatifs à `$HOME` (réglages de la personne : seul le brain par défaut `brain/` les porte) | `brain-state.py`, `cr-reunion` |
| `transcripts.json` | transcripts déjà traités, doublons ou exclus | `cr-reunion` |
| `messages-state.json` | curseurs et identifiants de messages traités | `veille-messages` |
| `client-repos.json` | catalogue privé des URLs Git client (voir [`kit/brain/docs/REPOSITORIES.md`](../../kit/brain/docs/REPOSITORIES.md)) | `tools/repos/client-repos.py` |

Un skill privé de ce brain ([`skills/`](../skills/README.md)) peut ajouter son propre fichier d'état ici ; il le crée lui-même et le déclare dans ce tableau. L'état d'un skill s'écrit toujours dans le `.data/` du brain où il écrit.
