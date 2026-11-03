"""Genera live/linkedin.json dai post LinkedIn raccolti con Apify.

Fonte, in ordine di preferenza:
  1. ultima esecuzione riuscita del task Apify APIFY_TASK_ID (serve APIFY_TOKEN);
  2. il dataset APIFY_DATASET_ID (leggibile anche senza token, se Apify lo consente).

Conta i post di ogni azienda negli ultimi 7 giorni e nei 7 precedenti, con
like, commenti e condivisioni. La pagina usa questi numeri al posto del foglio
quando Apify copre abbastanza competitor. Il file viene riscritto solo se
cambia qualcosa oltre all'orario.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "live/linkedin.json")
TOKEN = os.environ.get("APIFY_TOKEN") or None
TASK = os.environ.get("APIFY_TASK_ID") or None
DATASET = os.environ.get("APIFY_DATASET_ID") or None

# Nome della pagina LinkedIn (universalName) -> nome usato nella pagina
COMPANIES = {
    "cving": "CVing", "factorialai": "Factorial", "factorial": "Factorial", "personio": "Personio",
    "teamsystem": "TeamSystem", "teamtailor": "Teamtailor", "altamira-srl": "Altamira",
    "ncorehr": "nCore HR", "in-recruiting-worldwide": "Inrecruiting", "inrecruiting": "Inrecruiting",
    "arca24": "Arca24", "stepsconnect": "StepsConnect",
}
COMPETITORS = ["Factorial", "Personio", "TeamSystem", "StepsConnect", "Altamira",
               "nCore HR", "Teamtailor", "Inrecruiting", "Arca24"]


def get(path):
    # Token nell'header, mai nell'URL: così non finisce nei log
    headers = {"Authorization": "Bearer " + TOKEN} if TOKEN else {}
    req = urllib.request.Request("https://api.apify.com/v2" + path, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def company_of(item):
    """Azienda del post: dall'autore o, in mancanza, dalla pagina interrogata."""
    name = (item.get("author") or {}).get("universalName")
    if not name:
        url = (item.get("query") or {}).get("targetUrl", "")
        parts = url.split("/company/")
        name = parts[1].split("/")[0] if len(parts) > 1 else None
    return COMPANIES.get((name or "").lower(), name)


try:
    if TOKEN and TASK:
        items, source = get(f"/actor-tasks/{TASK}/runs/last/dataset/items?status=SUCCEEDED&clean=1"), f"task {TASK}"
    elif DATASET:
        items, source = get(f"/datasets/{DATASET}/items?clean=1"), f"dataset {DATASET}"
    else:
        sys.exit("Nessuna fonte Apify configurata: imposta APIFY_TASK_ID (con APIFY_TOKEN) o APIFY_DATASET_ID.")
except urllib.error.HTTPError as e:
    # Fonte non raggiungibile: si tiene il file precedente, senza far fallire il workflow
    print(f"Apify non raggiungibile (HTTP {e.code}): lascio invariato {OUT}")
    sys.exit(0)

now = datetime.now(timezone.utc)
week_ago, two_weeks_ago = now - timedelta(days=7), now - timedelta(days=14)
activity, covered = {}, set()
for it in items:
    if it.get("type") not in (None, "post"):
        continue
    name = company_of(it)
    if not name:
        continue
    covered.add(name)
    raw = (it.get("postedAt") or {}).get("date")
    if not raw:
        continue
    when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if when < two_weeks_ago:
        continue
    a = activity.setdefault(name, {"prev": 0, "now": 0, "likes": 0, "comments": 0, "shares": 0})
    a["now" if when >= week_ago else "prev"] += 1
    eng = it.get("engagement") or {}
    for k in ("likes", "comments", "shares"):
        a[k] += int(eng.get(k) or 0)

# Le aziende interrogate ma senza post recenti contano zero, non "mancanti"
for name in covered:
    activity.setdefault(name, {"prev": 0, "now": 0, "likes": 0, "comments": 0, "shares": 0})

payload = {
    "source": "linkedin-apify",
    "from": source,
    "windowDays": 7,
    "covered": sorted(covered),
    "competitorsCovered": len([c for c in COMPETITORS if c in covered]),
    "activity": dict(sorted(activity.items())),
}
old = json.loads(OUT.read_text()) if OUT.exists() else {}
if {k: v for k, v in old.items() if k != "updatedAt"} == payload:
    print("Nessuna variazione:", OUT)
    sys.exit(0)
payload["updatedAt"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(f"Aggiornato {OUT}: {len(items)} post da {source}, aziende coperte: {', '.join(sorted(covered)) or 'nessuna'}")
