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
  if (name === "pipeline" && typeof loadPipeline === "function") loadPipeline();
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
          <div class="card-title">${esc(t.name)} <span class="card-meta">${esc(t.kana || "")}</span> ${trustBadge(t.trust)}</div>
          <div class="card-meta">経験${t.experience_years}年 ／ 希望${t.desired_salary}万 ／ ${esc(t.type_os || "-")} ／ ${esc(t.location || "-")} ／ ${WORK_STYLE_JA[t.work_style] || t.work_style}</div>
          ${natVisa ? `<div class="card-meta">${natVisa}</div>` : ""}
        </div>
        <div class="card-actions">
          <button class="ghost" data-edit="${t.id}">編集</button>
          <button class="ghost" data-verify="${t.id}">検証</button>
          <button class="ghost" data-contact="${t.id}">連絡先</button>
          <button class="ghost" data-del="${t.id}">削除</button>
        </div>
      </div>
      <div class="chips">${skills}${langs}<span class="chip ${AVAIL_CLS[t.availability]}">${AVAIL_JA[t.availability]}</span></div>
      ${countries}
      ${t.profile ? `<div class="card-meta">${esc(t.profile)}</div>` : ""}
      ${contactBlock(t)}`;
    el.querySelector("[data-edit]").onclick = () => editTalent(t);
    el.querySelector("[data-verify]").onclick = () => openVerification(t);
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
  // 追記項目
  set("desired_industry", t.desired_industry); set("employment_type", t.employment_type);
  set("relocation", t.relocation); set("gender", t.gender); set("birthdate", t.birthdate);
  set("address", t.address); set("education", t.education); set("certifications", t.certifications);
  set("work_history", t.work_history); set("overseas_experience", t.overseas_experience);
  set("self_pr", t.self_pr); set("future_goals", t.future_goals);
  const det = form.querySelector("details.more-section");
  if (det) det.open = !!(t.gender || t.birthdate || t.address || t.education || t.certifications ||
    t.work_history || t.overseas_experience || t.self_pr || t.future_goals);
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
  // 追記事項
  set("employment_type", j.employment_type); set("salary_detail", j.salary_detail);
  set("working_hours", j.working_hours); set("holidays", j.holidays);
  set("requirements", j.requirements); set("benefits", j.benefits);
  set("ideal_candidate", j.ideal_candidate); set("selection_flow", j.selection_flow);
  set("store_info", j.store_info);
  const det = form.querySelector("details.more-section");
  if (det) det.open = !!(j.employment_type || j.salary_detail || j.working_hours || j.holidays ||
    j.requirements || j.benefits || j.ideal_candidate || j.selection_flow || j.store_info);
  B.jobSkills.set(j.required_skills || []);
  B.jobLangs.set(j.required_languages || []);
  setEditMode("job", j.id, j.title);
  showTab("jobs");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

// 求人カードから直接マッチングを実行
function matchJob(jobId) {
  currentMatchJobId = String(jobId);
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
let currentMatchJobId = null;
document.getElementById("run-match").addEventListener("click", async () => {
  const jobId = document.getElementById("match-job").value;
  if (!jobId) { toast("求人を選択してください", true); return; }
  currentMatchJobId = jobId;
  const topN = parseInt(document.getElementById("match-topn").value || "5", 10);
  const useLlm = document.getElementById("match-llm").checked;
  const useLearned = document.getElementById("match-learned").checked;
  const container = document.getElementById("match-results");
  container.innerHTML = '<div class="empty">AI がピックアップ中…</div>';
  try {
    const candidates = await api(`/api/jobs/${jobId}/match`, {
      method: "POST",
      body: JSON.stringify({ top_n: topN, use_llm: useLlm, persist: false, use_learned: useLearned }),
    });
    renderMatches(candidates);
  } catch (err) {
    container.innerHTML = `<div class="empty">エラー: ${esc(err.message)}</div>`;
  }
});

// ビザ適格性ブロック（越境要素がある候補に表示）
const VISA_CLS = { eligible: "green", conditional: "blue", review: "warn", difficult: "danger" };
const VISA_LABEL = { eligible: "可能", conditional: "条件付き", review: "要確認", difficult: "困難" };
function visaBlock(v) {
  const cls = VISA_CLS[v.level] || "warn";
  const progs = (v.programs || []).map(p => `
    <div class="visa-prog">
      <span class="visa-plevel ${VISA_CLS[p.level] || "warn"}">${esc(VISA_LABEL[p.level] || "要確認")}</span>
      <div class="visa-pbody">
        <b>${esc(p.name)}</b>${p.sponsor ? ' <span class="visa-tag">要スポンサー</span>' : ""}
        <div class="visa-req">${esc(p.requirements)} ／ 目安: ${esc(p.months)}${p.notes ? " ／ " + esc(p.notes) : ""}</div>
      </div>
    </div>`).join("");
  const top = v.programs && v.programs[0] ? v.programs[0].name : "";
  return `<details class="visa-box">
    <summary>🛂 ビザ（${esc(v.country)}）：<span class="visa-badge ${cls}">${esc(v.level_label)}</span>
      <span class="visa-sum">${esc(top)}</span></summary>
    <div class="visa-progs">${progs}</div>
    <div class="visa-note">※ ${esc(v.disclaimer)}</div>
  </details>`;
}

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
            <div class="match-name">${esc(t.name)} <span class="card-meta">${esc(t.type_os || "")} ／ 経験${t.experience_years}年${t.nationality ? " ／ " + esc(t.nationality) : ""}${(t.languages || []).length ? " ／ " + (t.languages || []).map(l => esc(l.name)).join("・") : ""}</span> ${trustBadge(c.trust)}</div>
          </div>
          <div class="score-pill ${scoreCls}">${c.score}</div>
        </div>
        ${recip}
        <div class="reason">💡 ${esc(c.reason)}<span class="src">(${srcLabel})</span></div>
        ${(c.visa && c.visa.relevant) ? visaBlock(c.visa) : ""}
        ${groups}
        <div class="match-actions">
          <button class="ghost" data-detail="${t.id}">個人情報・連絡先を表示</button>
          <button class="ghost" data-verify="${t.id}">検証</button>
          <button class="secondary" data-save="${t.id}">＋採用管理に保存</button>
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
    el.querySelector("[data-verify]").onclick = () => openVerification(t);
    const sbtn = el.querySelector("[data-save]");
    sbtn.onclick = async () => {
      if (!currentMatchJobId) { toast("求人が特定できません", true); return; }
      try {
        await api("/api/matches", { method: "POST",
          body: JSON.stringify({ job_id: parseInt(currentMatchJobId, 10), talent_id: t.id }) });
        sbtn.textContent = "✓ 保存済み"; sbtn.disabled = true;
        toast("採用管理に保存しました");
      } catch (err) { toast(err.message, true); }
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

// ---------- 検証（信頼性の裏取り） ----------
const TRUST_CLS = { strong: "green", standard: "blue", basic: "warn", unverified: "gray" };
const VSTATUS_CLS = { verified: "green", pending: "warn", mismatch: "danger", unverified: "gray" };

// 検証スコアのバッジ（人材カード・マッチ結果に表示）
function trustBadge(trust) {
  if (!trust) return "";
  const cls = TRUST_CLS[trust.level] || "gray";
  const warn = trust.has_mismatch ? ' <span class="trust-warn">⚠相違</span>' : "";
  const title = `検証 ${trust.verified_count}/${trust.categories.length}項目・スコア${trust.score}`;
  return `<span class="trust-badge ${cls}" title="${title}">🔎 検証 ${trust.score}・${esc(trust.level_label)}${warn}</span>`;
}

let VERIFY_META = null;
let currentVerifyTalent = null;

async function loadVerifyMeta() {
  if (VERIFY_META) return VERIFY_META;
  VERIFY_META = await api("/api/verifications/meta");
  const opt = (o) => `<option value="${o.key}">${esc(o.label)}</option>`;
  document.getElementById("vm-category").innerHTML = VERIFY_META.categories.map(opt).join("");
  document.getElementById("vm-status").innerHTML = VERIFY_META.statuses.map(opt).join("");
  document.getElementById("vm-method").innerHTML =
    '<option value="">（未選択）</option>' + VERIFY_META.methods.map(opt).join("");
  return VERIFY_META;
}
function metaLabel(kind, key) {
  if (!VERIFY_META || !key) return key || "";
  const found = (VERIFY_META[kind] || []).find(o => o.key === key);
  return found ? found.label : key;
}

async function openVerification(talent) {
  currentVerifyTalent = talent;
  await loadVerifyMeta();
  document.getElementById("vm-title").textContent = `検証：${talent.name}`;
  document.getElementById("verify-modal").hidden = false;
  document.body.classList.add("modal-open");
  await loadVerifications();
}
function closeVerification() {
  document.getElementById("verify-modal").hidden = true;
  document.body.classList.remove("modal-open");
  currentVerifyTalent = null;
  // 一覧のバッジを最新化
  loadTalents();
}

async function loadVerifications() {
  if (!currentVerifyTalent) return;
  const data = await api(`/api/talents/${currentVerifyTalent.id}/verifications`);
  renderVmTrust(data.trust);
  renderVmList(data.items);
}

function renderVmTrust(t) {
  const cls = TRUST_CLS[t.level] || "gray";
  const cats = t.categories.map(c =>
    `<span class="vm-cat ${VSTATUS_CLS[c.status] || "gray"}" title="重み${c.weight}">${esc(c.label)}: ${esc(c.status_label)}</span>`
  ).join("");
  const warn = t.has_mismatch ? `<div class="vm-mismatch">⚠ 相違ありの項目があります。内容をご確認ください。</div>` : "";
  document.getElementById("vm-trust").innerHTML = `
    <div class="vm-score-row">
      <div class="vm-score ${cls}">${t.score}<span>/100</span></div>
      <div class="vm-score-meta">
        <div class="vm-level ${cls}">${esc(t.level_label)}</div>
        <div class="hint">確認済 ${t.verified_count} ／ 確認中 ${t.pending_count} ／ 全 ${t.total_items} 項目</div>
      </div>
    </div>
    <div class="vm-cats">${cats}</div>${warn}`;
}

function renderVmList(items) {
  const list = document.getElementById("vm-list");
  if (!items.length) {
    list.innerHTML = '<div class="empty">検証項目はまだありません。上のフォームから追加してください。</div>';
    return;
  }
  list.innerHTML = "";
  for (const v of items) {
    const el = document.createElement("div");
    el.className = "vm-item";
    const statusOpts = VERIFY_META.statuses.map(s =>
      `<option value="${s.key}" ${v.status === s.key ? "selected" : ""}>${esc(s.label)}</option>`).join("");
    const when = v.verified_at ? `<span class="vm-when">確認 ${esc(v.verified_at.slice(0, 10))}</span>` : "";
    el.innerHTML = `
      <div class="vm-item-main">
        <span class="vm-badge ${VSTATUS_CLS[v.status] || "gray"}">${esc(metaLabel("categories", v.category))}</span>
        <div class="vm-item-body">
          <div class="vm-item-title">${esc(v.item || "（対象未記入）")}
            ${v.method ? `<span class="vm-method-tag">${esc(metaLabel("methods", v.method))}</span>` : ""}${when}</div>
          ${v.evidence ? `<div class="vm-item-sub">証跡: ${esc(v.evidence)}</div>` : ""}
          ${v.note ? `<div class="vm-item-sub">${esc(v.note)}</div>` : ""}
          ${v.verified_by ? `<div class="vm-item-sub">担当: ${esc(v.verified_by)}</div>` : ""}
        </div>
      </div>
      <div class="vm-item-actions">
        <select data-vstatus="${v.id}">${statusOpts}</select>
        <button class="ghost" data-vdel="${v.id}">削除</button>
      </div>`;
    el.querySelector("[data-vstatus]").onchange = async e => {
      await api(`/api/verifications/${v.id}`, { method: "PATCH", body: JSON.stringify({ status: e.target.value }) });
      loadVerifications();
    };
    el.querySelector("[data-vdel]").onclick = async () => {
      if (!confirm("この検証項目を削除しますか？")) return;
      await api(`/api/verifications/${v.id}`, { method: "DELETE" });
      toast("削除しました"); loadVerifications();
    };
    list.appendChild(el);
  }
}

document.getElementById("verify-form").addEventListener("submit", async e => {
  e.preventDefault();
  if (!currentVerifyTalent) return;
  const payload = Object.fromEntries(new FormData(e.target));
  try {
    await api(`/api/talents/${currentVerifyTalent.id}/verifications`,
      { method: "POST", body: JSON.stringify(payload) });
    e.target.reset();
    toast("検証を追加しました"); loadVerifications();
  } catch (err) { toast(err.message, true); }
});
document.querySelectorAll("#verify-modal [data-close]").forEach(el =>
  el.addEventListener("click", closeVerification));
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !document.getElementById("verify-modal").hidden) closeVerification();
});

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

// ---------- 採用管理（アウトカム学習） ----------
const STATUS_JA = { proposed: "提案", interview: "面接", offer: "内定", hired: "採用", rejected: "不採用" };
const STATUS_OPTS = ["proposed", "interview", "offer", "hired", "rejected"];

async function patchMatch(id, body) {
  await api(`/api/matches/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

