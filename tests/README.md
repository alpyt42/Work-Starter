# tests/

Tests des scripts de `tools/`, sans réseau ni données privées : `uv run --with pytest pytest tests/` depuis la racine `Work/`.

- `test_check_links.py` — contrôle de liens du brain.
- `test_client_repos.py` — catalogue et clonage des dépôts client.
- `test_brain_state.py` — fusion des états entre brains.
