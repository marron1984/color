"use strict";

// ---------- API ヘルパ ----------
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

function toast(msg, isErr = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => (t.className = "toast"), 2600);
}

const WORK_STYLE_JA = { onsite: "実地", online: "オンライン", both: "どちらも" };
const AVAIL_JA = { available: "即稼働可", assigned: "稼働中", unavailable: "稼働不可" };
const AVAIL_CLS = { available: "green", assigned: "warn", unavailable: "gray" };
const KIND_JA = { new: "新規開拓", existing: "既存顧客" };

// スキル/必須スキルのテキスト→配列変換
function parseSkills(text) {
  return text.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const [name, level] = l.split(",").map(s => s.trim());
    return { name, level: parseInt(level || "1", 10) };
  });
}
function parseRequiredSkills(text) {
  return text.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const [name, weight, min_level] = l.split(",").map(s => s.trim());
    return { name, weight: parseFloat(weight || "1"), min_level: parseInt(min_level || "1", 10) };
  });
}

// ---------- タブ切替 ----------
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

// ---------- クライアント ----------
async function loadClients() {
  const clients = await api("/api/clients");
  const list = document.getElementById("clients-list");
  list.innerHTML = clients.length ? "" : '<div class="empty">クライアント未登録</div>';
  for (const c of clients) {
    const el = document.createElement("div");
    el.className = "card";
    el.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${esc(c.name)}</div>
          <div class="card-meta">${esc(c.industry || "")} ／ ${esc(c.contact_name || "-")} ／ ${esc(c.contact_email || "-")}</div>
        </div>
        <button class="ghost" data-del="${c.id}">削除</button>
      </div>
      <div class="chips"><span class="chip ${c.kind === "existing" ? "green" : ""}">${KIND_JA[c.kind] || c.kind}</span></div>
      ${c.notes ? `<div class="card-meta">${esc(c.notes)}</div>` : ""}`;
    el.querySelector("[data-del]").onclick = async () => {
      if (!confirm("削除しますか？関連する求人も削除されます。")) return;
      await api(`/api/clients/${c.id}`, { method: "DELETE" });
      toast("削除しました"); refreshAll();
    };
    list.appendChild(el);
  }
  // セレクト更新
  const sel = document.getElementById("job-client");
  sel.innerHTML = clients.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
}

document.getElementById("client-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/api/clients", { method: "POST", body: JSON.stringify(Object.fromEntries(f)) });
    e.target.reset(); toast("クライアントを登録しました"); loadClients();
  } catch (err) { toast(err.message, true); }
});

// ---------- 人材 ----------
async function loadTalents() {
  const talents = await api("/api/talents");
  const list = document.getElementById("talents-list");
  list.innerHTML = talents.length ? "" : '<div class="empty">人材未登録</div>';
  for (const t of talents) {
    const el = document.createElement("div");
    el.className = "card";
    const skills = (t.skills || []).map(s => `<span class="chip">${esc(s.name)} Lv${s.level}</span>`).join("");
    el.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${esc(t.name)} <span class="card-meta">${esc(t.kana || "")}</span></div>
          <div class="card-meta">経験${t.experience_years}年 ／ 希望${t.desired_salary}万 ／ ${esc(t.type_os || "-")} ／ ${esc(t.location || "-")} ／ ${WORK_STYLE_JA[t.work_style] || t.work_style}</div>
        </div>
        <button class="ghost" data-del="${t.id}">削除</button>
      </div>
      <div class="chips">${skills}<span class="chip ${AVAIL_CLS[t.availability]}">${AVAIL_JA[t.availability]}</span></div>
      ${t.profile ? `<div class="card-meta">${esc(t.profile)}</div>` : ""}`;
    el.querySelector("[data-del]").onclick = async () => {
      if (!confirm("削除しますか？")) return;
      await api(`/api/talents/${t.id}`, { method: "DELETE" });
      toast("削除しました"); loadTalents();
    };
    list.appendChild(el);
  }
}

// 履歴書の読み込み → フォームへ自動入力
function fillTalentForm(fields) {
  const form = document.getElementById("talent-form");
  const set = (name, val) => {
    if (val !== undefined && val !== null && val !== "" && form.elements[name]) {
      form.elements[name].value = val;
    }
  };
  set("name", fields.name);
  set("kana", fields.kana);
  if (Array.isArray(fields.skills) && fields.skills.length) {
    form.elements["skills"].value = fields.skills
      .map(s => `${s.name},${s.level || 3}`).join("\n");
  }
  if (fields.experience_years) set("experience_years", fields.experience_years);
  if (fields.desired_salary) set("desired_salary", fields.desired_salary);
  set("type_os", fields.type_os);
  if (fields.work_style && form.elements["work_style"]) form.elements["work_style"].value = fields.work_style;
  set("location", fields.location);
  set("profile", fields.profile);
}

document.getElementById("resume-btn").addEventListener("click", async () => {
  const input = document.getElementById("resume-file");
  const status = document.getElementById("resume-status");
  if (!input.files || !input.files.length) {
    toast("履歴書ファイルを選択してください", true);
    return;
  }
  status.textContent = "読み込み中…"; status.className = "resume-status loading";
  const fd = new FormData();
  fd.append("file", input.files[0]);
  try {
    // FormData 送信なので Content-Type は自動設定（api ヘルパは使わない）
    const res = await fetch("/api/talents/parse-resume", { method: "POST", body: fd });
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    const data = await res.json();
    fillTalentForm(data.fields);
    const label = data.source === "ai" ? "AI が読み込みました" : "簡易解析で読み込みました";
    status.textContent = `✓ ${label}（内容をご確認ください）`;
    status.className = "resume-status";
    toast("履歴書を読み込みました");
  } catch (err) {
    status.textContent = ""; status.className = "resume-status err";
    toast("読み込み失敗: " + err.message, true);
  }
});