function renderPlMetrics(m) {
  const tile = (num, unit, label, sub, cls) => `
    <div class="kpi ${cls || ""}">
      <div class="kpi-num">${num}<span class="unit">${unit}</span></div>
      <div class="kpi-label">${label}</div>${sub ? `<div class="kpi-sub">${sub}</div>` : ""}
    </div>`;
  document.getElementById("pl-metrics").innerHTML = `<div class="kpi-row">
    ${tile(m.total, "件", "📈 保存中の候補", "選考パイプライン")}
    ${tile(m.hired, "名", "採用", `在籍 ${m.active} ／ 離職 ${m.left}`, "kpi-accent")}
    ${tile(m.retention_rate == null ? "–" : m.retention_rate, "%", "定着率",
      m.avg_retention_days ? `平均在籍 ${m.avg_retention_days} 日` : "", "kpi-green")}
    ${tile(m.decision_rate == null ? "–" : m.decision_rate, "%", "決定率", "採用/(採用+不採用)")}
  </div>`;
}

function renderPlLearning(L) {
  const el = document.getElementById("pl-learning");
  if (!L.n_labeled) {
    el.innerHTML = '<div class="db-empty">まだ学習データがありません。採用・不採用・定着の結果を記録すると、成功に効いた観点を学習します。</div>';
    return;
  }
  const imp = Object.entries(L.importances)
    .map(([k, v]) => ({ label: L.labels[k] || k, v }))
    .sort((a, b) => b.v - a.v);
  const rows = imp.map(i => {
    const w = Math.min(100, Math.abs(i.v) * 100);
    const cls = i.v > 0.02 ? "pos" : (i.v < -0.02 ? "neg" : "zero");
    return `<div class="imp-row">
      <div class="imp-label">${esc(i.label)}</div>
      <div class="imp-track"><div class="imp-fill ${cls}" style="width:${w.toFixed(0)}%"></div></div>
      <div class="imp-val">${i.v > 0 ? "+" : ""}${i.v}</div>
    </div>`;
  }).join("");
  el.innerHTML = `
    <div class="pl-conf">学習の信頼度: <b>${Math.round(L.confidence * 100)}%</b>
      （実績 ${L.n_labeled} 件 ／ 成功 ${L.n_success}・失敗 ${L.n_failure}）</div>
    <div class="imp-title">成功採用への寄与度（観点別）</div>
    <div class="imp-list">${rows}</div>`;
}

