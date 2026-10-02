# machine/

Scripts d'installation et de contrôle de l'espace `Work/` sur une machine. Ils ne modifient jamais la configuration home (`~/.gitconfig`, `~/.ssh/`) et ne commitent ni ne poussent rien. Les lancer depuis la racine `Work/`.

| Fichier | Rôle |
|---|---|
| `install.sh` | Point d'entrée après le clone de `Work` : clone le brain privé (`--brain <url>`) ou en crée un vierge depuis brain-starter, `brain-perso/` en option (`--brain-perso <url\|new>`), renomme le remote Work-Starter en `starter`, puis lance `bootstrap.sh`. Relançable sans rien écraser. |
| `bootstrap.sh` | Prépare un checkout neuf : dossiers locaux, clone du brain privé (`BRAIN_REMOTE`), skills restaurés depuis `skills-lock.json`, liens vérifiés. |
| `update.sh` | Rafraîchit les skills tiers et signale l'état Git, sans commit ni push. |
| `link-skills.sh` | Crée les liens de découverte des skills maison pour Claude (`.claude/skills/`) et Codex (`.agents/skills/`). |
| `sync-house-skills.py` | Copie le skill `new-project` (sans symlink) dans les dossiers de découverte. |
| `check-links.sh` | Vérifie les liens du brain et des skills ; à lancer après un déplacement. |
| `check-no-client.sh` / `.py` | Scan manuel facultatif : cherche dans les fichiers publiables les noms de clients et de personnes connus du brain privé. Ne certifie rien. |
| `gitconfig.example` | Modèle de `~/.gitconfig` avec une identité par frontière de confiance, à recopier et adapter soi-même. |
