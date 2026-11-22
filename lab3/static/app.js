Chart.defaults.animation = false;
Chart.defaults.font.family = '"Segoe UI", Arial, sans-serif';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (x, d = 3) => (x == null ? '—' : Number(x).toFixed(d).replace('.', ','));
const pct = (x) => (x == null ? '—' : (100 * x).toFixed(1).replace('.', ',') + '%');
const LANG = { fr: 'французский', it: 'итальянский' };
const DOMAIN = { cs: 'научная статья (CS)', lit: 'сочинение по литературе' };
let docs = [], charts = {};

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
}
const status = (t) => { $('#status').textContent = t; };

document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.id === 'tab-' + name));
  if (name === 'eval') loadEval();
  if (name === 'summary' && !$('#sum-doc').value) fillSelects();
  if (name === 'kb') openKb($('#kb-doc').value);
  history.replaceState(null, '', '#' + name);
}
function showHelp(section) {
  showTab('help');
  const el = document.getElementById('help-' + section);
  if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
}

const drop = $('#drop');
['dragenter', 'dragover'].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', (ev) => upload(ev.dataTransfer.files));
$('#file').addEventListener('change', (ev) => { upload(ev.target.files); ev.target.value = ''; });

async function upload(files) {
  if (!files.length) return;
  const fd = new FormData();
  [...files].forEach((f) => fd.append('files', f));
  fd.append('lang', $('#up-lang').value);
  fd.append('domain', $('#up-domain').value);
  status('Загрузка…');
  const r = await api('/api/documents', { method: 'POST', body: fd });
  status(`Загружено: ${r.added.length}` + (r.errors.length ? `; ошибки: ${r.errors.map((e) => e.filename + ' — ' + e.error).join('; ')}` : ''));
  await refresh();
  if (r.added.length) await summarizeAll(true);
}
async function loadCollection() {
  status('Загрузка тестовой коллекции…');
  const r = await api('/api/collection', { method: 'POST' });
  status(`Загружено документов: ${r.added.length}`);
  await refresh();
  await summarizeAll(true);
}
async function deleteAll() {
  if (!docs.length) return;
  await api('/api/documents', { method: 'DELETE' });
  status('Коллекция очищена');
  await refresh();
}
async function deleteDoc(id) { await api('/api/documents/' + id, { method: 'DELETE' }); await refresh(); }
async function patchDoc(id, field, value) {
  await api('/api/documents/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [field]: value }) });
  await summarizeAll(true);
}
let summarizing = null;
async function summarizeAll(quiet) {
  if (summarizing) return summarizing;
  summarizing = (async () => {
    if (!docs.length && quiet !== true) { await refresh(); }
    status('Построение рефератов…');
    const body = { n_sentences: +$('#n-sent').value || 10, n_keywords: +$('#n-kw').value || 10 };
    const r = await api('/api/summarize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    status(`Рефераты построены: ${r.done.length} док. за ${fmt(r.total_ms, 0)} мс (включая запись в БД)`);
    await refresh();
  })();
  try { await summarizing; } finally { summarizing = null; }
}

async function refresh() {
  docs = await api('/api/documents');
  const tb = $('#doc-table tbody');
  tb.innerHTML = docs.map((d, i) => `<tr>
    <td>${i + 1}</td>
    <td><a href="/documents/${d.id}/file" target="_blank">${esc(d.filename)}</a><div class="muted">${esc(d.title)}</div></td>
    <td><select class="no-print-sel" onchange="patchDoc(${d.id},'lang',this.value)">${Object.entries(LANG).map(([k, v]) => `<option value="${k}" ${k === d.lang ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
    <td><select onchange="patchDoc(${d.id},'domain',this.value)">${Object.entries(DOMAIN).map(([k, v]) => `<option value="${k}" ${k === d.domain ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
    <td class="num">${d.pages}</td><td class="num">${d.n_paragraphs}</td><td class="num">${d.n_sentences}</td><td class="num">${d.words}</td>
    <td class="num">${d.time_ms == null ? '—' : fmt(d.time_ms, 1) + ' / ' + fmt(d.time_ostis, 1)}</td>
    <td class="no-print">${d.time_ms == null ? '' : `<button class="btn sm" onclick="gotoSummary(${d.id})">Реферат</button> `}<button class="btn sm" onclick="showText(${d.id})">Текст</button> <button class="btn sm danger" onclick="deleteDoc(${d.id})">✕</button></td>
  </tr>`).join('');
  $('#empty').style.display = docs.length ? 'none' : 'block';
  const done = docs.filter((d) => d.time_ms != null);
  const cnt = (f) => docs.filter(f).length;
  const avg = done.length ? done.reduce((a, d) => a + d.time_ms, 0) / done.length : null;
  $('#doc-cards').innerHTML = [
    ['Документов в коллекции', docs.length, `рефераты построены: ${done.length}`],
    ['По языкам', `${cnt((d) => d.lang === 'fr')} / ${cnt((d) => d.lang === 'it')}`, 'французский / итальянский'],
    ['По предметным областям', `${cnt((d) => d.domain === 'cs')} / ${cnt((d) => d.domain === 'lit')}`, 'статьи CS / сочинения по литературе'],
    ['Предложений в документах', docs.reduce((a, d) => a + d.n_sentences, 0), `слов: ${docs.reduce((a, d) => a + d.words, 0)}`],
    ['Среднее время реферата', avg == null ? '—' : fmt(avg, 1) + ' мс', 'на один документ'],
  ].map(([l, v, s]) => `<div class="card stat"><div class="l">${l}</div><div class="v">${v}</div><div class="l">${s}</div></div>`).join('');
  fillSelects();
}
function fillSelects() {
  const done = docs.filter((d) => d.time_ms != null);
  for (const sel of ['#sum-doc', '#kb-doc']) {
    const el = $(sel), cur = el.value;
    el.innerHTML = done.map((d) => `<option value="${d.id}">${esc(d.filename)} — ${esc(d.title)}</option>`).join('');
    if (done.some((d) => String(d.id) === cur)) el.value = cur;
  }
}
async function showText(id) {
  const d = await api(`/api/documents/${id}/text`);
  $('#modal-title').innerHTML = `${esc(d.title)} · <a href="/documents/${id}/file" target="_blank">${esc(d.filename)}</a>`;
  $('#modal-body').innerHTML = d.paragraphs.map((p) => `<p>${esc(p)}</p>`).join('');
  $('#modal').classList.add('open');
}
function closeModal() { $('#modal').classList.remove('open'); }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

let METHOD = 'extraction';
const METHOD_NAME = { extraction: 'Sentence extraction', ostis: 'Семантический метод OSTIS' };
function setMethod(m) {
  METHOD = m;
  document.querySelectorAll('#sum-method button').forEach((b) => b.classList.toggle('on', b.dataset.m === m));
  openSummary($('#sum-doc').value);
}
function gotoSummary(id) { showTab('summary'); $('#sum-doc').value = id; openSummary(id); }
function kwTree(kws) {
  return `<ul class="kw-tree">${kws.map((k) => `<li><b>${esc(k.term)}</b>${k.ru ? ` <span class="muted">[${esc(k.ru)}]</span>` : ''}<span class="w">${k.ru ? 'a' : 'w'} = ${fmt(k.weight)}, tf = ${k.tf}</span>
    ${k.children.length ? `<ul>${k.children.map((c) => `<li>${esc(c.phrase)}${c.ru ? ` <span class="muted">[${esc(c.ru)}]</span>` : ''}<span class="w">×${c.count}</span></li>`).join('')}</ul>` : ''}</li>`).join('')}</ul>`;
}
async function openSummary(id) {
  if (!id) return;
  const s = await api(`/api/documents/${id}/summary?method=${METHOD}`);
  const sem = s.method === 'ostis';
  const q = s.quality, refIdx = new Set(q ? q.reference_idx : []);
  const val = (x) => (sem ? x.sem_weight : x.weight) || 0;
  const maxW = Math.max(...s.sentences.map(val), 1e-9);
  const conceptCol = (x) => (x.concepts || []).map((c) => `<span class="chip">${esc(c.replace('concept_', ''))}</span>`).join('');
  $('#sum-body').innerHTML = `
  <div class="card">
    <div class="row between"><h2>${esc(s.doc.title)}</h2>
      <div class="no-print"><a class="btn" href="/api/report.html?ids=${id}">HTML</a> <a class="btn" href="/api/report.txt?ids=${id}">TXT</a> <a class="btn" href="/api/kb.scs?ids=${id}">SCs</a> <button class="btn" onclick="window.print()">Печать</button></div></div>
    <div>Исходный документ: <a href="/documents/${id}/file" target="_blank">${esc(s.doc.filename)}</a></div>
    <div class="meta"><span>Метод: <b>${s.method_name}</b></span><span>Язык: <b>${s.lang_name}</b></span><span>Область: <b>${s.domain_name}</b></span><span>Страниц: ${s.doc.pages}</span><span>Абзацев: ${s.doc.n_paragraphs}</span><span>Предложений: ${s.doc.n_sentences}</span><span>Слов: ${s.doc.words}</span>${sem ? `<span>Понятий найдено: ${s.concepts.length}</span>` : `<span>|DB| = ${s.db_size}</span>`}<span>Время: ${fmt(s.time_ms, 1)} мс</span></div>
    ${q ? `<div class="quality"><div>Совпало с эталоном: <b>${s.sentences.filter((x) => x.selected && refIdx.has(x.idx)).length} из ${s.summary.length}</b></div><div>P = ${pct(q.precision)}</div><div>R = ${pct(q.recall)}</div><div>F1 = ${pct(q.f1)}</div><div>Ключевые ${sem ? 'понятия' : 'слова'}: точность ${pct(q.kw_precision)}, покрытие эталона ${pct(q.kw_recall)}</div></div>` : ''}
  </div>
  <div class="split">
    <div class="card"><h3>${sem ? 'Семантический реферат' : 'Классический реферат'}</h3><ol class="summary-list">${s.summary.map((t) => `<li>${esc(t)}</li>`).join('')}</ol></div>
    <div class="card"><h3>${sem ? 'Ключевые понятия базы знаний' : 'Реферат в виде списка ключевых слов'}</h3>${kwTree(s.keywords)}
      ${q ? `<p class="muted">Эталонные ключевые слова: ${q.reference_keywords.map(esc).join('; ')}</p>` : ''}</div>
  </div>
  <div class="card"><h3>${sem ? 'Семантические веса предложений' : 'Веса предложений'}</h3>
    <table class="grid"><thead><tr><th class="num">№</th><th class="num">Абз.</th><th>Предложение</th>${sem ? '<th>Понятия базы знаний</th><th class="num">Σ a(c)</th>' : '<th class="num">Posd</th><th class="num">Posp</th><th class="num">Score</th><th class="num">Weight</th>'}<th class="num">Ранг</th></tr></thead>
    <tbody>${s.sentences.map((x) => `<tr class="${x.selected ? 'sel' : ''}"><td class="num">${x.idx + 1}${refIdx.has(x.idx) ? ' <span class="ref" title="эталонное предложение">★</span>' : ''}</td><td class="num">${x.paragraph + 1}</td><td>${esc(x.text)}</td>${sem ? `<td>${conceptCol(x)}</td><td class="num"><span class="bar" style="width:${Math.round(40 * val(x) / maxW)}px"></span> ${fmt(val(x), 2)}</td>` : `<td class="num">${fmt(x.posd)}</td><td class="num">${fmt(x.posp)}</td><td class="num">${fmt(x.score, 2)}</td><td class="num"><span class="bar" style="width:${Math.round(40 * x.weight / maxW)}px"></span> ${fmt(x.weight, 2)}</td>`}<td class="num">${x.rank}</td></tr>`).join('')}</tbody></table>
    <p class="muted">Зелёным выделены предложения, вошедшие в реферат; ★ — предложения эталонного реферата.${sem ? ' Предложения выбираются по приросту покрытия значимых понятий, поэтому ранг по Σ a(c) не совпадает с порядком выбора.' : ''}</p></div>
  ${sem ? `<div class="card"><h3>Понятия базы знаний, найденные в документе</h3>
    <table class="grid"><thead><tr><th>Понятие (sc-узел)</th><th>Идентификатор в тексте</th><th>Русское имя</th><th>Родитель (nrel_inclusion)</th><th class="num">tf(c,D)</th><th class="num">a0(c)</th><th class="num">a(c)</th></tr></thead>
    <tbody>${s.concepts.slice(0, 25).map((c) => `<tr><td><code>${esc(c.concept)}</code></td><td>${esc(c.name)}</td><td>${esc(c.ru)}</td><td><code>${esc(c.parent || '—')}</code></td><td class="num">${c.tf}</td><td class="num">${fmt(c.a0)}</td><td class="num">${fmt(c.activation)}</td></tr>`).join('')}</tbody></table>
    <p class="muted">a0(c) = 0,5·(1 + tf/tf<sub>max</sub>)·spec(c); a(c) = a0(c) + 0,2·Σ a0 соседних понятий онтологии. Понятия с tf = 0 получили активацию от соседей.</p></div>`
  : `<div class="card"><h3>Термины с наибольшим весом w(t,D)</h3>
    <table class="grid"><thead><tr><th>Термин (основа)</th><th class="num">tf(t,D)</th><th class="num">df(t)</th><th class="num">w(t,D)</th></tr></thead>
    <tbody>${s.terms.slice(0, 20).map((t) => `<tr><td>${esc(t.surface)} <span class="muted">(${esc(t.stem)})</span></td><td class="num">${t.tf}</td><td class="num">${t.df}</td><td class="num">${fmt(t.weight)}</td></tr>`).join('')}</tbody></table></div>`}`;
}

const EXAMPLES = {
  fr: "Un réseau de neurones est un modèle d'apprentissage automatique composé de couches de neurones artificiels. Chaque neurone calcule une somme pondérée de ses entrées et applique une fonction d'activation.\n\nL'apprentissage profond utilise des réseaux comportant de nombreuses couches. Les poids sont ajustés par rétropropagation et descente de gradient à partir des données d'apprentissage.\n\nLes réseaux convolutifs sont adaptés aux images, tandis que les transformeurs, fondés sur l'attention, dominent le traitement automatique des langues. Le surapprentissage reste un problème important lorsque les données sont rares.",
  it: "Il protocollo TCP garantisce una trasmissione affidabile dei dati su Internet. I dati vengono suddivisi in pacchetti che viaggiano attraverso la rete grazie all'instradamento svolto dai router.\n\nOgni dispositivo è identificato da un indirizzo IP, mentre il sistema dei nomi di dominio traduce i nomi in indirizzi. Il protocollo UDP è più semplice e viene usato dalle applicazioni in tempo reale.\n\nPer proteggere le comunicazioni si utilizza il protocollo TLS, basato sulla crittografia a chiave pubblica e sui certificati digitali.",
};
function example(l) { $('#free-text').value = EXAMPLES[l]; $('#free-lang').value = 'auto'; summarizeText(); }
async function summarizeText() {
  const text = $('#free-text').value.trim();
  if (!text) return;
  const r = await api('/api/text', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, lang: $('#free-lang').value, n_sentences: +$('#free-n').value || 4, method: $('#free-method').value }) });
  const sem = r.method === 'ostis';
  const ls = r.lang_scores && r.lang_scores.fr != null ? ` (доля служебных слов: fr ${pct(r.lang_scores.fr)}, it ${pct(r.lang_scores.it)})` : '';
  $('#free-out').innerHTML = `
  <div class="card"><div class="meta"><span>Метод: <b>${r.method_name}</b></span><span>Язык: <b>${r.lang_name}</b>${ls}</span><span>Область: <b>${sem ? r.kb_domain + ' (по базе знаний)' : r.domain_name}</b></span><span>Предложений: ${r.n_sentences}</span>${sem ? '' : `<span>|DB| = ${r.db_size}</span>`}<span>Время: ${fmt(r.time_ms, 2)} мс</span></div></div>
  <div class="split"><div class="card"><h3>${sem ? 'Семантический реферат' : 'Классический реферат'}</h3><ol class="summary-list">${r.summary.map((t) => `<li>${esc(t)}</li>`).join('')}</ol></div>
  <div class="card"><h3>${sem ? 'Ключевые понятия базы знаний' : 'Ключевые слова'}</h3>${kwTree(r.keywords)}</div></div>
  <div class="card"><h3>Веса предложений</h3><table class="grid"><thead><tr><th class="num">№</th><th>Предложение</th>${sem ? '<th class="num">Понятий</th><th class="num">Σ a(c)</th>' : '<th class="num">Posd</th><th class="num">Posp</th><th class="num">Score</th><th class="num">Weight</th>'}</tr></thead>
  <tbody>${r.sentences.map((x) => `<tr class="${x.in_summary ? 'sel' : ''}"><td class="num">${x.idx + 1}</td><td>${esc(x.text)}</td>${sem ? `<td class="num">${x.concepts}</td><td class="num">${fmt(x.weight, 2)}</td>` : `<td class="num">${fmt(x.posd)}</td><td class="num">${fmt(x.posp)}</td><td class="num">${fmt(x.score, 2)}</td><td class="num">${fmt(x.weight, 2)}</td>`}</tr>`).join('')}</tbody></table></div>`;
}

const VAR_ORDER = ['ostis', 'full', 'score', 'score_posd', 'score_posp', 'lead', 'random'];
const VAR_SHORT = { ostis: 'OSTIS (семантический)', full: 'SE: Score·Posd·Posp', score: 'Score', score_posd: 'Score·Posd', score_posp: 'Score·Posp', lead: 'Lead-N', random: 'Random-N' };
async function loadEval() {
  const e = await api('/api/evaluation');
  const g = Object.values(e.groups);
  if (!e.total.count) { $('#eval-groups').innerHTML = '<div class="muted center">Нет построенных рефератов.</div>'; return; }
  const row = (name, x) => `<tr><td>${name}</td><td class="num">${x.count}</td>${x.full ? `<td class="num">${pct(x.full.f1)}</td><td class="num">${pct(x.ostis.f1)}</td><td class="num">${fmt(x.full.rouge1)}</td><td class="num">${fmt(x.ostis.rouge1)}</td><td class="num">${pct(x.kw_precision)}</td><td class="num">${pct(x.kw_ostis_precision)}</td><td class="num">${pct(x.kw_recall)}</td><td class="num">${pct(x.kw_ostis_recall)}</td>` : '<td colspan="8" class="muted">нет эталона</td>'}<td class="num">${fmt(x.time_ms, 1)} / ${fmt(x.time_ostis, 1)}</td></tr>`;
  $('#eval-groups').innerHTML = `<table class="grid"><thead><tr><th rowspan="2">Группа документов</th><th class="num" rowspan="2">Док.</th><th class="num" colspan="2">F1</th><th class="num" colspan="2">ROUGE-1</th><th class="num" colspan="2">КС: точность</th><th class="num" colspan="2">КС: покрытие</th><th class="num" rowspan="2">Время SE / OSTIS, мс</th></tr>
    <tr><th class="num">SE</th><th class="num">OSTIS</th><th class="num">SE</th><th class="num">OSTIS</th><th class="num">SE</th><th class="num">OSTIS</th><th class="num">SE</th><th class="num">OSTIS</th></tr></thead>
    <tbody>${g.map((x) => row(`${x.lang}, ${x.domain}`, x)).join('')}${row('<b>Все документы</b>', e.total)}</tbody></table>`;
  if (e.total.full) {
    $('#eval-variants').innerHTML = `<table class="grid"><thead><tr><th>Вариант</th><th class="num">P</th><th class="num">R</th><th class="num">F1</th><th class="num">ROUGE-1</th><th class="num">ROUGE-2</th></tr></thead>
      <tbody>${VAR_ORDER.filter((v) => e.total[v]).map((v) => `<tr class="${v === 'full' || v === 'ostis' ? 'sel' : ''}"><td>${e.variants[v]}</td><td class="num">${pct(e.total[v].precision)}</td><td class="num">${pct(e.total[v].recall)}</td><td class="num">${pct(e.total[v].f1)}</td><td class="num">${fmt(e.total[v].rouge1)}</td><td class="num">${fmt(e.total[v].rouge2)}</td></tr>`).join('')}</tbody></table>`;
  }
  $('#eval-docs').innerHTML = `<table class="grid"><thead><tr><th>Документ</th><th>Язык</th><th>Область</th><th class="num">Предл.</th><th class="num">F1 SE</th><th class="num">F1 OSTIS</th><th class="num">F1 Lead-N</th><th class="num">КС SE</th><th class="num">КС OSTIS</th><th class="num">Время SE / OSTIS, мс</th></tr></thead>
    <tbody>${e.documents.map((d) => `<tr><td><a href="/documents/${d.id}/file" target="_blank">${esc(d.filename)}</a></td><td>${LANG[d.lang]}</td><td>${DOMAIN[d.domain]}</td><td class="num">${d.n_sentences}</td>${d.metrics ? `<td class="num">${pct(d.metrics.full.f1)}</td><td class="num">${pct(d.metrics.ostis.f1)}</td><td class="num">${pct(d.metrics.lead.f1)}</td><td class="num">${pct(d.kw_precision)}</td><td class="num">${pct(d.kw_ostis_precision)}</td>` : '<td colspan="5" class="muted">нет эталона</td>'}<td class="num">${fmt(d.time_ms, 1)} / ${fmt(d.time_ostis, 1)}</td></tr>`).join('')}</tbody></table>`;
  const labels = g.map((x) => `${x.lang.slice(0, 4)}., ${x.domain.startsWith('науч') ? 'CS' : 'лит.'}`);
  const shown = ['ostis', 'full', 'score_posp', 'lead', 'random'];
  const colors = ['#3c9a5f', '#2f5aa8', '#9bb7e8', '#e0a03c', '#b8b8b8'];
  draw('chart-f1', { type: 'bar', data: { labels, datasets: shown.filter((v) => g[0] && g[0][v]).map((v, i) => ({ label: VAR_SHORT[v], data: g.map((x) => x[v] ? +(100 * x[v].f1).toFixed(1) : null), backgroundColor: colors[i] })) },
    options: { scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: 'F1, %' } } }, plugins: { legend: { position: 'bottom' } } } });
  draw('chart-time', { type: 'bar', data: { labels: e.documents.map((d) => d.filename.replace('.pdf', '')), datasets: [
      { label: 'sentence extraction', data: e.documents.map((d) => +d.time_ms.toFixed(2)), backgroundColor: '#2f5aa8' },
      { label: 'OSTIS', data: e.documents.map((d) => +d.time_ostis.toFixed(2)), backgroundColor: '#3c9a5f' }] },
    options: { plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true, title: { display: true, text: 'мс' } } } } });
}
function draw(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart(document.getElementById(id), cfg); }

