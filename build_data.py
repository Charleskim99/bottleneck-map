# -*- coding: utf-8 -*-
"""intro-funnel 실행 결과를 웹 앱이 읽는 JSON으로 내보낸다. 공개 서지·초록 문장만 담고 비공개 용어는 검사한다.

실행:  PYTHONUTF8=1 python build_data.py        -> data/bottlenecks.json, data/radar.json, data/refs.json, data/meta.json
"""
import csv
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
IF = os.path.dirname(HERE)                                    # Dropbox/intro-funnel
SK = os.path.join(os.path.expanduser("~"), ".claude", "skills", "intro-funnel", "scripts")
sys.path.insert(0, SK)
from lite import bottleneck as bn, oa   # noqa: E402

R3 = os.path.join(IF, "lm-bottleneck", "runs", "20261014-0814")
R2 = os.path.join(IF, "field-radar", "runs", "20260926-0044")
R1 = os.path.join(IF, "lm-particle-ink", "runs", "20260920-1724")
OUT = os.path.join(HERE, "data")
os.makedirs(OUT, exist_ok=True)
DENY = ["polydopamine", "pda-lm", "pda@lm", "catechol-gallium", "dopamine hydrochloride", "da-hcl", "sintering-free", "pdrn", "nce9080@"]


def jload(p):
    return json.load(io.open(p, encoding="utf-8"))


def jdump(name, obj):
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    low = text.lower()
    hits = [d for d in DENY if d in low]
    if hits:
        raise SystemExit(f"비공개 용어가 들어 있어 내보내지 않습니다: {name} {hits}")
    io.open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n").write(text)
    print(f"{name}: {len(text) // 1024} KB")


# ------------------------------------------------------------------ 1. 병목 지도
store = jload(os.path.join(R3, "bn", "sentences.json"))
items = store["items"]
by_sid = {r["sid"]: r for r in items}
clusters = bn.cluster(items, overlap=0.6)
recent_from = oa._months_ago(24)
rows = bn.table_rows(clusters, recent_from=recent_from, min_papers=3)
sens = jload(os.path.join(R3, "bn", "sensitivity.json")) if os.path.exists(os.path.join(R3, "bn", "sensitivity.json")) else {}
ft = jload(os.path.join(IF, "report", "midterm", "fulltext_check.json")) if os.path.exists(os.path.join(IF, "report", "midterm", "fulltext_check.json")) else []
ft_by_doi = {x["doi"]: x for x in ft if not x.get("status")}
works = jload(os.path.join(R3, "bn", "works.json"))


def ev_item(r):
    return {"sid": r["sid"], "kind": r.get("label_kind"), "quote": r.get("quote", ""), "sentence": r["sentence"],
            "doi": r["doi"], "first_author": r.get("first_author"), "year": r.get("year"), "venue": r.get("venue"),
            "date": r.get("date"), "title": r.get("title"), "is_review": bool(r.get("is_review")),
            "crossref": (works.get(r["doi"]) or {}).get("gate_a"), "excluded": bool(r.get("excluded_venue")),
            "excluded_reason": r.get("excluded_reason")}


themes = []
for row in rows:
    ev = [ev_item(by_sid[s]) for s in row["sids"] if s in by_sid]
    ev.sort(key=lambda e: e["date"] or "", reverse=True)          # 최신 먼저
    ev.sort(key=lambda e: e["kind"] != "bottleneck")                  # 한계 문장을 앞에(안정 정렬)
    dois = {e["doi"] for e in ev}
    themes.append({"id": row["cluster_id"], "theme": row["theme"], "stage": row.get("stage"), "status": row["status"],
                   "why": row.get("why"), "papers_total": row["papers_total"], "open_recent": row["open_recent"],
                   "solved_recent": row["solved_recent"], "both_sides": row.get("both_sides", 0), "ratio": row["ratio"],
                   "first_mention": row.get("first_mention"), "last_mention": row.get("last_mention"), "reviews": row["reviews"],
                   "sensitivity": sens.get(row["theme"]), "evidence": ev,
                   "fulltext": [ft_by_doi[d] for d in sorted(dois) if d in ft_by_doi]})
