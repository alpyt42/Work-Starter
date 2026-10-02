#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Renomme ou crée des projets Toggl Track — et RIEN d'autre (ni suppression, ni archivage, ni entrée de temps).

Usage (depuis la racine de Work/) :
  uv run tools/toggl_projects.py            affiche le plan (à blanc, 0 requête : lit le cache de toggl.py)
  uv run tools/toggl_projects.py --apply    exécute le plan — uniquement sur GO explicite de l'utilisateur

Plan : brain/.data/toggl-projects-plan.json
  "renommer": {"<project_id>": {"de": "<nom actuel>", "vers": "<nouveau nom>"}}
  "creer":    [{"client": "<client Toggl existant>", "nom": "<nom du projet>"}]
Garde-fous : renommage seulement si le nom actuel est encore exactement « de » ; création seulement si
aucun projet de ce nom n'existe déjà chez ce client (actif ou archivé) et si le client existe.
Coût : 1 requête par action + 2 pour rafraîchir le cache (quota gratuit : 30 / heure).
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_DIR = os.path.abspath(os.environ.get("BRAIN_DIR", os.path.join(os.path.dirname(HERE), "brain")))
PLAN_FILE = os.path.join(BRAIN_DIR, ".data", "toggl-projects-plan.json")
_spec = importlib.util.spec_from_file_location("toggl", os.path.join(HERE, "toggl.py"))
toggl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(toggl)          # réutilise token(), catalog(), le cache et le quota de toggl.py


def write(method: str, path: str, body: dict) -> None:
    """Seules écritures du script : PUT (renommer) et POST (créer) sur les projets d'un workspace."""
    assert method in ("PUT", "POST") and "/projects" in path
    url = f"{toggl.API}{path}"
    auth = base64.b64encode(f"{toggl.token()}:api_token".encode()).decode()
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            toggl.QUOTA["remaining"] = r.headers.get("X-Toggl-Quota-Remaining")
            toggl.QUOTA["calls"] += 1
    except urllib.error.HTTPError as e:
        if e.code == 402:
            sys.exit("✗ Quota Toggl épuisé — réessaie plus tard (le reste du plan n'a pas été exécuté).")
        sys.exit(f"✗ Erreur Toggl {e.code} sur {method} {path} — arrêt (la suite du plan n'a pas été exécutée).")


def main():
    ap = argparse.ArgumentParser(description="Renommer / créer des projets Toggl (plan à blanc par défaut).")
    ap.add_argument("--apply", action="store_true", help="exécuter le plan (sinon : affichage seulement)")
    args = ap.parse_args()
    with open(PLAN_FILE, encoding="utf-8") as fh:
        plan = json.load(fh)
    projects, clients = toggl.catalog(refresh=args.apply)      # à blanc : cache ; --apply : état frais de Toggl
    cname = lambda cid: clients.get(cid, {}).get("name", "(sans client)")
    todo = []
    print("Renommer :")
    for pid, step in plan.get("renommer", {}).items():
        p = projects.get(int(pid))
        if not p:
            print(f"  ✗ projet {pid} introuvable — ignoré"); continue
        if p["name"] == step["vers"]:
            print(f"  = {cname(p.get('client_id'))} / {p['name']}  (déjà fait)"); continue
        if p["name"] != step["de"]:
            print(f"  ✗ {cname(p.get('client_id'))} / {p['name']} : nom actuel ≠ « {step['de']} » — ignoré"); continue
        todo.append(("PUT", f"/workspaces/{p['workspace_id']}/projects/{p['id']}", {"name": step["vers"]}))
        print(f"  {'→' if args.apply else '·'} {cname(p.get('client_id'))} / {p['name']}  ⟶  {step['vers']}")
    print("Créer :")
    wid = next(iter(projects.values()))["workspace_id"] if projects else None
    by_name = {c["name"]: cid for cid, c in clients.items()}
    for item in plan.get("creer", []):
        cid = by_name.get(item["client"])
        if not cid:
            print(f"  ✗ client « {item['client']} » introuvable — ignoré (le créer d'abord dans Toggl)"); continue
        if any(p["name"] == item["nom"] and p.get("client_id") == cid for p in projects.values()):
            print(f"  = {item['client']} / {item['nom']}  (existe déjà)"); continue
        todo.append(("POST", f"/workspaces/{wid}/projects", {"name": item["nom"], "client_id": cid, "active": True}))
        print(f"  {'→' if args.apply else '·'} {item['client']} / {item['nom']}")
    if not todo:
        print("\nRien à faire.")
    elif not args.apply:
        print(f"\nÀ blanc : {len(todo)} action(s), rien n'a été modifié. Exécution : --apply (sur GO de l'utilisateur).")
    else:
        for method, path, body in todo:
            write(method, path, body)
        toggl.catalog(refresh=True)
        print(f"\n✓ {len(todo)} action(s) exécutée(s) ; cache rafraîchi.")
    if toggl.QUOTA["calls"]:
        print(f"· Toggl : {toggl.QUOTA['calls']} requête(s), quota restant {toggl.QUOTA['remaining']}", file=sys.stderr)


if __name__ == "__main__":
    main()
