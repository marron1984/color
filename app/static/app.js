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
function showTab(name) {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  const panel = document.getElementById("tab-" + name);
  if (panel) panel.classList.add("active");
  if (name === "dashboard" && typeof loadDashboard === "function") loadDashboard();
}
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => showTab(btn.dataset.tab));
});

// ---------- 編集モード ----------
const editState = { client: null, talent: null, job: null };

function setEditMode(kind, id, name) {
  editState[kind] = id;
  const form = document.getElementById(kind + "-form");
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.textContent = id ? "更新" : "登録";
  const banner = document.getElementById(kind + "-edit");
  if (banner) {
    banner.hidden = !id;
    const nm = banner.querySelector(".edit-name");
    if (nm) nm.textContent = name || "";
  }
}

function clearForm(kind) {
  const form = document.getElementById(kind + "-form");
  form.reset();
  if (kind === "talent") { B.talentSkills.clear(); B.talentLangs.clear(); B.talentCountries.clear(); }
  if (kind === "job") { B.jobSkills.clear(); B.jobLangs.clear(); }
  setEditMode(kind, null);
}

document.querySelectorAll("[data-cancel]").forEach(btn => {
  btn.addEventListener("click", () => clearForm(btn.dataset.cancel));
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
          <div class="card-meta">${esc(c.industry || "")} ／ ${esc(c.contact_name || "-")} ／ ${esc(c.phone || "-")}</div>
          ${c.address ? `<div class="card-meta">📍 ${esc(c.address)}</div>` : ""}
        </div>
        <div class="card-actions">
          <button class="ghost" data-edit="${c.id}">編集</button>
          <button class="ghost" data-del="${c.id}">削除</button>
        </div>
      </div>
      <div class="chips"><span class="chip ${c.kind === "existing" ? "green" : ""}">${KIND_JA[c.kind] || c.kind}</span></div>
      ${c.notes ? `<div class="card-meta pre">${esc(c.notes)}</div>` : ""}`;
    el.querySelector("[data-edit]").onclick = () => editClient(c);
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

function editClient(c) {
  const form = document.getElementById("client-form");
  const set = (n, v) => { if (form.elements[n] !== undefined) form.elements[n].value = v ?? ""; };
  set("name", c.name); set("kind", c.kind); set("industry", c.industry); set("address", c.address);
  set("contact_name", c.contact_name); set("contact_email", c.contact_email);
  set("phone", c.phone); set("notes", c.notes);
  setEditMode("client", c.id, c.name);
  showTab("clients");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("client-form").addEventListener("submit", async e => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(e.target));
  const id = editState.client;
  try {
    if (id) await api(`/api/clients/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/api/clients", { method: "POST", body: JSON.stringify(payload) });
    clearForm("client"); toast(id ? "店舗を更新しました" : "店舗を登録しました"); loadClients();
  } catch (err) { toast(err.message, true); }
});

