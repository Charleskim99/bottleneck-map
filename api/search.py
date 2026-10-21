# -*- coding: utf-8 -*-
"""Vercel 서버 함수: POST /api/search  {"query": "...", "months": 24}  ->  분야를 직접 입력해 받는 한계·해결 주장 문장.

왜 따로 있는가: 이 사이트에 올라간 병목 지도·동향 요약·참고문헌은 한 분야(액체금속 신축 전자)를 미리 돌려 둔
결과입니다. 다른 분야 사람이 그대로 쓸 수 없어서, 검색어를 받아 그 자리에서 OpenAlex를 돌리는 경로를 뒀습니다.

어디까지 하는가(중요): 여기서는 **라벨을 붙이지 않습니다.** 원래 파이프라인은 문장마다 LLM이 라벨하고 스크립트가
축자 인용을 대조하지만, 그 단계는 API 키가 필요합니다. 이 함수는 키 없이 도는 부분, 즉 초록을 문장으로 자르고
한계·성취 신호 단어로 1차 분류하는 데까지만 합니다. 그래서 결과는 "검증된 병목 지도"가 아니라 "신호 단어로 고른
문장 목록"이고, 화면도 그렇게 표시합니다.

표준 라이브러리만 씁니다. 로컬 시험은 dev_server.py 가 같은 handle() 을 붙입니다.
"""
import datetime as _dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

API = "https://api.openalex.org/works"
UA = "IntroFunnelWeb/0.1 (bottleneck map viewer; live field search)"
SELECT = ("id,doi,title,publication_year,publication_date,cited_by_count,type,authorships,primary_location,"
          "abstract_inverted_index,is_retracted")
# 출판사 규칙: MDPI 학술지와 Scientific Reports 는 후보에 넣지 않는다(본 파이프라인과 같은 규칙).
EXCLUDE_PREFIX = ("10.3390/", "10.1038/s41598")
EXCLUDE_PUBLISHER = ("mdpi",)
EXCLUDE_VENUE = ("scientific reports",)

_ABBR = (r"(?<!\be\.g)(?<!\bi\.e)(?<!\bet\sal)(?<!\bvs)(?<!\bcf)(?<!\bca)(?<!\bapprox)(?<!\bFig)(?<!\bfig)"
         r"(?<!\bEq)(?<!\beq)(?<!\bRef)(?<!\bref)(?<!\bNo)(?<!\bvol)(?<!\bDr)")
_SPLIT = re.compile(_ABBR + r"(?<=[.!?])[\"')\]]?\s+(?=[\"'(\[]?[A-Z0-9])")
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]*")

