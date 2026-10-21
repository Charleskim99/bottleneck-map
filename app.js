/* 병목 지도 뷰어 - 빌드 없이 동작하는 정적 앱. 데이터는 data/*.json, 사용자 입력은 localStorage. */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } },
  };
  const STATUS_CLASS = { "열려 있음": "open", "경쟁 중": "contest", "해결 주장 우세": "solved", "근거 부족": "thin" };
  const KIND_KO = { bottleneck: "한계", "resolution-claim": "해결 주장", neither: "해당 없음" };
  const STAGE_KO = { material: "재료", process: "공정", interface: "계면", device: "소자", reliability: "신뢰성", metrology: "측정", "cost-scale": "비용·양산" };
  const state = { status: "all", stage: "all", q: "", showExcluded: false, selected: null, data: null, radar: null, refs: null };

  // ------------------------------------------------------------ tabs + 공유 링크 (#tab=map&theme=BN02, #tab=label&s=문장)
  const hashParams = () => new URLSearchParams(location.hash.replace(/^#/, ""));
  function setHash(obj) {
    const p = hashParams();
    Object.entries(obj).forEach(([k, v]) => (v == null || v === "" ? p.delete(k) : p.set(k, v)));
    history.replaceState(null, "", "#" + p.toString());
  }
  function activateTab(name) {
    const b = $$(".tab").find((x) => x.dataset.tab === name);
    if (!b) return;
    $$(".tab").forEach((x) => x.classList.toggle("is-active", x === b));
    $$(".panel").forEach((p) => p.classList.toggle("is-active", p.id === "tab-" + name));
    store.set("if.tab", name); setHash({ tab: name });
  }
  $$(".tab").forEach((b) => b.addEventListener("click", () => activateTab(b.dataset.tab)));
  activateTab(hashParams().get("tab") || store.get("if.tab", "map"));
  // 이미 열려 있는 화면에 해시 링크가 들어오면 새로고침이 일어나지 않으므로 직접 받는다
  window.addEventListener("hashchange", () => {
    const t = hashParams().get("tab");
    if (t) activateTab(t);
    if (state.data) applyHash();
  });
  function applyHash() {
    const p = hashParams();
    const th = p.get("theme");
    if (th && state.data.themes.some((t) => t.id === th)) { state.selected = th; renderTable(); renderDetail(th); }
    const s = (p.get("s") || "").trim();
    if (s) { $("#label-input").value = s; showResult(heuristic(s), "신호 단어 (링크)"); }
    const q = (p.get("q") || "").trim();
    if (q) { $("#q-input").value = q; runSearch(); }
  }

  // ------------------------------------------------------------ data
  async function load(name) {
    const r = await fetch("data/" + name, { cache: "no-store" });
    if (!r.ok) throw new Error(name + " " + r.status);
    return r.json();
  }
  Promise.all([load("bottlenecks.json"), load("radar.json"), load("refs.json"), load("meta.json").catch(() => null)])
    .then(([b, r, f, m]) => { state.data = b; state.radar = r; state.refs = f; initMap(); renderRadar(); renderRefs(); renderAbout(m); applyHash(); })
    .catch((e) => { $("#map-summary").textContent = "데이터를 읽지 못했습니다: " + e.message + " (build_data.py를 먼저 실행했는지 확인)"; });

  // ------------------------------------------------------------ map
  function initMap() {
    const stages = Array.from(new Set(state.data.themes.map((t) => t.stage).filter(Boolean)));
    const sel = $("#stage-select");
    stages.forEach((s) => { const o = document.createElement("option"); o.value = s; o.textContent = STAGE_KO[s] || s; sel.appendChild(o); });
    sel.addEventListener("change", () => { state.stage = sel.value; renderTable(); });
    $$("#status-chips .chip").forEach((c) => c.addEventListener("click", () => {
      $$("#status-chips .chip").forEach((x) => x.classList.toggle("is-on", x === c));
      state.status = c.dataset.status; renderTable();
    }));
    $("#search").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); renderTable(); });
    $("#show-excluded").addEventListener("change", (e) => { state.showExcluded = e.target.checked; renderTable(); if (state.selected) renderDetail(state.selected); });
    renderTable();
  }
  function judged(id) { return store.get("if.judge." + id, null); }
  function matches(t) {
    if (state.status !== "all" && t.status !== state.status) return false;
    if (state.stage !== "all" && t.stage !== state.stage) return false;
    if (!state.q) return true;
    const hay = [t.theme, ...t.evidence.map((e) => e.quote + " " + e.first_author + " " + e.venue)].join(" ").toLowerCase();
    return hay.includes(state.q);
  }
  function renderTable() {
    const d = state.data;
    const rows = d.themes.filter(matches);
    const tb = $("#theme-table tbody");
    tb.innerHTML = rows.map((t) => {
      const j = judged(t.id);
      return `<tr data-id="${t.id}" class="${state.selected === t.id ? "is-selected" : ""}">
        <td><div class="theme-name">${esc(t.theme)}</div><div class="judge">${t.both_sides ? "양쪽 모두 " + t.both_sides + "편 · " : ""}마지막 언급 ${esc(t.last_mention || "")}</div></td>
        <td>${esc(STAGE_KO[t.stage] || t.stage || "")}</td>
        <td><span class="badge ${STATUS_CLASS[t.status] || "thin"}">${esc(t.status)}</span>${t.sensitivity && !t.sensitivity.stable ? ' <span class="judge" title="묶는 기준·기간을 바꾸면 판정이 바뀜">설정 의존</span>' : ""}</td>
        <td class="num">${t.papers_total}</td><td class="num">${t.open_recent}</td><td class="num">${t.solved_recent}</td>
        <td class="judge">${j ? esc(j.verdict) + (j.memo ? " · 메모" : "") : "—"}</td></tr>`;
    }).join("");
    $$("#theme-table tbody tr").forEach((tr) => tr.addEventListener("click", () => { state.selected = tr.dataset.id; setHash({ theme: tr.dataset.id }); renderTable(); renderDetail(tr.dataset.id); }));
    const judgedN = d.themes.filter((t) => t.status !== "근거 부족").length;
    $("#map-summary").textContent = `실행 ${d.run} · 초록 ${d.stats.papers_scanned}편 · 라벨 ${d.labels.bottleneck + d.labels["resolution-claim"]}건 · 주제 ${d.themes.length}개 중 판정 ${judgedN}개 · 최근 창 ${d.recent_from} 이후 · 출판사 규칙으로 ${d.excluded.length}편 제외 · 표시 ${rows.length}개`;
  }
  function renderDetail(id) {
    const t = state.data.themes.find((x) => x.id === id);
    if (!t) return;
    const ev = t.evidence.filter((e) => state.showExcluded || !e.excluded);
    const block = (kind) => ev.filter((e) => e.kind === kind).map((e) => `
      <div class="ev ${kind === "bottleneck" ? "b" : "r"} ${e.excluded ? "ex" : ""}">
        <q>${esc(e.quote)}</q>
        <span class="src">${esc(e.first_author || "?")} ${esc(e.year || "")}, ${esc(e.venue || "")}${e.is_review ? " · 리뷰" : ""}${e.excluded ? " · 제외(" + esc(e.excluded_reason) + ")" : ""} · <a href="https://doi.org/${esc(e.doi)}" target="_blank" rel="noopener">DOI</a>${e.crossref === "APPROVED" ? " · Crossref 확인" : ""}</span>
        <details><summary class="judge">문장 전체</summary><div class="judge">${esc(e.sentence)}</div></details>
      </div>`).join("") || `<p class="placeholder">없음</p>`;
    const ft = t.fulltext.map((f) => `<div class="ft"><b>${esc(f.paper.split(",")[0])}</b> · 초록 주장 “${esc(f.abstract_claim)}” → <b>${esc(f.verdict.split(".")[0])}</b><br><span class="muted">조건: ${esc(f.conditions)}</span></div>`).join("");
    const j = judged(id) || { verdict: "", memo: "" };
    const sens = t.sensitivity ? (t.sensitivity.stable ? "묶는 기준·기간 여섯 설정에서 같은 판정" : "설정에 따라 판정이 바뀜: " + t.sensitivity.statuses.join(" / ")) : "민감도 정보 없음";
    $("#detail").innerHTML = `
      <h2>${esc(t.theme)}</h2>
      <div class="meta"><span class="badge ${STATUS_CLASS[t.status] || "thin"}">${esc(t.status)}</span> · ${esc(STAGE_KO[t.stage] || t.stage || "")} · 논문 ${t.papers_total}편(리뷰 ${t.reviews}) · 최근 한계 ${t.open_recent} / 해결주장 ${t.solved_recent} · 양쪽 모두 ${t.both_sides}편<br>${esc(t.why || "")} · ${esc(sens)}</div>
      <h3>내 판단 <span class="saved" id="saved-note"></span></h3>
      <div class="verdict-box">
        ${["동의", "보류", "반대"].map((v) => `<label><input type="radio" name="verdict" value="${v}" ${j.verdict === v ? "checked" : ""}> ${v}</label>`).join("")}
      </div>
      <textarea class="memo" id="memo" placeholder="이 판정에 대한 메모 (브라우저에 저장)">${esc(j.memo)}</textarea>
      ${ft ? `<h3>본문 대조 (${t.fulltext.length}편)</h3>${ft}` : ""}
      <h3>한계로 적은 문장 (${ev.filter((e) => e.kind === "bottleneck").length})</h3>${block("bottleneck")}
      <h3>해결했다고 주장한 문장 (${ev.filter((e) => e.kind === "resolution-claim").length})</h3>${block("resolution-claim")}`;
    const save = () => {
      const verdict = ($("input[name=verdict]:checked") || {}).value || "";
      const memo = $("#memo").value;
      const ok = store.set("if.judge." + id, { verdict, memo, at: new Date().toISOString() });
      $("#saved-note").textContent = ok ? "저장됨 " + new Date().toLocaleTimeString() : "저장 실패(브라우저 저장소 차단)";
      renderTable();
    };
    $$("input[name=verdict]").forEach((r) => r.addEventListener("change", save));
    let timer; $("#memo").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(save, 400); });
  }

  // ------------------------------------------------------------ radar
  function renderRadar() {
    const r = state.radar;
    $("#radar-summary").textContent = `실행 ${r.run} · ${esc(r.project || "")} · 승인 ${r.approved} / ${r.total}건 · 승인되지 않은 항목은 사유와 함께 표시`;
    $("#radar-list").innerHTML = r.axes.map((a) => `
      <div class="axis card">
        <h2>${esc(a.id)} ${esc(a.label)}</h2>
        <div class="q">${esc(a.claim || "")} · 검색어 <code>${esc(a.query || "")}</code></div>
        ${a.items.map((it) => `
          <div class="item ${it.state === "APPROVED" ? "" : "ex"}">
            <b>${esc(it.first_author || "?")} ${esc(it.year || "")}</b>, ${esc(it.venue || "")} · <a href="https://doi.org/${esc(it.doi)}" target="_blank" rel="noopener">DOI</a>
            ${it.state === "APPROVED" ? "" : ` <span class="badge ex">${esc(it.state)}</span> <span class="muted">${esc(it.reason || "")}</span>`}
            <div>${esc(it.claim)}</div>
            <div class="quote">근거: “${esc(it.quote)}”${it.grader ? " · 채점 " + esc(it.grader) : ""}</div>
          </div>`).join("")}
      </div>`).join("");
  }

  // ------------------------------------------------------------ refs
  function renderRefs(q = "") {
    const f = state.refs;
    const ql = q.trim().toLowerCase();
    const refs = f.refs.filter((x) => !ql || [x.title, x.first_author, x.journal, x.level_name].join(" ").toLowerCase().includes(ql));
    $("#refs-summary").textContent = `${esc(f.project || "")} · 체인 ${f.chain} · 참고문헌 ${f.refs.length}편(표시 ${refs.length})`;
    let lastLevel = null;
    $("#refs-list").innerHTML = refs.map((x) => {
      const head = x.level !== lastLevel ? `<div class="level-head">${esc(x.level)} · ${esc(x.level_name)}</div>` : "";
      lastLevel = x.level;
      return head + `<div class="ref"><div class="lab">${esc(x.label)}<br>${esc(x.role || "")}</div>
        <div><div><b>${esc(x.first_author)} ${esc(x.year)}</b>, <i>${esc(x.journal)}</i>${x.review === "True" || x.review === "yes" ? " · 리뷰" : ""} · <a href="https://doi.org/${esc(x.doi)}" target="_blank" rel="noopener">DOI</a></div>
        <div>${esc(x.title)}</div>
        <div class="cite">인용 이유: ${esc(x.cited_for || "")}</div>
        ${x.evidence_quote ? `<div class="cite">근거: “${esc(x.evidence_quote)}”</div>` : ""}</div></div>`;
    }).join("");
  }
  $("#ref-search").addEventListener("input", (e) => renderRefs(e.target.value));

  // ------------------------------------------------------------ about
  function renderAbout(m) {
    if (!m) return;
    $("#about-meta").textContent = `데이터 생성 ${m.built} · 주제 ${m.themes}개(판정 ${m.themes_judged}) · 동향 승인 ${m.radar_approved}건 · 참고문헌 ${m.refs}편 · 출처: ${m.source}`;
  }

  // ------------------------------------------------------------ 문장 판정 (신호 단어, 브라우저)
  const GAP = [/\bbottlenecks?\b/i, /\bremain(?:s|ed|ing)?\s+(?:a\s+|an\s+|the\s+)?(?:major|key|critical|significant|open)?\s*(?:challeng(?:e|es|ing)|elusive|unclear|unsolved|unresolved|difficult|problematic|limited|limitation|obstacle|barrier|issue|problem)/i,
    /\b(?:still|yet)\s+(?:remains?|lacks?|suffers?|limited|challenging|difficult|unclear)/i, /\bsuffers?\s+from\b/i, /\b(?:hinder|hamper|impede|preclude|restrict)\w*\b/i,
    /\b(?:limited|restricted|constrained|plagued)\s+by\b/i, /\b(?:major|key|critical|main|fundamental|long-standing)\s+(?:challenge|limitation|obstacle|barrier|issue|problem|drawback|hurdle)/i,
    /\b(?:challenges?|limitations?|drawbacks?|obstacles?|barriers?|hurdles?|shortcomings?)\b/i, /\btrade-?offs?\b/i, /\b(?:difficult|hard)\s+to\b/i, /\bfail(?:s|ed|ure)?\b/i,
    /\b(?:lack|lacks|lacking|absence)\s+(?:of|the)\b/i, /\b(?:insufficient|inadequate)\b/i, /\bhas\s+yet\s+to\b/i, /\bnot\s+(?:yet\s+)?been\s+(?:fully\s+)?(?:achieved|realized|demonstrated|understood|resolved)/i,
    /\b(?:prone|susceptible)\s+to\b/i, /\b(?:degrad|deteriorat)\w*\b/i, /\b(?:instabilit|irreversib|unreliab)/i];
  const SOLVED = [/\bno\s+longer\s+(?:a\s+|an\s+)?(?:challenge|barrier|limitation|obstacle|issue|problem|bottleneck|required|necessary|needed)/i, /\bovercom(?:e|es|ing)\b/i,
    /\b(?:eliminat|resolv|circumvent|mitigat|alleviat)\w*\b/i, /\bsolv(?:e|es|ed|ing)\b/i, /\bwithout\s+(?:the\s+need\s+for|any\s+|additional\s+)/i,
    /\b(?:well[-\s]established|mature|now\s+routinely|widely\s+(?:adopted|used))\b/i, /\b(?:enable|enables|enabled|enabling|allow|allows|allowing)\b/i];
  function heuristic(sentence) {
    const g = GAP.filter((r) => r.test(sentence)).map((r) => (sentence.match(r) || [""])[0]);
    const s = SOLVED.filter((r) => r.test(sentence)).map((r) => (sentence.match(r) || [""])[0]);
    let kind = "neither";
    if (g.length && g.length >= s.length) kind = "bottleneck";
    else if (s.length) kind = "resolution-claim";
    return { kind, gap_cues: g, solved_cues: s, note: "신호 단어 기반 1차 판정입니다. 문장이 방법·수치만 말하면 neither가 맞고, 최종 판정은 사람 또는 AI가 합니다." };
  }
  function showResult(r, source) {
    $("#label-result").innerHTML = `<div class="card"><div><span class="muted">${esc(source)}</span> → <span class="kind badge ${r.kind === "bottleneck" ? "kind-b" : r.kind === "resolution-claim" ? "kind-r" : "thin"}">${esc(KIND_KO[r.kind] || r.kind)}</span> (${esc(r.kind)})</div>
      ${r.theme ? `<div>주제: ${esc(r.theme)}</div>` : ""}${r.quote ? `<div>인용: “${esc(r.quote)}”${r.quote_verbatim === false ? ' <span class="badge thin">문장에 없는 인용</span>' : ""}</div>` : ""}
      ${r.gap_cues ? `<div class="muted">한계 신호: ${esc(r.gap_cues.join(", ") || "없음")} · 성취 신호: ${esc(r.solved_cues.join(", ") || "없음")}</div>` : ""}
      ${r.note ? `<div class="muted">${esc(r.note)}</div>` : ""}</div>`;
  }
  function pushHistory(entry) {
    const h = store.get("if.labels", []);
    h.unshift(entry); store.set("if.labels", h.slice(0, 20)); renderHistory();
  }
  // ------------------------------------------------------------ 분야 검색 (라이브)
  function sentHtml(r) {
    return `<div class="sent">${esc(r.sentence)}
      <div class="meta">${esc(r.paper)}${r.venue ? " · " + esc(r.venue) : ""} · <a href="https://doi.org/${esc(r.doi)}" target="_blank" rel="noopener">DOI</a>
      ${r.cues && r.cues.length ? " · 신호: " + esc(r.cues.slice(0, 3).join(", ")) : ""}</div></div>`;
  }
  async function runSearch() {
    const q = $("#q-input").value.trim();
    if (!q) { $("#q-status").textContent = "검색어를 넣어 주세요."; return; }
    const btn = $("#btn-search"); btn.disabled = true;
    $("#q-status").textContent = "OpenAlex에서 찾는 중…";
    $("#q-caveat").hidden = true; $("#q-result").innerHTML = "";
    setHash({ tab: "search", q });
    try {
      const r = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, months: Number($("#q-months").value) }) });
      const j = await r.json();
      if (!r.ok || j.error) { $("#q-status").textContent = "찾지 못했습니다: " + (j.error || r.status); return; }
      $("#q-status").textContent = "";
      $("#q-caveat").hidden = false;
      $("#q-caveat").textContent = j.caveat;
      const kw = (j.keywords || []).map((k) => `<span class="kw">${esc(k.word)} <b>${k.papers}</b></span>`).join("");
      $("#q-result").innerHTML =
        `<p class="hint">검색 결과 ${j.hit_count != null ? j.hit_count.toLocaleString() : "?"}건 중 최근·인용 상위 ${j.papers}편을 읽었습니다
         (초록이 없거나 짧아 건너뛴 논문 ${j.papers_without_abstract}편). 최근 ${j.months}개월 기준.</p>
         ${kw ? `<h3>한계 문장에 자주 나온 말</h3><p>${kw}</p>` : ""}
         <h3>아직 한계로 적힌 문장 <span class="muted">${j.gap.length}개</span></h3>
         ${j.gap.length ? j.gap.map(sentHtml).join("") : "<p class='muted'>없습니다.</p>"}
         <h3>해결했다고 적은 문장 <span class="muted">${j.solved.length}개</span></h3>
         ${j.solved.length ? j.solved.map(sentHtml).join("") : "<p class='muted'>없습니다.</p>"}`;
    } catch (e) {
      $("#q-status").textContent = "서버에 연결하지 못했습니다(로컬 정적 서버에는 /api가 없습니다): " + e.message;
    }
    btn.disabled = false;
  }
  $("#btn-search").addEventListener("click", runSearch);
  $("#q-input").addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });

  function renderHistory() {
    const h = store.get("if.labels", []);
    $("#label-history").innerHTML = h.length ? h.map((x) => `<li><span class="badge ${x.kind === "bottleneck" ? "kind-b" : x.kind === "resolution-claim" ? "kind-r" : "thin"}">${esc(KIND_KO[x.kind] || x.kind)}</span> <span class="muted">${esc(x.source)} · ${esc(new Date(x.at).toLocaleString())}</span><br>${esc(x.sentence.slice(0, 160))}</li>`).join("") : "<li class='muted'>아직 없습니다.</li>";
  }
  renderHistory();
  $("#btn-heuristic").addEventListener("click", () => {
    const s = $("#label-input").value.trim();
    if (!s) { $("#label-status").textContent = "문장을 넣어 주세요."; return; }
    const r = heuristic(s); showResult(r, "신호 단어"); pushHistory({ sentence: s, kind: r.kind, source: "신호 단어", at: new Date().toISOString() }); $("#label-status").textContent = "";
  });
  $("#btn-ai").addEventListener("click", async () => {
    const s = $("#label-input").value.trim();
    if (!s) { $("#label-status").textContent = "문장을 넣어 주세요."; return; }
    const btn = $("#btn-ai"); btn.disabled = true; $("#label-status").textContent = "서버에 요청 중…";
    try {
      const r = await fetch("/api/label", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sentence: s, field: state.data ? state.data.field : "" }) });
      const j = await r.json();
      if (!r.ok || j.error) { $("#label-status").textContent = "AI 판정 불가: " + (j.error || r.status) + " (신호 단어 판정은 됩니다)"; }
      else {
        if (j.quote) j.quote_verbatim = s.toLowerCase().replace(/\s+/g, " ").includes(String(j.quote).toLowerCase().replace(/\s+/g, " "));
        showResult(j, "AI (" + (j.model || "server") + ")"); pushHistory({ sentence: s, kind: j.kind, source: "AI", at: new Date().toISOString() }); $("#label-status").textContent = "";
      }
    } catch (e) { $("#label-status").textContent = "서버 함수에 연결하지 못했습니다(로컬 정적 서버에서는 /api가 없습니다): " + e.message; }
    btn.disabled = false;
  });
})();