// 食べログから店舗情報を取得してフォームに反映
document.getElementById("tabelog-btn").addEventListener("click", async () => {
  const urlEl = document.getElementById("tabelog-url");
  const status = document.getElementById("tabelog-status");
  const url = (urlEl.value || "").trim();
  if (!url) { toast("食べログの URL を入力してください", true); return; }
  status.textContent = "取得中…"; status.className = "resume-status loading";
  try {
    const data = await api("/api/clients/fetch-tabelog", {
      method: "POST", body: JSON.stringify({ url }),
    });
    const form = document.getElementById("client-form");
    const set = (name, val) => { if (val && form.elements[name]) form.elements[name].value = val; };
    set("name", data.fields.name);
    set("industry", data.fields.industry);
    set("address", data.fields.address);
    set("phone", data.fields.phone);
    set("notes", data.fields.notes);
    status.textContent = "✓ 取得しました（内容をご確認ください）"; status.className = "resume-status";
    toast("食べログから取得しました");
  } catch (err) {
    status.textContent = ""; status.className = "resume-status err";
    toast(err.message, true);
  }
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
          <button class="ghost" data-edit="${t.id}">編集</button>
          <button class="ghost" data-contact="${t.id}">連絡先</button>
          <button class="ghost" data-del="${t.id}">削除</button>
        </div>
      </div>
      <div class="chips">${skills}${langs}<span class="chip ${AVAIL_CLS[t.availability]}">${AVAIL_JA[t.availability]}</span></div>
      ${countries}
      ${t.profile ? `<div class="card-meta">${esc(t.profile)}</div>` : ""}
      ${contactBlock(t)}`;
    el.querySelector("[data-edit]").onclick = () => editTalent(t);
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

// 既存人材をフォームに読み込んで編集モードに
function editTalent(t) {
  const form = document.getElementById("talent-form");
  const set = (n, v) => { if (form.elements[n] !== undefined) form.elements[n].value = v ?? ""; };
  set("name", t.name); set("kana", t.kana);
  set("experience_years", t.experience_years); set("desired_salary", t.desired_salary);
  set("type_os", t.type_os); set("work_style", t.work_style); set("location", t.location);
  set("availability", t.availability);
  set("nationality", t.nationality); set("visa_status", t.visa_status);
  set("phone", t.phone); set("email", t.email); set("contact_note", t.contact_note);
  set("profile", t.profile);
  B.talentSkills.set(t.skills || []);
  B.talentLangs.set(t.languages || []);
  B.talentCountries.set(t.desired_countries || []);
  setEditMode("talent", t.id, t.name);
  showTab("talents");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
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
  const id = editState.talent;
  try {
    if (id) await api(`/api/talents/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/api/talents", { method: "POST", body: JSON.stringify(payload) });
    clearForm("talent");
    toast(id ? "人材を更新しました" : "人材を登録しました"); loadTalents();
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
        <div class="card-actions">
          <button class="ghost" data-edit="${j.id}">編集</button>
          <button class="ghost" data-del="${j.id}">削除</button>
        </div>
      </div>
      <div class="chips">${countryChip}${visaChip}${req}${reqLangs}</div>
      ${j.description ? `<div class="card-meta">${esc(j.description)}</div>` : ""}
      <button class="secondary job-match-btn" data-match="${j.id}">🎯 この求人でマッチング</button>`;
    el.querySelector("[data-edit]").onclick = () => editJob(j);
    el.querySelector("[data-match]").onclick = () => matchJob(j.id);
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

// 既存求人をフォームに読み込んで編集モードに
function editJob(j) {
  const form = document.getElementById("job-form");
  document.getElementById("job-client").value = j.client_id;
  const set = (n, v) => { if (form.elements[n] !== undefined) form.elements[n].value = v ?? ""; };
  set("title", j.title); set("offered_salary", j.offered_salary); set("type_os", j.type_os);
  set("work_style", j.work_style); set("location", j.location); set("headcount", j.headcount);
  set("country", j.country); set("currency", j.currency); set("description", j.description);
  form.elements["visa_support"].checked = !!j.visa_support;
  B.jobSkills.set(j.required_skills || []);
  B.jobLangs.set(j.required_languages || []);
  setEditMode("job", j.id, j.title);
  showTab("jobs");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 求人カードから直接マッチングを実行
function matchJob(jobId) {
  const sel = document.getElementById("match-job");
  sel.value = String(jobId);
  showTab("match");
  document.getElementById("run-match").click();
  document.getElementById("tab-match").scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("job-form").addEventListener("submit", async e => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(e.target));
  payload.client_id = parseInt(document.getElementById("job-client").value, 10);
  payload.required_skills = B.jobSkills.get();
  payload.required_languages = B.jobLangs.get();
  payload.offered_salary = parseInt(payload.offered_salary || "0", 10);
  payload.headcount = parseInt(payload.headcount || "1", 10);
  payload.country = payload.country || "日本";
  payload.currency = payload.currency || "JPY";
  payload.visa_support = e.target.elements["visa_support"].checked;
  const id = editState.job;
  try {
    if (id) await api(`/api/jobs/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    clearForm("job"); toast(id ? "求人を更新しました" : "求人を登録しました"); loadJobs();
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
    const bd = c.breakdown;
    const barsFor = (side) => (bd.components || []).filter(x => (x.side || "employer") === side).map(comp => `
      <div class="bar-label">${esc(comp.label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${comp.score}%"></div><span class="bar-val">${comp.score}</span></div>
      ${comp.detail ? `<div class="bar-detail">${esc(comp.detail)}</div>` : ""}`).join("");
    const emp = bd.employer_fit, cand = bd.candidate_fit;
    const recip = (emp != null && cand != null) ? `
      <div class="recip">
        <span class="recip-pill">企業ニーズ適合 <b>${emp}</b></span>
        <span class="recip-x">×</span>
        <span class="recip-pill cand">本人希望適合 <b>${cand}</b></span>
        ${bd.percentile != null ? `<span class="recip-rank">候補内 上位${bd.percentile}%</span>` : ""}
      </div>` : "";
    const groups = recip ? `
      <div class="bar-group"><div class="bar-group-title">企業→人材（要件の充足）</div><div class="bars">${barsFor("employer")}</div></div>
      <div class="bar-group"><div class="bar-group-title">人材→企業（本人の希望）</div><div class="bars">${barsFor("candidate")}</div></div>`
      : `<div class="bars">${barsFor("employer")}${barsFor("candidate")}</div>`;
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
        ${recip}
        <div class="reason">💡 ${esc(c.reason)}<span class="src">(${srcLabel})</span></div>
        ${groups}
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
    // 一時ストレージ（非永続）で動作している場合は警告を表示
    const warn = document.getElementById("storage-warning");
    if (warn) warn.hidden = h.persistent !== false ? true : false;
  } catch (_) {}
}

