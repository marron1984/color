"use strict";

// ---------- 共通ヘルパ ----------
async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, m =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}
function toast(msg, isErr = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => (t.className = "toast"), 2600);
}
function money(n, cur) {
  if (!n) return "応相談";
  return (cur && cur !== "JPY") ? `${cur} ${Number(n).toLocaleString()}` : `${Number(n).toLocaleString()}万円`;
}

const TRUST_CLS = { strong: "green", standard: "blue", basic: "warn", unverified: "gray" };
function trustBadge(tr) {
  if (!tr) return "";
  const cls = TRUST_CLS[tr.level] || "gray";
  const warn = tr.has_mismatch ? ' <span class="trust-warn">⚠</span>' : "";
  return `<span class="trust-badge ${cls}">🔎 検証 ${tr.score}・${esc(tr.level_label)}${warn}</span>`;
}

const params = new URLSearchParams(location.search);
const clientToken = params.get("c");
const talentToken = params.get("t");

// ==================== 企業ポータル ====================
async function loadClientPortal(token) {
  const data = await api(`/api/portal/client/${encodeURIComponent(token)}`);
  document.getElementById("portal-title").textContent = "企業ポータル";
  document.getElementById("portal-sub").textContent = `${data.client.name} 様｜ご提案中の候補`;
  document.title = `企業ポータル｜${data.client.name}`;
  const root = document.getElementById("portal-root");
  if (!data.jobs.length) {
    root.innerHTML = '<div class="panel"><div class="empty">現在ご提案中の求人はありません。</div></div>';
    return;
  }
  root.innerHTML = "";
  for (const jw of data.jobs) {
    const j = jw.job;
    const panel = document.createElement("div");
    panel.className = "panel";
    const meta = [
      j.country, j.location, j.employment_type,
      j.offered_salary ? money(j.offered_salary, j.currency) : "",
    ].filter(Boolean).join(" ／ ");
    panel.innerHTML = `
      <h2>${esc(j.title)}</h2>
      <p class="hint">${esc(meta)}${j.visa_support ? " ／ ビザサポートあり" : ""}</p>
      <div class="portal-cands"></div>`;
    const wrap = panel.querySelector(".portal-cands");
    if (!jw.candidates.length) {
      wrap.innerHTML = '<div class="empty">候補の選定中です。</div>';
    } else {
      jw.candidates.forEach((cand, i) => wrap.appendChild(clientCandidateCard(token, cand, i)));
    }
    root.appendChild(panel);
  }
}

function clientCandidateCard(token, c, i) {
  const el = document.createElement("div");
  el.className = "pc-card";
  const skills = (c.skills || []).map(s => `<span class="chip">${esc(s.name)} Lv${s.level}</span>`).join("");
  const langs = (c.languages || []).map(l => `<span class="chip green">${esc(l)}</span>`).join("");
  const scoreCls = c.score >= 75 ? "high" : c.score < 50 ? "low" : "";
  const meta = [
    c.type_os, `経験${c.experience_years}年`, c.nationality,
    c.visa_status,
  ].filter(Boolean).join(" ／ ");
  const chosen = c.client_interest;
  el.innerHTML = `
    <div class="pc-head">
      <div>
        <div class="pc-name">候補 ${i + 1}：${esc(c.display_name)} ${trustBadge(c.trust)}</div>
        <div class="card-meta">${esc(meta)}</div>
      </div>
      <div class="score-pill ${scoreCls}">${c.score}</div>
    </div>
    <div class="chips">${skills}${langs}</div>
    ${c.reason ? `<div class="reason">💡 ${esc(c.reason)}</div>` : ""}
    <div class="pc-actions">
      <button class="secondary" data-int="interested" ${chosen === "interested" ? "disabled" : ""}>
        ${chosen === "interested" ? "✓ 面接を希望済み" : "この候補に興味あり／面接希望"}</button>
      <button class="ghost" data-int="passed" ${chosen === "passed" ? "disabled" : ""}>
        ${chosen === "passed" ? "✓ 見送り済み" : "見送る"}</button>
    </div>
    <div class="pc-note">※ お名前・ご連絡先はシーコレクションが仲介いたします。「興味あり」で担当者に通知されます。</div>`;
  el.querySelectorAll("[data-int]").forEach(btn => {
    btn.onclick = async () => {
      try {
        await api(`/api/portal/client/${encodeURIComponent(token)}/matches/${c.match_id}`,
          { method: "POST", body: JSON.stringify({ interest: btn.dataset.int }) });
        toast(btn.dataset.int === "interested" ? "面接希望を送信しました" : "見送りを記録しました");
        loadClientPortal(token);
      } catch (err) { toast(err.message, true); }
    };
  });
  return el;
}