let KB = null;
async function openKb(id) {
  loadKbInfo();
  if (!id) { $('#scg').innerHTML = '<div class="muted center">Нет построенных рефератов.</div>'; $('#scs').textContent = ''; return; }
  const m = $('#kb-method').value;
  const s = await api(`/api/documents/${id}/summary?method=${m}`);
  $('#kb-dl').href = `/api/kb.scs?ids=${id}&method=${m}`;
  $('#scs').textContent = s.scs;
  $('#scg').innerHTML = scgSvg(s.graph);
}
async function loadKbInfo() {
  if (KB) return;
  KB = await api('/api/kb/info');
  const m = KB.memory;
  $('#kb-stats').innerHTML = [
    ['Понятий в базе знаний', KB.concepts, `CS: ${KB.by_domain.cs}, литература: ${KB.by_domain.lit}`],
    ['Идентификаторов', KB.identifiers.fr + KB.identifiers.it, `французских: ${KB.identifiers.fr}, итальянских: ${KB.identifiers.it}`],
    ['Связей онтологии', KB.inclusion + KB.related, `включение: ${KB.inclusion}, ассоциативных: ${KB.related}`],
    ['sc-элементов в памяти', m.total, `узлов ${m.nodes}, ссылок ${m.links}, дуг ${m.access_arcs + m.common_arcs}`],
    ['Загрузка kb/*.scs', fmt(KB.load_ms, 1) + ' мс', Object.entries(KB.files).map(([f, n]) => `${f}: ${n}`).join(', ')],
  ].map(([l, v, s]) => `<div class="card stat"><div class="l">${l}</div><div class="v">${v}</div><div class="l">${s}</div></div>`).join('');
  renderConcepts();
}
function renderConcepts() {
  if (!KB) return;
  const q = ($('#kb-q').value || '').toLowerCase(), dom = $('#kb-dom').value;
  const list = KB.concepts_list.filter((c) => (!dom || c.domain === dom) && (!q || [c.concept, c.ru, ...c.fr, ...c.it].some((x) => x.toLowerCase().includes(q))));
  $('#kb-concepts').innerHTML = `<p class="muted">Показано ${Math.min(list.length, 30)} из ${list.length}</p><table class="grid"><thead><tr><th>Понятие</th><th>Русское имя</th><th>Французские идентификаторы</th><th>Итальянские идентификаторы</th><th>Родитель</th></tr></thead>
    <tbody>${list.slice(0, 30).map((c) => `<tr><td><code>${esc(c.concept)}</code></td><td>${esc(c.ru)}</td><td>${c.fr.map(esc).join('; ')}</td><td>${c.it.map(esc).join('; ')}</td><td><code>${esc(c.parent || '—')}</code></td></tr>`).join('')}</tbody></table>`;
}
function scgSvg(g) {
  const pos = {}, W = 1240;
  const byKind = (k) => g.nodes.filter((n) => n.kind === k);
  const doc = byKind('doc')[0], classes = byKind('class'), structs = byKind('struct');
  const links = byKind('link'), termsN = byKind('term'), subs = byKind('subterm');
  const rows = Math.max(links.length, termsN.length, 3);
  classes.forEach((n, i) => { pos[n.id] = [W / 2 + (i - (classes.length - 1) / 2) * 300, 40]; });
  pos[doc.id] = [W / 2, 130];
  const top = 220, step = 44;
  if (structs[0]) pos[structs[0].id] = [110, top];
  if (structs[1]) pos[structs[1].id] = [700, top];
  links.forEach((n, i) => { pos[n.id] = [450, top + 40 + i * step]; });
  termsN.forEach((n, i) => { pos[n.id] = [830, top + 40 + i * step]; });
  const used = [];
  subs.forEach((n) => {
    const parent = g.edges.find((e) => e.to === n.id && e.kind === 'nrel');
    let y = parent && pos[parent.from] ? pos[parent.from][1] : top;
    while (used.some((v) => Math.abs(v - y) < 20)) y += 20;
    used.push(y); pos[n.id] = [1010, y];
  });
  const H = Math.max(top + 40 + rows * step, ...used.map((v) => v + 30)) + 10;
  const edge = (e) => {
    const a = pos[e.from], b = pos[e.to]; if (!a || !b) return '';
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
    const toLink = g.nodes.find((n) => n.id === e.to)?.kind === 'link';
    if (toLink) { const bx = b[0] - 150, by = b[1]; const ddx = bx - a[0], ddy = by - a[1], LL = Math.hypot(ddx, ddy) || 1;
      return arc(a[0] + ddx / LL * 13, a[1] + ddy / LL * 13, bx, by, e); }
    const r2 = g.nodes.find((n) => n.id === e.to)?.kind === 'subterm' ? 9 : 13;
    return arc(a[0] + dx / L * 13, a[1] + dy / L * 13, b[0] - dx / L * r2, b[1] - dy / L * r2, e);
  };
  const arc = (x1, y1, x2, y2, e) => {
    const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1;
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const lx = e.kind === 'rrel' ? x2 - dx / L * 26 : mx + 4, ly = e.kind === 'rrel' ? y2 - dy / L * 26 - 4 : my - 5;
    const lbl = e.rel ? `<text x="${lx}" y="${ly}" class="rel">${esc(e.rel)}</text>` : '';
    if (e.kind === 'nrel') return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#333" stroke-width="3.5" marker-end="url(#ar)"/><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#fff" stroke-width="1.2"/>${lbl}`;
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#333" stroke-width="1.4" marker-end="url(#ar)"/>${lbl}`;
  };
  const node = (n) => {
    const [x, y] = pos[n.id]; if (x == null) return '';
    if (n.kind === 'link') return `<rect x="${x - 150}" y="${y - 14}" width="300" height="28" rx="3" fill="#f3f3f3" stroke="#333"/><text x="${x}" y="${y + 4}" text-anchor="middle" class="lt">${esc(n.label)}</text>`;
    const fill = { doc: '#ffe8a3', class: '#cfe0ff', struct: '#e3d4ff', term: '#d4f0dc', subterm: '#eef8f0' }[n.kind];
    const r = n.kind === 'subterm' ? 8 : 12;
    let inner = '';
    if (n.kind === 'class') inner = `<line x1="${x - 8}" y1="${y - 8}" x2="${x + 8}" y2="${y + 8}" stroke="#333"/><line x1="${x - 8}" y1="${y + 8}" x2="${x + 8}" y2="${y - 8}" stroke="#333"/>`;
    if (n.kind === 'struct') inner = `<circle cx="${x}" cy="${y}" r="3" fill="#333"/>`;
    const anchor = n.kind === 'subterm' ? 'start' : 'middle', tx = n.kind === 'subterm' ? x + 12 : x, ty = n.kind === 'subterm' ? y + 4 : y - 18;
    const label = n.kind === 'doc' ? esc(n.label.length > 70 ? n.label.slice(0, 70) + '…' : n.label) : esc(n.label);
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="#333" stroke-width="2"/>${inner}<text x="${n.kind === 'term' ? x + 17 : tx}" y="${n.kind === 'term' ? y + 4 : ty}" text-anchor="${n.kind === 'term' ? 'start' : anchor}" class="nt">${label}</text>`;
  };
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:900px" xmlns="http://www.w3.org/2000/svg">
    <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker>
    <style>.nt{font:12px "Segoe UI",Arial;fill:#1d2433;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}.lt{font:11px "Segoe UI",Arial;fill:#1d2433}.rel{font:11px "Segoe UI",Arial;fill:#7a2e8e;paint-order:stroke;stroke:#fff;stroke-width:3px}</style></defs>
    ${g.edges.map(edge).join('')}${g.nodes.map(node).join('')}</svg>`;
}

refresh().then(() => { const t = location.hash.slice(1); if (t && document.getElementById('tab-' + t)) showTab(t); });