// ---------- ダッシュボード ----------
function barList(items) {
  if (!items || !items.length) return '<div class="db-empty">データがありません</div>';
  const max = Math.max(1, ...items.map(i => i.count));
  return items.map(i => `
    <div class="db-bar-row">
      <div class="db-bar-label" title="${esc(i.name)}">${esc(i.name)}</div>
      <div class="db-bar-track"><div class="db-bar-fill" style="width:${(i.count / max * 100).toFixed(1)}%${i.count ? "" : ";min-width:0"}"></div></div>
      <div class="db-bar-val">${i.count}</div>
    </div>`).join("");
}

function statusBars(t) {
  const rows = [
    { label: "即勤務可", count: t.available, color: "var(--accent-2)" },
    { label: "勤務中", count: t.assigned, color: "var(--warn)" },
    { label: "対応不可", count: t.unavailable, color: "var(--muted)" },
  ];
  const max = Math.max(1, ...rows.map(r => r.count));
  return rows.map(r => `
    <div class="db-bar-row">
      <div class="db-bar-label">${r.label}</div>
      <div class="db-bar-track"><div class="db-bar-fill" style="width:${(r.count / max * 100).toFixed(1)}%;background:${r.color}${r.count ? "" : ";min-width:0"}"></div></div>
      <div class="db-bar-val">${r.count}</div>
    </div>`).join("");
}

async function loadDashboard() {
  const root = document.getElementById("dashboard");
  try {
    const s = await api("/api/stats");
    root.innerHTML = `
      <div class="kpi-row">
        <div class="kpi" data-go="clients">
          <div class="kpi-num">${s.clients.total}<span class="unit">店</span></div>
          <div class="kpi-label">🏬 店舗</div>
          <div class="kpi-sub">新規 ${s.clients.new} ／ 既存 ${s.clients.existing}</div>
        </div>
        <div class="kpi kpi-green" data-go="talents">
          <div class="kpi-num">${s.talents.available}<span class="unit">名</span></div>
          <div class="kpi-label">🧑‍🍳 稼働可能な人材</div>
          <div class="kpi-sub">登録 ${s.talents.total} 名中</div>
        </div>
        <div class="kpi kpi-accent" data-go="jobs">
          <div class="kpi-num">${s.jobs.open}<span class="unit">件</span></div>
          <div class="kpi-label">📋 募集中の求人</div>
          <div class="kpi-sub">募集 ${s.jobs.headcount} 名 ／ 海外 ${s.jobs.overseas} 件</div>
        </div>
        <div class="kpi" data-go="match">
          <div class="kpi-num">${s.matches.total}<span class="unit">件</span></div>
          <div class="kpi-label">🎯 保存済みマッチ</div>
          <div class="kpi-sub">クリックでマッチングへ</div>
        </div>
      </div>
      <div class="db-grid">
        <div class="panel db-card"><h3>人材の稼働状況</h3><div class="db-bars">${statusBars(s.talents)}</div></div>
        <div class="panel db-card"><h3>職種別の人材</h3><div class="db-bars">${barList(s.talent_by_type)}</div></div>
        <div class="panel db-card"><h3>国籍別の人材</h3><div class="db-bars">${barList(s.talent_by_nationality)}</div></div>
        <div class="panel db-card"><h3>勤務国別の求人</h3><div class="db-bars">${barList(s.jobs_by_country)}</div></div>
      </div>`;
    root.querySelectorAll("[data-go]").forEach(el => {
      el.onclick = () => showTab(el.dataset.go);
    });
  } catch (err) {
    root.innerHTML = `<div class="empty">読み込みに失敗しました: ${esc(err.message)}</div>`;
  }
}

function refreshAll() {
  loadDashboard(); loadClients(); loadTalents(); loadJobs();
}

// 初期ロード
loadHealth();
refreshAll();