// ==================== 候補者ポータル ====================
async function loadTalentPortal(token) {
  const data = await api(`/api/portal/talent/${encodeURIComponent(token)}`);
  document.getElementById("portal-title").textContent = "候補者ポータル";
  document.getElementById("portal-sub").textContent = `${data.talent.name} 様｜あなたへのご提案求人`;
  document.title = `候補者ポータル｜${data.talent.name}`;
  const root = document.getElementById("portal-root");
  if (!data.offers.length) {
    root.innerHTML = '<div class="panel"><div class="empty">現在ご提案中の求人はありません。担当者からのご連絡をお待ちください。</div></div>';
    return;
  }
  root.innerHTML = "";
  data.offers.forEach(o => root.appendChild(talentOfferCard(token, o)));
}

function talentOfferCard(token, o) {
  const el = document.createElement("div");
  el.className = "panel";
  const rows = [
    ["勤務国・地域", o.country],
    ["勤務地", o.location],
    ["給与", money(o.offered_salary, o.currency)],
    ["雇用形態", o.employment_type],
    ["勤務時間", o.working_hours],
    ["休日", o.holidays],
    ["福利厚生", o.benefits],
    ["応募資格", o.requirements],
    ["求める人物像", o.ideal_candidate],
  ].filter(r => r[1]).map(r => `<div class="cb-row"><span class="cb-key">${esc(r[0])}</span><span>${esc(r[1])}</span></div>`).join("");
  const chosen = o.candidate_interest;
  el.innerHTML = `
    <div class="pc-head">
      <div>
        <h2>${esc(o.title)}</h2>
        <div class="card-meta">${esc(o.client_name || "")}${o.visa_support ? " ／ ビザサポートあり" : ""}</div>
      </div>
      <div class="score-pill ${o.score >= 75 ? "high" : ""}">${o.score}</div>
    </div>
    ${o.reason ? `<div class="reason">💡 ${esc(o.reason)}</div>` : ""}
    ${o.description ? `<div class="card-meta pre">${esc(o.description)}</div>` : ""}
    <div class="contact-block" style="margin-top:10px">${rows}</div>
    <div class="pc-actions">
      <button class="secondary" data-int="interested" ${chosen === "interested" ? "disabled" : ""}>
        ${chosen === "interested" ? "✓ 応募の意思を送信済み" : "この求人に応募したい"}</button>
      <button class="ghost" data-int="declined" ${chosen === "declined" ? "disabled" : ""}>
        ${chosen === "declined" ? "✓ 見送り済み" : "今回は見送る"}</button>
    </div>`;
  el.querySelectorAll("[data-int]").forEach(btn => {
    btn.onclick = async () => {
      try {
        await api(`/api/portal/talent/${encodeURIComponent(token)}/matches/${o.match_id}`,
          { method: "POST", body: JSON.stringify({ interest: btn.dataset.int }) });
        toast(btn.dataset.int === "interested" ? "応募の意思を送信しました" : "見送りを記録しました");
        loadTalentPortal(token);
      } catch (err) { toast(err.message, true); }
    };
  });
  return el;
}

// ---------- 起動 ----------
(async function () {
  const root = document.getElementById("portal-root");
  try {
    if (clientToken) await loadClientPortal(clientToken);
    else if (talentToken) await loadTalentPortal(talentToken);
    else root.innerHTML = '<div class="panel"><div class="empty">リンクが正しくありません。担当者から共有されたリンクをご利用ください。</div></div>';
  } catch (err) {
    root.innerHTML = `<div class="panel"><div class="empty">${esc(err.message === "リンクが無効です" ? "リンクが無効か、有効期限が切れています。担当者にお問い合わせください。" : err.message)}</div></div>`;
  }
})();
