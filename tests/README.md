# tests/

Tests des scripts de `tools/`, sans service distant ni données privées, sur des espaces `Work/` temporaires : `uv run --with pytest --with markdown-it-py pytest tests/` depuis la racine `Work/`. Les tests de l'interface ouvrent seulement un port éphémère sur `127.0.0.1`.

- `test_check_links.py` — contrôle de liens du brain, dont les liens vers un autre brain.
- `test_client_repos.py` — catalogue et clonage des dépôts client.
- `test_brain_state.py` — liste des brains (périmètre, description) et fusion des états entre brains.
- `test_new_brain.py` — création d'un brain vierge depuis `kit/brain/seed/` et de sa frontière (`.data/brain.json`).
- `test_brain_boundaries.py` — frontières entre brains : noms de clients d'un autre brain (`check-no-client.py`), hook `brain-pre-commit` et formulaire d'ajout d'action.
- `test_action.py`, `test_action_board.py`, `test_decision.py` — registres, vues et transitions des actions et décisions.
- `test_tasks_web.py` — interface locale, API, recherche documentaire et vue Git.
- `test_machine_doctor.py` — diagnostic de la machine : brains, configuration des skills, liens, frontière de chaque brain.
- `test_work_config.py` — couches de configuration des skills (défauts, brains, local), lock, `adopt`, empreinte.
- `test_link_skills.py` — `link-skills.sh` et `sync-house-skills.py` : liens et copies de skills de plusieurs brains, skills tiers, nettoyage.
