#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Toggl Track en LECTURE SEULE (API v9) — aucune écriture possible, par construction.

Usage (depuis la racine de Work/) :
  uv run tools/toggl.py week [--offset N] [--json]        entrées de la semaine (N=-1 : semaine dernière)
  uv run tools/toggl.py summary --from AAAA-MM-JJ --to AAAA-MM-JJ [--json]
                                                          total d'heures par client / projet sur la période
  uv run tools/toggl.py projects [--json] [--refresh]     projets et clients (cache local 24 h)
  uv run tools/toggl.py boond [--offset N | --from … --to …] [--steps 20] [--json]
                                                          heures Toggl → proposition de jours Boond (rien n'est envoyé)

Token : variable TOGGL_API_TOKEN ou fichier tools/.env (ignoré par git).
Il n'est jamais affiché, écrit ailleurs ni passé en argument de commande.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.track.toggl.com/api/v9"
QUOTA = {"remaining": None, "resets_in": None, "calls": 0}
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".toggl-cache.json")   # ignoré par git
WORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN_DIR = os.path.abspath(os.environ.get("BRAIN_DIR", os.path.join(WORK, "brain")))
CACHE_TTL_S = 24 * 3600
JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def from_env_file(key: str) -> str:
    """Lit KEY=valeur dans tools/.env, sans l'afficher ni l'exporter."""
    try:
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ""


def token() -> str:
    tok = os.environ.get("TOGGL_API_TOKEN", "").strip() or from_env_file("TOGGL_API_TOKEN")
    if not tok:
        sys.exit("✗ Token Toggl introuvable. Renseigne TOGGL_API_TOKEN dans tools/.env ou dans l'environnement.")
    return tok


