"""Genera live/positioning.json dal Google Sheet scaricato (data/competitor-2026.xlsx).

La pagina legge questo file per la mappa di brand positioning: uscite per
competitor negli ultimi due report e follower Instagram. Il file viene
riscritto solo se i dati cambiano, così non partono commit e deploy a vuoto.
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/competitor-2026.xlsx")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "live/positioning.json")

# Nomi del foglio -> nomi brevi usati nella pagina
ALIASES = {"Zucchetti / Inrecruiting": "Inrecruiting"}
KNOWN = ["Factorial", "Personio", "TeamSystem", "StepsConnect", "Altamira",
         "nCore HR", "Teamtailor", "Inrecruiting", "Arca24"]

wb = openpyxl.load_workbook(SRC, data_only=True)

# Uscite dei competitor negli ultimi due report della scheda Storico Intelligence
rows = [r for r in wb["Storico Intelligence"].iter_rows(min_row=2, values_only=True)
        if r[0] and r[1] == "Competitor" and r[2]]
weeks = sorted({r[0] for r in rows})[-2:]
counts = Counter((ALIASES.get(r[2], r[2]), r[0]) for r in rows if r[0] in weeks)
names = KNOWN + sorted({n for n, _ in counts} - set(KNOWN))
prev_w = weeks[-2] if len(weeks) > 1 else None
now_w = weeks[-1]
activity = {n: {"prev": counts.get((n, prev_w), 0), "now": counts.get((n, now_w), 0)} for n in names}

# Follower Instagram: settimana precedente e dato aggiornato
instagram = {}
for r in wb["Follower Instagram"].iter_rows(min_row=4, values_only=True):
    if r[0] and str(r[0]).startswith("@") and r[1] is not None and r[2] is not None:
        instagram[r[0]] = [int(r[1]), int(r[2])]

# Data del report, dalla seconda riga della scheda Weekly Highlights
subtitle = str(wb["Weekly Highlights"].cell(row=2, column=1).value or "")
m = re.search(r"Generato il (\d{2}/\d{2}/\d{4} \d{2}:\d{2})", subtitle)

payload = {
    "reportDate": m.group(1) if m else None,
    "weeks": weeks,
    "activity": activity,
    "instagram": instagram,
}

old = json.loads(OUT.read_text()) if OUT.exists() else {}
if {k: v for k, v in old.items() if k != "updatedAt"} == payload:
    print("Nessuna variazione:", OUT)
    sys.exit(0)
payload["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print("Aggiornato:", OUT, payload["reportDate"], weeks)