excluded = sorted({(r["doi"], r.get("venue"), r.get("excluded_reason")) for r in items if r.get("excluded_venue")})
jdump("bottlenecks.json", {
    "generated": time.strftime("%Y-%m-%d"), "run": os.path.basename(R3), "field": store.get("field"),
    "recent_from": recent_from, "stats": store["stats"],
    "labels": {k: sum(1 for r in items if r.get("label_kind") == k and not r.get("excluded_venue")) for k in ("bottleneck", "resolution-claim", "neither")},
    "venue_rule": "MDPI 학술지와 Scientific Reports는 후보에서 제외(출판사명·학술지명·DOI 접두사). 표시만 하고 삭제하지 않음.",
    "excluded": [{"doi": d, "venue": v, "reason": why} for d, v, why in excluded],
    "themes": themes})

# ------------------------------------------------------------------ 2. 동향 요약 (radar)
f2 = jload(os.path.join(R2, "funnel.json"))
ev2 = jload(os.path.join(R2, "evidence.json"))["bindings"]
w2 = jload(os.path.join(R2, "works.json"))
axes = []
for lv in f2["levels"]:
    mine = sorted([b for b in ev2 if b["level"] == lv["id"]], key=lambda b: b["order"])
    out = []
    for b in mine:
        rec = (w2.get(b["doi"]) or {}).get("record") or {}
        out.append({"bid": b["bid"], "state": b["state"], "reason": b.get("reason"), "claim": b["claim"], "quote": b.get("evidence_quote", ""),
                    "doi": b["doi"], "first_author": ((rec.get("authors") or [{}])[0] or {}).get("family"), "year": rec.get("year"),
                    "venue": rec.get("container_abbrev") or rec.get("container"), "title": rec.get("title"),
                    "cited_by": (w2.get(b["doi"]) or {}).get("cited_by"), "grader": b.get("grader")})
    axes.append({"id": lv["id"], "label": lv["label"], "claim": lv.get("claim"), "query": lv.get("query"), "items": out})
jdump("radar.json", {"generated": time.strftime("%Y-%m-%d"), "run": os.path.basename(R2), "project": f2.get("project"),
                     "approved": sum(1 for b in ev2 if b["state"] == "APPROVED"), "total": len(ev2), "axes": axes})

# ------------------------------------------------------------------ 3. 인트로 참고문헌
f1 = jload(os.path.join(R1, "funnel.json"))
refs = []
with io.open(os.path.join(R1, "refs", "references.csv"), encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        refs.append({k: r.get(k) for k in ("label", "level", "level_name", "role", "first_author", "year", "journal", "title", "doi", "review", "cited_for", "evidence_quote")})
levels = [{"id": l["id"], "type": l["type"], "label": l["label"], "claim": l.get("claim")} for l in f1["levels"]]
jdump("refs.json", {"generated": time.strftime("%Y-%m-%d"), "run": os.path.basename(R1), "project": f1.get("project"),
                    "chain": " > ".join(l["type"] for l in f1["levels"]), "levels": levels, "refs": refs,
                    "ris": "data/references_endnote.ris"})
import shutil
shutil.copy(os.path.join(R1, "refs", "references_endnote.ris"), os.path.join(OUT, "references_endnote.ris"))
print("references_endnote.ris 복사")

# ------------------------------------------------------------------ 4. meta
jdump("meta.json", {"built": time.strftime("%Y-%m-%d %H:%M"), "themes": len(themes), "themes_judged": sum(1 for t in themes if t["status"] != "근거 부족"),
                    "radar_approved": sum(1 for b in ev2 if b["state"] == "APPROVED"), "refs": len(refs),
                    "source": "intro-funnel 실행 3건(2026-09-20 / 09-26 / 10-14), 출판사 규칙 적용(10-18)"})
print("done")