document.getElementById("talent-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = new FormData(e.target);
  const payload = Object.fromEntries(f);
  payload.skills = parseSkills(payload.skills || "");
  payload.experience_years = parseFloat(payload.experience_years || "0");
  payload.desired_salary = parseInt(payload.desired_salary || "0", 10);
  try {
    await api("/api/talents", { method: "POST", body: JSON.stringify(payload) });
    e.target.reset(); toast("人材を登録しました"); loadTalents();
  } catch (err) { toast(err.message, true); }
});

// ---------- 求人 ----------
async function loadJobs() {
  const jobs = await api("/api/jobs");
  const list = document.getElementById("jobs-list");
  list.innerHTML = jobs.length ? "" : '<div class="empty">求人未登録</div>';
  for (const j of jobs) {
    const el = document.createElement("div");
    el.className = "card";
    const req = (j.required_skills || []).map(s => `<span class="chip">${esc(s.name)}≧Lv${s.min_level}</span>`).join("");
    el.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${esc(j.title)}</div>
          <div class="card-meta">${esc(j.client_name || "")} ／ 提示${j.offered_salary}万 ／ ${esc(j.type_os || "-")} ／ ${esc(j.location || "-")} ／ ${WORK_STYLE_JA[j.work_style] || j.work_style} ／ ${j.headcount}名</div>
        </div>
        <button class="ghost" data-del="${j.id}">削除</button>
      </div>
      <div class="chips">${req}</div>
      ${j.description ? `<div class="card-meta">${esc(j.description)}</div>` : ""}`;
    el.querySelector("[data-del]").onclick = async () => {
      if (!confirm("削除しますか？")) return;
      await api(`/api/jobs/${j.id}`, { method: "DELETE" });
      toast("削除しました"); refreshAll();
    };
    list.appendChild(el);
  }
  // マッチング用セレクト
  const sel = document.getElementById("match-job");
  sel.innerHTML = jobs.map(j => `<option value="${j.id}">${esc(j.title)}（${esc(j.client_name || "")}）</option>`).join("");
}

document.getElementById("job-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = new FormData(e.target);
  const payload = Object.fromEntries(f);
  payload.client_id = parseInt(document.getElementById("job-client").value, 10);
  payload.required_skills = parseRequiredSkills(payload.required_skills || "");
  payload.offered_salary = parseInt(payload.offered_salary || "0", 10);
  payload.headcount = parseInt(payload.headcount || "1", 10);
  try {
    await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    e.target.reset(); toast("求人を登録しました"); loadJobs();
  } catch (err) { toast(err.message, true); }
});

// ---------- マッチング ----------
document.getElementById("run-match").addEventListener("click", async () => {
  const jobId = document.getElementById("match-job").value;
  if (!jobId) { toast("求人を選択してください", true); return; }
  const topN = parseInt(document.getElementById("match-topn").value || "5", 10);
  const useLlm = document.getElementById("match-llm").checked;
  const container = document.getElementById("match-results");
  container.innerHTML = '<div class="empty">AI がピックアップ中…</div>';
  try {
    const candidates = await api(`/api/jobs/${jobId}/match`, {
      method: "POST",
      body: JSON.stringify({ top_n: topN, use_llm: useLlm, persist: false }),
    });
    renderMatches(candidates);
  } catch (err) {
    container.innerHTML = `<div class="empty">エラー: ${esc(err.message)}</div>`;
  }
});

function renderMatches(candidates) {
  const container = document.getElementById("match-results");
  if (!candidates.length) {
    container.innerHTML = '<div class="empty">候補となる人材がいません。人材を登録してください。</div>';
    return;
  }
  container.innerHTML = "";
  candidates.forEach((c, i) => {
    const scoreCls = c.score >= 75 ? "high" : c.score < 50 ? "low" : "";
    const bars = c.breakdown.components.map(comp => `
      <div class="bar-label">${esc(comp.label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${comp.score}%"></div><span class="bar-val">${comp.score}</span></div>
      ${comp.detail ? `<div class="bar-detail">${esc(comp.detail)}</div>` : ""}`).join("");
    const t = c.talent;
    const srcLabel = c.source === "ai" ? "AI 生成" : "スコア明細";
    const el = document.createElement("div");
    el.className = "match-card";
    el.innerHTML = `
      <div class="rank ${i === 0 ? "top" : ""}">${i + 1}</div>
      <div class="match-body">
        <div class="match-top">
          <div>
            <div class="match-name">${esc(t.name)} <span class="card-meta">${esc(t.type_os || "")} ／ 経験${t.experience_years}年 ／ ${esc(t.location || "")}</span></div>
          </div>
          <div class="score-pill ${scoreCls}">${c.score}</div>
        </div>
        <div class="reason">💡 ${esc(c.reason)}<span class="src">(${srcLabel})</span></div>
        <div class="bars">${bars}</div>
      </div>`;
    container.appendChild(el);
  });
}

// ---------- 共通 ----------
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, m =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    const badge = document.getElementById("llm-badge");
    if (h.llm_enabled) {
      badge.textContent = "AI: Claude 連携 ON";
      badge.className = "badge badge-ok";
    } else {
      badge.textContent = "AI: スコアリングのみ";
      badge.className = "badge badge-muted";
    }
  } catch (_) {}
}

function refreshAll() {
  loadClients(); loadTalents(); loadJobs();
}

// 初期ロード
loadHealth();
refreshAll();