def get(path: str, params: dict | None = None):
    """Seule fonction réseau du script : GET uniquement."""
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    auth = base64.b64encode(f"{token()}:api_token".encode()).decode()
    req = urllib.request.Request(url, method="GET",
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                QUOTA["remaining"] = r.headers.get("X-Toggl-Quota-Remaining")
                QUOTA["resets_in"] = r.headers.get("X-Toggl-Quota-Resets-In")
                QUOTA["calls"] += 1
                return json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            if e.code == 402:                      # quota horaire du plan gratuit épuisé
                reset = e.headers.get("X-Toggl-Quota-Resets-In")
                sys.exit("✗ Quota Toggl épuisé (plan gratuit : 30 requêtes / heure)"
                         + (f" — réinitialisé dans {int(reset) // 60} min." if reset and reset.isdigit() else "."))
            if e.code == 429 and attempt < 2:      # limite de débit courte : on patiente puis on réessaie
                time.sleep(2 * (attempt + 1))
                continue
            if e.code in (401, 403):
                sys.exit("✗ Toggl refuse l'accès (401/403) : token invalide ou révoqué.")
            sys.exit(f"✗ Erreur Toggl {e.code} sur {path}")
        except urllib.error.URLError as e:
            sys.exit(f"✗ Toggl injoignable : {e.reason}")
    sys.exit("✗ Toggl : trop de requêtes, réessaie dans une minute.")


def local(ts: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone() if ts else None


def seconds(entry: dict) -> int:
    """Durée en secondes ; une entrée en cours a une durée négative → calculée jusqu'à maintenant."""
    d = entry.get("duration") or 0
    if d < 0:
        start = local(entry.get("start"))
        return int((dt.datetime.now().astimezone() - start).total_seconds()) if start else 0
    return int(d)


def hm(s: int) -> str:
    return f"{s // 3600}h{(s % 3600) // 60:02d}"


def catalog(refresh: bool = False):
    """Projets et clients (cache local 24 h pour économiser le quota ; --refresh pour forcer)."""
    if not refresh:
        try:
            with open(CACHE_FILE, encoding="utf-8") as fh:
                c = json.load(fh)
            if time.time() - c.get("at", 0) < CACHE_TTL_S:
                return ({int(k): v for k, v in c["projects"].items()}, {int(k): v for k, v in c["clients"].items()})
        except (FileNotFoundError, ValueError, KeyError):
            pass
    projects = {p["id"]: p for p in (get("/me/projects", {"include_archived": "true"}) or [])}
    clients = {c["id"]: c for c in (get("/me/clients") or [])}
    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump({"at": time.time(), "projects": projects, "clients": clients}, fh, ensure_ascii=False)
    os.chmod(CACHE_FILE, 0o600)
    return projects, clients


def entries(start: dt.date, end: dt.date):
    """Entrées entre start (inclus) et end (inclus)."""
    return get("/me/time_entries", {"start_date": start.isoformat(),
                                    "end_date": (end + dt.timedelta(days=1)).isoformat(),
                                    "meta": "true"}) or []


def label(entry):
    """Client / projet depuis les métadonnées de l'entrée (meta=true) — aucune requête en plus."""
    return (entry.get("client_name") or "(sans client)"), (entry.get("project_name") or "(sans projet)")


def cmd_week(args):
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=args.offset)
    sunday = monday + dt.timedelta(days=6)
    rows = []
    for e in sorted(entries(monday, sunday), key=lambda e: e.get("start") or ""):
        client, project = label(e)
        start, stop = local(e.get("start")), local(e.get("stop"))
        rows.append({"date": start.date().isoformat() if start else "", "start": start.strftime("%H:%M") if start else "",
                     "stop": stop.strftime("%H:%M") if stop else "en cours", "duree_s": seconds(e),
                     "client": client, "projet": project, "description": e.get("description") or "",
                     "tags": e.get("tags") or [], "billable": bool(e.get("billable"))})
    if args.json:
        print(json.dumps({"du": monday.isoformat(), "au": sunday.isoformat(), "entrees": rows}, ensure_ascii=False, indent=2))
        return
    print(f"Semaine du {monday:%d/%m} au {sunday:%d/%m/%Y} — {len(rows)} entrées, total {hm(sum(r['duree_s'] for r in rows))}")
    day = None
    for r in rows:
        if r["date"] != day:
            day = r["date"]
            tot = sum(x["duree_s"] for x in rows if x["date"] == day)
            print(f"\n{JOURS[dt.date.fromisoformat(day).weekday()]} {dt.date.fromisoformat(day):%d/%m}  ({hm(tot)})")
        print(f"  {r['start']}-{r['stop']:>8}  {hm(r['duree_s']):>6}  {r['client']} / {r['projet']} — {r['description']}")


def cmd_summary(args):
    start, end = dt.date.fromisoformat(args.date_from), dt.date.fromisoformat(args.date_to)
    if end < start:
        sys.exit("✗ --to est avant --from")
    agg: dict[tuple, int] = {}
    for e in entries(start, end):
        k = label(e)
        agg[k] = agg.get(k, 0) + seconds(e)
    total = sum(agg.values())
    rows = [{"client": c, "projet": p, "duree_s": s, "part": round(100 * s / total, 1) if total else 0}
            for (c, p), s in sorted(agg.items(), key=lambda kv: -kv[1])]
    if args.json:
        print(json.dumps({"du": start.isoformat(), "au": end.isoformat(), "total_s": total, "lignes": rows}, ensure_ascii=False, indent=2))
        return
    print(f"Du {start:%d/%m/%Y} au {end:%d/%m/%Y} — total {hm(total)}\n")
    for r in rows:
        print(f"  {hm(r['duree_s']):>7}  {r['part']:>5}%  {r['client']} / {r['projet']}")


def cmd_projects(args):
    projects, clients = catalog(refresh=args.refresh)
    rows = sorted(({"client": clients[p["client_id"]]["name"] if p.get("client_id") in clients else "(sans client)",
                    "projet": p["name"], "actif": bool(p.get("active")), "id": p["id"]} for p in projects.values()),
                  key=lambda r: (r["client"], r["projet"]))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    for r in rows:
        print(f"  {'•' if r['actif'] else '○'} {r['client']} / {r['projet']}  (id {r['id']})")


MAPPING_FILE = os.path.join(BRAIN_DIR, ".data", "boond-mapping.json")


def allocate(minutes: dict, n: int, carry: dict) -> dict:
    """Répartit n pas de la journée au prorata des minutes (plus forts restes ; égalité → plus d'heures).
    L'écart d'arrondi de chaque ligne (carry, mis à jour) est reporté sur le jour suivant où elle apparaît,
    pour que les totaux de la période restent au plus près de Toggl."""
    total = sum(minutes.values())
    if not total:
        return {}
    raw = {k: n * m / total + carry.get(k, 0) for k, m in minutes.items()}
    out = {k: max(0, int(v // 1)) for k, v in raw.items()}
    rest = lambda k: (raw[k] - out[k], minutes[k])
    while sum(out.values()) < n:
        for k in sorted(raw, key=rest, reverse=True)[:n - sum(out.values())]:
            out[k] += 1
    while sum(out.values()) > n:
        out[min((k for k in out if out[k]), key=rest)] -= 1
    for k in raw:
        carry[k] = raw[k] - out[k]
    return {k: v for k, v in out.items() if v}


def cmd_boond(args):
    """Heures Toggl → jours Boond (1 j par jour travaillé, par pas de 1/steps). Lecture seule, rien n'est envoyé à Boond."""
    if args.date_from:
        start = dt.date.fromisoformat(args.date_from)
        end = dt.date.fromisoformat(args.date_to) if args.date_to else start + dt.timedelta(days=4)
    else:
        today = dt.date.today()
        start = today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=args.offset)
        end = start + dt.timedelta(days=4)
    try:
        with open(MAPPING_FILE, encoding="utf-8") as fh:
            raw_map = json.load(fh)
    except FileNotFoundError:
        raw_map = {}
    mapping = {k: v for k, v in raw_map.items() if not k.startswith("_")}
    lines = raw_map.get("_boond_lignes", {})
    projets = [l for l in lines.get("projets", []) if l not in ("Absence", "Interne")]
    interne = lines.get("interne", [])

    def resolve(key: str):
        """1) correspondance explicite · 2) code mission MISxxxx ou libellé Boond dans le nom Toggl · 3) ligne Interne homonyme."""
        if mapping.get(key):
            return mapping[key]
        client, _, project = key.partition(" / ")
        low = key.lower()
        for line in projets:
            code = next((w for w in line.replace("-", " ").split() if w.startswith("MIS") and w[3:].isdigit()), None)
            if (code and code.lower() in low) or line.lower() in (project.lower(), low):
                return line
        for name in interne:
            if project.lower() == name.lower():
                return f"Interne - {name}"
        return None
    per_day: dict[str, dict] = {}
    unmapped: dict[str, int] = {}
    weekend: dict[str, int] = {}
    for e in entries(start, end):
        s = local(e.get("start"))
        if not s:
            continue
        key = " / ".join(label(e))
        line = resolve(key) or f"(non mappé) {key}"
        if not resolve(key):
            unmapped[key] = unmapped.get(key, 0) + seconds(e)
        if s.weekday() >= 5:
            weekend[s.date().isoformat()] = weekend.get(s.date().isoformat(), 0) + seconds(e)
            continue
        per_day.setdefault(s.date().isoformat(), {})
        per_day[s.date().isoformat()][line] = per_day[s.date().isoformat()].get(line, 0) + seconds(e) // 60
    days, totals, dropped, carry = [], {}, [], {}
    d = start
    while d <= end:
        if d.weekday() < 5:
            mins = per_day.get(d.isoformat(), {})
            q = allocate(mins, args.steps, carry)
            for line, m in mins.items():
                if line not in q:
                    dropped.append((d.isoformat(), line, m))
            for line, v in q.items():
                totals[line] = totals.get(line, 0) + v
            days.append({"date": d.isoformat(), "heures_s": 60 * sum(mins.values()), "minutes": mins,
                         "jours": {line: round(v / args.steps, 4) for line, v in sorted(q.items(), key=lambda kv: -kv[1])}})
        d += dt.timedelta(days=1)
    if args.json:
        print(json.dumps({"du": start.isoformat(), "au": end.isoformat(), "pas": 1 / args.steps, "jours": days,
                          "totaux": {k: round(v / args.steps, 4) for k, v in totals.items()},
                          "non_mappe_s": unmapped, "week_end_s": weekend,
                          "ecrases": [{"date": a, "ligne": b, "minutes": c} for a, b, c in dropped]},
                         ensure_ascii=False, indent=2))
        return
    fmt = lambda x: f"{x:g}".replace(".", ",")
    print(f"Proposition Boond du {start:%d/%m} au {end:%d/%m/%Y} (pas de {fmt(1 / args.steps)} j) — rien n'est envoyé à Boond\n")
    for day in days:
        dd = dt.date.fromisoformat(day["date"])
        if not day["jours"]:
            print(f"  {JOURS[dd.weekday()]} {dd:%d/%m}  —  (aucune heure Toggl)")
            continue
        parts = " · ".join(f"{line} {fmt(v)}" for line, v in day["jours"].items())
        print(f"  {JOURS[dd.weekday()]} {dd:%d/%m}  ({hm(day['heures_s'])})  {parts}")
    total_days = sum(totals.values()) / args.steps
    print(f"\nTotal : {fmt(total_days)} j")
    for line, v in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {fmt(v / args.steps):>5} j  {100 * v / sum(totals.values()):5.1f} %  {line}")
    if dropped:
        print("\n⚠️ Temps inférieur à un pas, écrasé à 0 :")
        for a, b, c in dropped:
            print(f"  {dt.date.fromisoformat(a):%d/%m}  {c} min  {b}")
    if unmapped:
        print("\n⚠️ Projets Toggl sans ligne Boond — demander la ligne à l'utilisateur, puis l'ajouter dans brain/.data/boond-mapping.json"
              " (ou mettre le code MISxxxx dans le nom du projet Toggl) :")
        for k, s in unmapped.items():
            print(f"  {hm(s)}  {k}")
    if weekend:
        print("\n⚠️ Heures le week-end (non réparties) : " + ", ".join(f"{k} {hm(v)}" for k, v in weekend.items()))


def main():
    ap = argparse.ArgumentParser(description="Toggl Track en lecture seule (API v9).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("week", help="entrées de la semaine")
    w.add_argument("--offset", type=int, default=0, help="0 = semaine en cours, -1 = semaine dernière…")
    w.add_argument("--json", action="store_true")
    s = sub.add_parser("summary", help="total par client / projet sur une période")
    s.add_argument("--from", dest="date_from", required=True)
    s.add_argument("--to", dest="date_to", required=True)
    s.add_argument("--json", action="store_true")
    p = sub.add_parser("projects", help="projets et clients")
    p.add_argument("--json", action="store_true")
    p.add_argument("--refresh", action="store_true", help="ignorer le cache local (2 requêtes)")
    b = sub.add_parser("boond", help="heures Toggl → proposition de jours Boond (lecture seule)")
    b.add_argument("--offset", type=int, default=0, help="semaine : 0 = en cours, -1 = dernière…")
    b.add_argument("--from", dest="date_from", help="début (AAAA-MM-JJ), à la place de --offset")
    b.add_argument("--to", dest="date_to", help="fin incluse (défaut : début + 4 jours)")
    b.add_argument("--steps", type=int, default=20, help="découpage d'une journée (20 = pas de 0,05 j, le minimum Boond)")
    b.add_argument("--json", action="store_true")
    args = ap.parse_args()
    {"week": cmd_week, "summary": cmd_summary, "projects": cmd_projects, "boond": cmd_boond}[args.cmd](args)
    # quota sur stderr pour ne pas polluer la sortie (ni le --json)
    if QUOTA["calls"]:
        rem, reset = QUOTA["remaining"], QUOTA["resets_in"]
        msg = f"· Toggl : {QUOTA['calls']} requête(s) utilisée(s)"
        if rem is not None:
            msg += f", quota restant {rem}" + (f" (réinitialisé dans {int(reset) // 60} min)" if reset and reset.isdigit() else "")
        print(msg, file=sys.stderr)
    else:
        print("· Toggl : 0 requête (cache local)", file=sys.stderr)


if __name__ == "__main__":
    main()