GAP_CUES = [
    (2, r"\bbottlenecks?\b"),
    (2, r"\bremain(?:s|ed|ing)?\s+(?:a\s+|an\s+|the\s+)?(?:major|key|critical|significant|main|central|primary|formidable|open)?\s*"
        r"(?:challenge|challenging|elusive|unclear|unknown|unsolved|unresolved|difficult|problematic|limited|limitation|obstacle|barrier|issue|problem)"),
    (2, r"\b(?:still|yet)\s+(?:remains?|lacks?|lacking|suffers?|limited|challenging|difficult|unclear|elusive|an?\s+open)"),
    (2, r"\bsuffers?\s+from\b"),
    (2, r"\b(?:hinder|hamper|impede|preclude|prohibit|restrict)\w*\b"),
    (2, r"\b(?:limited|restricted|constrained|hindered|hampered|plagued|challenged)\s+by\b"),
    (2, r"\b(?:major|key|critical|main|primary|significant|fundamental|outstanding|long-standing|remaining)\s+"
        r"(?:challenge|limitation|obstacle|barrier|issue|problem|drawback|hurdle|concern|difficulty)"),
    (2, r"\b(?:challenges?|limitations?|drawbacks?|obstacles?|barriers?|hurdles?|shortcomings?|difficulties)\b"),
    (2, r"\btrade-?offs?\b"),
    (2, r"\b(?:difficult|hard|impossible|infeasible)\s+to\b"),
    (2, r"\bfail(?:s|ed|ure|ures)?\b"),
    (2, r"\b(?:lack|lacks|lacking|absence|dearth|scarcity|paucity)\s+(?:of|the|a\b)"),
    (2, r"\b(?:insufficient|inadequate|unsatisfactory|suboptimal|undesirable)\b"),
    (2, r"\bhas\s+yet\s+to\b|\bhave\s+yet\s+to\b"),
    (2, r"\bnot\s+(?:yet\s+)?been\s+(?:fully\s+|widely\s+|well\s+)?(?:achieved|realized|realised|demonstrated|understood|explored|established|resolved|addressed)"),
    (2, r"\bopen\s+(?:question|problem|challenge|issue)"),
    (2, r"\b(?:prone|susceptible|vulnerable)\s+to\b"),
    (2, r"\b(?:impair|compromis|deteriorat|degrad)(?:e|es|ed|ing|ation)?\b"),
    (2, r"\b(?:instabilit|irreversib|unreliab|inhomogene|non-?uniform)"),
    (1, r"\bhowever\b|\bnevertheless\b|\bnonetheless\b|\bunfortunately\b|\bwhereas\b|\bin\s+contrast\b"),
    (1, r"\bpoor(?:ly)?\b|\bweak\b|\bcostly\b|\bexpensive\b"),
    (1, r"\bleakage\b|\btoxic(?:ity)?\b|\bcorrosi|\bdelaminat|\bcrack"),
    (1, r"\bunstable\b|\bdrift\b|\bhysteresis\b|\bfatigue\b"),
]
SOLVED_CUES = [
    (2, r"\bno\s+longer\s+(?:a\s+|an\s+|the\s+)?(?:major\s+|key\s+|critical\s+)?"
        r"(?:challenge|challenging|barrier|limitation|obstacle|issue|problem|bottleneck|concern|hurdle|required|necessary|needed)"),
    (2, r"\bis\s+now\s+(?:routine|possible|feasible|achievable|straightforward|established)\b"),
    (2, r"\bovercom(?:e|es|ing)\b"),
    (2, r"\b(?:eliminat|resolv|circumvent|mitigat|alleviat|obviat)(?:e|es|ed|ing)\b"),
    (2, r"\bsolv(?:e|es|ed|ing)\b"),
    (2, r"\bwithout\s+(?:the\s+need\s+for|any\s+|additional\s+|external\s+|post-?)"),
    (2, r"\b(?:well[-\s]established|mature|now\s+routinely|widely\s+(?:adopted|used|available)|commercially\s+available)\b"),
    (2, r"\bhas\s+been\s+(?:widely\s+|well\s+|successfully\s+)?(?:achieved|demonstrated|established|realized|realised|solved)\b"),
    (2, r"\b(?:enable|enables|enabled|enabling|allow|allows|allowed|allowing)\b"),
    (1, r"\b(?:we|here(?:in)?|this\s+(?:work|study|paper|article))\s+(?:report|reports|present|presents|demonstrate|demonstrates|"
        r"propose|proposes|develop|develops|introduce|introduces|show|shows)"),
    (1, r"\bsuccessful(?:ly)?\b|\brobust\b|\bdurable\b|\breliable\b|\bscalable\b|\breproducible\b"),
]
STOP = set("a an the of and or for to in on with by from as at is are was were be been being this that these those it its "
           "their our we us can could may might will would should must have has had do does did not no nor which who whom "
           "whose what when where how why than then thus hence such very more most much many few both each other others same "
           "different new novel high low large small using used use based between among within without into onto over under "
           "about after before during while due via toward towards per also however therefore moreover furthermore "
           "additionally although though because since if unless tradeoff tradeoffs challenge challenges limitation "
           "limitations issue issues problem problems difficulty difficulties performance properties property step steps "
           "results result show shows showed study studies work works paper report reports here due remains remain still "
           "yet due lack lacks limited".split())


def _norm(s):
    s = (s or "").lower()
    s = s.translate(str.maketrans("‐‑‒–—−“”‘’", "------\"\"''"))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sentences(text):
    text = re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()
    if not text:
        return []
    out = []
    for part in _SPLIT.split(text):
        part = part.strip()
        if part:
            out.append(part)
    return out


def _score(sentence):
    low = _norm(sentence)
    g = s = 0
    gn, sn = [], []
    sg = ss = False
    for w, pat in GAP_CUES:
        m = re.search(pat, low)
        if m:
            g += w
            gn.append(m.group(0).strip()[:34])
            sg = sg or w == 2
    for w, pat in SOLVED_CUES:
        m = re.search(pat, low)
        if m:
            s += w
            sn.append(m.group(0).strip()[:34])
            ss = ss or w == 2
    if sg and g >= s:
        cls = "gap"
    elif ss and s > g:
        cls = "solved"
    elif sg:
        cls = "mixed"
    elif ss:
        cls = "solved"
    else:
        cls = None
    return cls, g, s, (gn + sn)[:5]


def _abstract(inv):
    if not inv:
        return ""
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    return " ".join(w for _, w in sorted(pos))