function renderPlList(matches) {
  const list = document.getElementById("pl-list");
  list.innerHTML = matches.length ? "" : '<div class="empty">保存された候補はありません。マッチング結果の「＋採用管理に保存」から追加してください。</div>';
  for (const m of matches) {
    const el = document.createElement("div");
    el.className = "card";
    const opts = STATUS_OPTS.map(s => `<option value="${s}" ${m.status === s ? "selected" : ""}>${STATUS_JA[s]}</option>`).join("");
    const hired = m.status === "hired";
    const retSel = hired ? `
      <label class="pl-inline">定着
        <select data-ret="${m.id}">
          <option value="" ${!m.retention ? "selected" : ""}>未設定</option>
          <option value="active" ${m.retention === "active" ? "selected" : ""}>在籍中</option>
          <option value="left" ${m.retention === "left" ? "selected" : ""}>離職</option>
        </select>
      </label>
      <label class="pl-inline">在籍日数<input type="number" data-days="${m.id}" value="${m.retention_days || 0}" /></label>` : "";
    const leftReason = (hired && m.retention === "left")
      ? `<label class="pl-inline pl-grow">離職理由<input data-reason="${m.id}" value="${esc(m.left_reason || "")}" /></label>` : "";
    el.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${esc(m.talent ? m.talent.name : "?")} <span class="card-meta">適合 ${m.score}</span></div>
          <div class="card-meta">${esc(m.job_title || "")}（${esc(m.client_name || "")}）</div>
        </div>
        <button class="ghost" data-del="${m.id}">削除</button>
      </div>
      <div class="pl-controls">
        <label class="pl-inline">ステータス<select data-status="${m.id}">${opts}</select></label>
        ${retSel}${leftReason}
      </div>`;
    el.querySelector("[data-status]").onchange = async e => { await patchMatch(m.id, { status: e.target.value }); loadPipeline(); };
    const rs = el.querySelector("[data-ret]");
    if (rs) rs.onchange = async e => { await patchMatch(m.id, { retention: e.target.value }); loadPipeline(); };
    const dd = el.querySelector("[data-days]");
    if (dd) dd.onchange = async e => { await patchMatch(m.id, { retention_days: parseInt(e.target.value || "0", 10) }); loadPipeline(); };
    const rr = el.querySelector("[data-reason]");
    if (rr) rr.onchange = async e => { await patchMatch(m.id, { left_reason: e.target.value }); };
    el.querySelector("[data-del]").onclick = async () => {
      if (!confirm("この候補を採用管理から削除しますか？")) return;
      await api(`/api/matches/${m.id}`, { method: "DELETE" });
      toast("削除しました"); loadPipeline();
    };
    list.appendChild(el);
  }
}

async function loadPipeline() {
  try {
    const [matches, L] = await Promise.all([api("/api/matches"), api("/api/learning")]);
    renderPlMetrics(L.metrics);
    renderPlLearning(L.learned);
    renderPlList(matches);
  } catch (err) {
    document.getElementById("pl-list").innerHTML = `<div class="empty">読み込みに失敗しました: ${esc(err.message)}</div>`;
  }
}

function refreshAll() {
  loadDashboard(); loadClients(); loadTalents(); loadJobs();
}

// 初期ロード
loadHealth();
refreshAll();
