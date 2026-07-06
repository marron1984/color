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

const WORK_STYLE_JA = { onsite: "店舗勤務", online: "オンライン", both: "どちらも" };
const AVAIL_JA = { available: "即勤務可", assigned: "勤務中", unavailable: "対応不可" };
const AVAIL_CLS = { available: "green", assigned: "warn", unavailable: "gray" };
const KIND_JA = { new: "新規開拓", existing: "既存顧客" };

// 入力ビルダー: 名前＋レベル等を選んで「追加」→チップ表示（×で削除）
function initBuilder(id) {
  const root = document.getElementById(id);
  if (!root) return null;
  const kind = root.dataset.kind;                 // skill / lang / reqskill / reqlang / name
  const chips = root.querySelector(".builder-chips");
  const nameEl = root.querySelector(".bd-name");
  const levelEl = root.querySelector(".bd-level");
  const weightEl = root.querySelector(".bd-weight");
  const minEl = root.querySelector(".bd-min");
  const addBtn = root.querySelector(".bd-add");
  let items = [];

  const WLABEL = { 3: "重要度:高", 2: "重要度:中", 1: "重要度:低" };
  function chipText(it) {
    if (kind === "skill" || kind === "lang") return `${esc(it.name)} <span>Lv${it.level}</span>`;
    if (kind === "reqskill") return `${esc(it.name)} <span>${WLABEL[it.weight] || ""}・Lv${it.min_level}以上</span>`;
    if (kind === "reqlang") return `${esc(it.name)} <span>Lv${it.min_level}以上</span>`;
    return esc(it.name);
  }
  function render() {
    if (!items.length) { chips.innerHTML = '<span class="builder-empty">まだ追加されていません</span>'; return; }
    chips.innerHTML = items.map((it, i) =>
      `<span class="bchip">${chipText(it)}<button type="button" data-i="${i}" aria-label="削除">×</button></span>`).join("");
    chips.querySelectorAll("button[data-i]").forEach(b => b.onclick = () => { items.splice(+b.dataset.i, 1); render(); });
  }
  function add() {
    const name = (nameEl.value || "").trim();
    if (!name) { nameEl.focus(); return; }
    const it = { name };
    if (kind === "skill" || kind === "lang") it.level = parseInt(levelEl.value, 10);
    if (kind === "reqskill") { it.weight = parseFloat(weightEl.value); it.min_level = parseInt(minEl.value, 10); }
    if (kind === "reqlang") it.min_level = parseInt(minEl.value, 10);
    const dup = items.findIndex(x => x.name === name);  // 同名は上書き
    if (dup >= 0) items[dup] = it; else items.push(it);
    nameEl.value = ""; render(); nameEl.focus();
  }
  addBtn.onclick = add;
  nameEl.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  render();

  return {
    get() { return kind === "name" ? items.map(i => i.name) : items.map(i => ({ ...i })); },
    set(arr) {
      items = (arr || []).map(x => {
        if (kind === "name") return { name: typeof x === "string" ? x : x.name };
        if (kind === "skill" || kind === "lang") return { name: x.name, level: x.level || 3 };
        if (kind === "reqskill") return { name: x.name, weight: x.weight || 2, min_level: x.min_level || 1 };
        if (kind === "reqlang") return { name: x.name, min_level: x.min_level || 1 };
        return { name: x.name };
      });
      render();
    },
    clear() { items = []; render(); },
  };
}

// 各ビルダーを初期化（DOM は body 末尾で読み込まれるため即時取得可）
const B = {
  talentSkills: initBuilder("talent-skill-builder"),
  talentLangs: initBuilder("talent-lang-builder"),
  talentCountries: initBuilder("talent-country-builder"),
  jobSkills: initBuilder("job-skill-builder"),
  jobLangs: initBuilder("job-lang-builder"),
};

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
  list.innerHTML = clients.length ? "" : '<div class="empty">店舗未登録</div>';
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
      if (!confirm("この店舗を削除しますか？関連する求人も削除されます。")) return;
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
    e.target.reset(); toast("店舗を登録しました"); loadClients();
  } catch (err) { toast(err.message, true); }
});