def _months_ago(months):
    d = _dt.date.today()
    y, m = divmod((d.year * 12 + d.month - 1) - months, 12)
    return f"{y:04d}-{m + 1:02d}-01"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _hit(w):
    doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
    if not doi.startswith("10."):
        return None
    src = ((w.get("primary_location") or {}).get("source") or {})
    venue = src.get("display_name") or ""
    publisher = (src.get("host_organization_name") or "").lower()
    if doi.startswith(EXCLUDE_PREFIX) or any(p in publisher for p in EXCLUDE_PUBLISHER) or venue.lower().strip() in EXCLUDE_VENUE:
        return None
    names = [(a.get("author") or {}).get("display_name") or "" for a in (w.get("authorships") or [])]
    return {"doi": doi, "title": re.sub(r"<[^>]+>", "", w.get("title") or ""), "year": w.get("publication_year"),
            "date": w.get("publication_date"), "venue": venue, "cited_by": w.get("cited_by_count") or 0,
            "first_author": (names[0] if names else ""), "abstract": _abstract(w.get("abstract_inverted_index"))}


def handle(payload: dict) -> tuple[int, dict]:
    query = re.sub(r"\s+", " ", (payload.get("query") or "")).strip()
    if not query:
        return 400, {"error": "검색어를 넣어 주세요"}
    if len(query) > 120:
        return 400, {"error": "검색어가 너무 깁니다(120자 이내)"}
    terms = [t for t in re.split(r"\s+", query) if t]
    if len(terms) > 6:
        return 400, {"error": "검색어는 핵심어 2~4개가 가장 잘 맞습니다. 모든 단어가 AND로 묶이므로 6개를 넘기면 결과가 거의 없습니다"}
    try:
        months = max(6, min(60, int(payload.get("months") or 24)))
    except (TypeError, ValueError):
        months = 24
    per_page = max(10, min(25, int(payload.get("per_page") or 25)))
    flt_base = f"title_and_abstract.search:{query.replace(',', ' ')},is_retracted:false,type:article|review"
    passes = [("cited", f"{flt_base},from_publication_date:{_months_ago(48)}", "cited_by_count:desc", per_page),
              ("new", f"{flt_base},from_publication_date:{_months_ago(months)}", "publication_date:desc", per_page)]
    pool, hit_count = {}, None
    for tag, flt, sort, n in passes:
        url = API + "?" + urllib.parse.urlencode({"filter": flt, "sort": sort, "per-page": n, "select": SELECT})
        try:
            data = _get(url)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return 503, {"error": "OpenAlex 하루 호출 한도에 걸렸습니다(이 서버 주소 기준). 잠시 뒤 다시 시도해 주세요"}
            return 502, {"error": f"OpenAlex 오류 HTTP {e.code}"}
        except Exception as e:
            return 502, {"error": f"OpenAlex에 연결하지 못했습니다: {type(e).__name__}"}
        if tag == "cited":
            hit_count = (data.get("meta") or {}).get("count")
        for w in data.get("results") or []:
            h = _hit(w)
            if h:
                pool.setdefault(h["doi"], h)
    papers = list(pool.values())
    gap, solved, no_abs = [], [], 0
    for p in papers:
        if len(p["abstract"]) < 200:
            no_abs += 1
            continue
        best = []
        for s in _sentences(p["abstract"]):
            if len(_WORD.findall(s.lower())) < 6 or len(s) > 600:
                continue
            cls, g, sc, cues = _score(s)
            if not cls:
                continue
            best.append({"cls": cls, "score": g + sc, "sentence": s, "cues": cues,
                         "paper": f"{p['first_author'] or '?'} {p['year']}", "venue": p["venue"],
                         "doi": p["doi"], "title": p["title"], "date": p["date"]})
        best.sort(key=lambda r: -r["score"])
        for r in best[:2]:
            (solved if r["cls"] == "solved" else gap).append(r)
    tally = {}
    for r in gap:
        for t in set(_WORD.findall(r["sentence"].lower())):
            if t not in STOP and len(t) > 3 and not t.isdigit():
                tally[t] = tally.get(t, 0) + 1
    top = [{"word": k, "papers": v} for k, v in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:14] if v > 1]
    gap.sort(key=lambda r: ((r["date"] or ""), r["score"]), reverse=True)
    solved.sort(key=lambda r: ((r["date"] or ""), r["score"]), reverse=True)
    return 200, {"query": query, "months": months, "hit_count": hit_count,
                 "papers": len(papers), "papers_without_abstract": no_abs,
                 "gap": gap[:40], "solved": solved[:40], "keywords": top,
                 "caveat": ("신호 단어로 고른 1차 결과입니다. 원래 파이프라인의 라벨(LLM)과 축자 인용 대조, 주제 묶기, "
                            "Crossref 서지 확인은 이 화면에서 돌지 않습니다. 병목 지도 탭의 예시 분야만 그 검증을 거쳤습니다.")}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return self._send(400, {"error": "본문이 JSON이 아닙니다"})
        code, obj = handle(payload)
        self._send(code, obj)

    def do_GET(self):
        self._send(405, {"error": "POST 로 호출하세요"})
