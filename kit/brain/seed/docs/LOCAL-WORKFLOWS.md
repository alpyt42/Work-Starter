# Paramètres locaux des workflows

Les procédures réutilisables (scripts et skills publics) vivent dans l'espace de travail ; seuls les skills privés propres à ce brain vivent dans [`skills/`](../skills/README.md). Ce document ne garde que les paramètres propres à ce brain et les exceptions confirmées par le propriétaire. Les états suivis par Git sont dans `.data/` ([`README`](../.data/README.md)) ; les jetons d'API restent dans un `.env` ignoré de l'espace de travail, lu seulement par les scripts.

## Emplacement du checkout

- Racine de l'espace : (à compléter, par exemple `~/Work/`), avec le brain dans `brain/`. Les scripts de l'espace trouvent `brain/` à côté de `tools/` ; `BRAIN_DIR` force un autre emplacement.

## Réunions

- Transcripts à lire : le dossier `transcripts_dir` de [`.data/local-paths.json`](../.data/local-paths.json) (chemin relatif à `$HOME`, hors de l'espace, jamais cité dans un Markdown). Enregistrements audio : `recordings_dir` ; ne pas les ouvrir, déplacer ou supprimer sans demande explicite.
- Le transcript et l'audio restent à leur emplacement ; seul le CR Markdown entre dans le brain, avec une provenance décrite en mots (outil, enregistreur, date). Suivi des fichiers traités : `.data/transcripts.json`.
- Format d'une ligne de transcript : (à compléter selon l'outil d'enregistrement).

## Messages

- Curseurs et identifiants traités : `.data/messages-state.json`.
- Exceptions de tri : (aucune pour l'instant).