// 連絡先ブロック（既定は非表示。ボタンで開閉）
function contactBlock(t) {
  const rows = [];
  if (t.phone) rows.push(`<div class="cb-row"><span class="cb-key">電話</span><a href="tel:${esc(t.phone)}">${esc(t.phone)}</a></div>`);
  if (t.email) rows.push(`<div class="cb-row"><span class="cb-key">メール</span><a href="mailto:${esc(t.email)}">${esc(t.email)}</a></div>`);
  if (t.contact_note) rows.push(`<div class="cb-row"><span class="cb-key">その他</span><span>${esc(t.contact_note)}</span></div>`);
  const inner = rows.length ? rows.join("") : `<div class="contact-empty">連絡先は未登録です</div>`;
  return `<div class="contact-block" hidden>${inner}</div>`;
}

// ---------- 人材 ----------
async function loadTalents() {
  const talents = await api("/api/talents");
  const list = document.getElementById("talents-list");
  list.innerHTML = talents.length ? "" : '<div class="empty">人材未登録</div>';
  for (const t of talents) {
    const el = document.createElement("div");
    el.className = "card";
    const skills = (t.skills || []).map(s => `<span class="chip">${esc(s.name)} Lv${s.level}</span>`).join("");
    const langs = (t.languages || []).map(l => `<span class="chip green">${esc(l.name)} Lv${l.level}</span>`).join("");
    const countries = (t.desired_countries || []).length
      ? `<div class="card-meta">🌐 希望勤務国: ${(t.desired_countries || []).map(esc).join("・")}</div>` : "";
    const natVisa = [
      t.nationality ? `国籍: ${esc(t.nationality)}` : "",
      t.visa_status ? `在留資格: ${esc(t.visa_status)}` : "",
    ].filter(Boolean).join(" ／ ");
    el.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${esc(t.name)} <span class="card-meta">${esc(t.kana || "")}</span></div>
          <div class="card-meta">経験${t.experience_years}年 ／ 希望${t.desired_salary}万 ／ ${esc(t.type_os || "-")} ／ ${esc(t.location || "-")} ／ ${WORK_STYLE_JA[t.work_style] || t.work_style}</div>
          ${natVisa ? `<div class="card-meta">${natVisa}</div>` : ""}
        </div>
        <div class="card-actions">
          <button class="ghost" data-contact="${t.id}">連絡先</button>
          <button class="ghost" data-del="${t.id}">削除</button>
        </div>
      </div>
      <div class="chips">${skills}${langs}<span class="chip ${AVAIL_CLS[t.availability]}">${AVAIL_JA[t.availability]}</span></div>
      ${countries}
      ${t.profile ? `<div class="card-meta">${esc(t.profile)}</div>` : ""}
      ${contactBlock(t)}`;
    el.querySelector("[data-del]").onclick = async () => {
      if (!confirm("削除しますか？")) return;
      await api(`/api/talents/${t.id}`, { method: "DELETE" });
      toast("削除しました"); loadTalents();
    };
    const cbtn = el.querySelector("[data-contact]");
    const cblock = el.querySelector(".contact-block");
    cbtn.onclick = () => {
      const hidden = cblock.hasAttribute("hidden");
      cblock.toggleAttribute("hidden");
      cbtn.textContent = hidden ? "連絡先を隠す" : "連絡先";
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
  if (Array.isArray(fields.skills) && fields.skills.length) B.talentSkills.set(fields.skills);
  if (fields.experience_years) set("experience_years", fields.experience_years);
  if (fields.desired_salary) set("desired_salary", fields.desired_salary);
  set("type_os", fields.type_os);
  if (fields.work_style && form.elements["work_style"]) form.elements["work_style"].value = fields.work_style;
  set("location", fields.location);
  // 海外人材向け
  set("nationality", fields.nationality);
  set("visa_status", fields.visa_status);
  if (Array.isArray(fields.languages) && fields.languages.length) B.talentLangs.set(fields.languages);
  if (Array.isArray(fields.desired_countries) && fields.desired_countries.length) B.talentCountries.set(fields.desired_countries);
  // 連絡先
  set("phone", fields.phone);
  set("email", fields.email);
  set("contact_note", fields.contact_note);
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
  payload.skills = B.talentSkills.get();
  payload.languages = B.talentLangs.get();
  payload.desired_countries = B.talentCountries.get();
  payload.experience_years = parseFloat(payload.experience_years || "0");
  payload.desired_salary = parseInt(payload.desired_salary || "0", 10);
  try {
    await api("/api/talents", { method: "POST", body: JSON.stringify(payload) });
    e.target.reset();
    B.talentSkills.clear(); B.talentLangs.clear(); B.talentCountries.clear();
    toast("人材を登録しました"); loadTalents();
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
    const reqLangs = (j.required_languages || []).map(l => `<span class="chip green">${esc(l.name)}≧Lv${l.min_level}</span>`).join("");
    const cur = j.currency || "JPY";
    const pay = cur === "JPY" ? `提示${j.offered_salary}万` : `提示${(j.offered_salary || 0).toLocaleString()} ${esc(cur)}`;
    const overseas = j.country && j.country !== "日本";
    const countryChip = `<span class="chip ${overseas ? "warn" : "gray"}">${overseas ? "🌐 " : ""}${esc(j.country || "日本")}</span>`;
    const visaChip = j.visa_support ? `<span class="chip green">ビザ支援あり</span>` : "";
    el.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${esc(j.title)}</div>
          <div class="card-meta">${esc(j.client_name || "")} ／ ${pay} ／ ${esc(j.type_os || "-")} ／ ${esc(j.location || "-")} ／ ${WORK_STYLE_JA[j.work_style] || j.work_style} ／ ${j.headcount}名</div>
        </div>
        <button class="ghost" data-del="${j.id}">削除</button>
      </div>
      <div class="chips">${countryChip}${visaChip}${req}${reqLangs}</div>
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
  payload.required_skills = B.jobSkills.get();
  payload.required_languages = B.jobLangs.get();
  payload.offered_salary = parseInt(payload.offered_salary || "0", 10);
  payload.headcount = parseInt(payload.headcount || "1", 10);
  payload.country = payload.country || "日本";
  payload.currency = payload.currency || "JPY";
  payload.visa_support = e.target.elements["visa_support"].checked;
  try {
    await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    e.target.reset(); B.jobSkills.clear(); B.jobLangs.clear();
    toast("求人を登録しました"); loadJobs();
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
            <div class="match-name">${esc(t.name)} <span class="card-meta">${esc(t.type_os || "")} ／ 経験${t.experience_years}年${t.nationality ? " ／ " + esc(t.nationality) : ""}${(t.languages || []).length ? " ／ " + (t.languages || []).map(l => esc(l.name)).join("・") : ""}</span></div>
          </div>
          <div class="score-pill ${scoreCls}">${c.score}</div>
        </div>
        <div class="reason">💡 ${esc(c.reason)}<span class="src">(${srcLabel})</span></div>
        <div class="bars">${bars}</div>
        <div class="match-actions">
          <button class="ghost" data-detail="${t.id}">個人情報・連絡先を表示</button>
        </div>
        ${personalInfoBlock(t)}
      </div>`;
    const dbtn = el.querySelector("[data-detail]");
    const dblock = el.querySelector(".contact-block");
    dbtn.onclick = () => {
      const hidden = dblock.hasAttribute("hidden");
      dblock.toggleAttribute("hidden");
      dbtn.textContent = hidden ? "個人情報・連絡先を隠す" : "個人情報・連絡先を表示";
    };
    container.appendChild(el);
  });
}

// マッチ候補の個人情報＋連絡先ブロック（既定は非表示）
function personalInfoBlock(t) {
  const row = (k, v) => v ? `<div class="cb-row"><span class="cb-key">${k}</span><span>${esc(v)}</span></div>` : "";
  const link = (k, href, v) => v ? `<div class="cb-row"><span class="cb-key">${k}</span><a href="${href}${esc(v)}">${esc(v)}</a></div>` : "";
  const countries = (t.desired_countries || []).join("・");
  const rows = [
    row("フリガナ", t.kana),
    row("希望年収", t.desired_salary ? `${t.desired_salary}万` : ""),
    row("希望勤務地", t.location),
    row("在留資格", t.visa_status),
    countries ? row("希望勤務国", countries) : "",
    link("電話", "tel:", t.phone),
    link("メール", "mailto:", t.email),
    row("その他", t.contact_note),
    row("プロフィール", t.profile),
  ].filter(Boolean).join("");
  return `<div class="contact-block" hidden>${rows || '<div class="contact-empty">登録情報がありません</div>'}</div>`;
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
