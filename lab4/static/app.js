const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (x, d = 1) => (x == null ? '—' : Number(x).toLocaleString('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }));
let current = null, treeKind = 'dep', dictOffset = 0, dictTimer = null;
const POS_RU = { NOUN: 'существительное', PROPN: 'имя собственное', VERB: 'глагол', AUX: 'вспом. глагол', ADJ: 'прилагательное',
  ADV: 'наречие', ADP: 'предлог', DET: 'определитель', PRON: 'местоимение', NUM: 'числительное', CCONJ: 'сочин. союз',
  SCONJ: 'подчин. союз', PART: 'частица', INTJ: 'междометие', X: 'другое', SYM: 'символ' };
const STATUS_RU = { dict: 'словарь', phrase: 'оборот', grammar: 'грамматика', rule: 'правило', proper: 'без перевода', unknown: 'нет в словаре', punct: 'знак' };
const GENDER = { m: 'м. р.', f: 'ж. р.' };

async function api(url, opt = {}) {
  const r = await fetch(url, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) {  }
    throw new Error(msg);
  }
  return r.json();
}
function toast(msg, bad) {
  let el = $('#toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  el.textContent = msg;
  el.style.cssText = `position:fixed;right:18px;bottom:18px;background:${bad ? '#b42318' : '#1f3b73'};color:#fff;padding:10px 14px;border-radius:6px;z-index:20;max-width:420px;box-shadow:0 2px 8px #0003`;
  clearTimeout(el._t); el._t = setTimeout(() => el.remove(), bad ? 6000 : 3000);
}

function showTab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + name));
  if (name === 'dict') { loadDictStats(); loadUnknown(); loadDict(); loadPhrases(); }
  if (name === 'history') loadHistory();
}
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
function help(id) { showTab('help'); const el = document.getElementById(id); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1500); }

async function loadSample() {
  const v = $('#sample').value; if (!v) return;
  const [part, name] = v.split('/');
  const r = await api(`/api/sample/${part}/${name}`);
  $('#src').value = r.text; $('#title').value = r.title;
}
async function uploadFile(input) {
  const f = input.files[0]; if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  try { const r = await api('/api/upload', { method: 'POST', body: fd }); $('#src').value = r.text; $('#title').value = r.title; toast(`Файл «${f.name}» загружен`); }
  catch (e) { toast(e.message, true); }
  input.value = '';
}
const drop = $('#drop');
['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => { if (e.dataTransfer.files.length) uploadFile({ files: e.dataTransfer.files, set value(v) { } }); });

async function doTranslate() {
  const text = $('#src').value.trim();
  if (!text) { toast('Введите текст на английском языке', true); return; }
  const btn = event && event.target; if (btn) btn.disabled = true;
  try {
    const r = await api('/api/translate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, title: $('#title').value, mode: $('#mode').value, domain: $('#domain').value }) });
    setResult(r);
    toast(`Переведено: ${r.stats.words} слов за ${fmt(r.time_ms.total, 0)} мс`);
  } catch (e) { toast(e.message, true); } finally { if (btn) btn.disabled = false; }
}

function setResult(r) {
  current = r;
  $('#out-actions').hidden = false;
  $('#out').innerHTML = r.paragraphs.map(p => p.heading
    ? `<h4>${p.sentences.map(s => s.html).join(' ')}</h4>`
    : `<p>${p.sentences.map(s => s.html).join(' ')}</p>`).join('');
  const st = r.stats;
  $('#stats').hidden = false;
  $('#stats').innerHTML = [
    [st.words, 'слов во входном тексте'], [st.translated, 'переведено слов'], [st.unknown, 'нет в словаре'],
    [st.proper, 'имена собственные и числа'], [fmt(st.coverage) + '%', 'покрытие словарём'], [st.unique, 'разных лемм'],
    [r.domain_name || '—', 'предметная область'], [fmt(r.time_ms.total, 0) + ' мс', `время (анализ ${fmt(r.time_ms.analysis, 0)} мс)`],
  ].map(([v, l]) => `<div class="card stat"><div class="v" style="font-size:${String(v).length > 12 ? 15 : 24}px">${esc(v)}</div><div class="l">${l}</div></div>`).join('');
  $('#sent-card').hidden = false;
  $('#sent-table').innerHTML = '<tr><th class="num">№</th><th>Исходное предложение</th><th>Перевод</th><th>Нет в словаре</th></tr>' +
    r.sentences.map((s, i) => `<tr class="sent" onclick="openTree(${i})"><td class="num">${i + 1}</td><td>${esc(s.en)}</td><td>${s.html}</td>
      <td class="small">${s.unknown.map(esc).join(', ')}</td></tr>`).join('');
  const pos = [...new Set(r.freq.map(f => f.pos))].sort();
  $('#freq-pos').innerHTML = '<option value="">Все части речи</option>' + pos.map(p => `<option value="${p}">${POS_RU[p] || p}</option>`).join('');
  renderFreq();
  $('#tree-sent').innerHTML = r.sentences.map((s, i) => `<option value="${i}">${i + 1}. ${esc(s.en.slice(0, 90))}</option>`).join('');
  renderTree();
}

function gramInfo(tr, pos) {
  if (!tr) return '';
  const p = [];
  if (tr.gender) p.push(GENDER[tr.gender]);
  if (tr.plural && tr.plural !== tr.fr) p.push('мн. ч. ' + tr.plural);
  if (tr.forms && pos === 'ADJ') p.push('формы: ' + [...new Set(tr.forms)].join(', '));
  if (tr.forms && (pos === 'VERB' || pos === 'AUX')) p.push('наст. вр.: ' + tr.forms.join(', ') + '; прич. ' + (tr.pp || ''));
  return p.join('; ');
}
function renderFreq() {
  if (!current) return;
  const q = $('#freq-q').value.trim().toLowerCase(), pos = $('#freq-pos').value, onlyUnk = $('#freq-unk').checked;
  const rows = current.freq.filter(f => (!q || f.lemma.includes(q) || f.forms.some(x => x.includes(q)))
    && (!pos || f.pos === pos) && (!onlyUnk || !f.translation));
  $('#freq-meta').innerHTML = `<span>Документ: <b>${esc(current.title)}</b></span><span>Всего лемм: ${current.freq.length}</span>
    <span>Показано: ${rows.length}</span><span>Слов в тексте: ${current.stats.words}</span>`;
  $('#freq-table').innerHTML = `<tr><th class="num">№</th><th>Слово (лемма)</th><th>Формы в тексте</th><th class="num">Частота</th>
    <th>Часть речи и теги</th><th>Роль в предложении</th><th>Морфология</th><th>Перевод</th><th>Грамматика (фр.)</th></tr>` +
    rows.map((f, i) => {
      const tr = f.translation;
      return `<tr><td class="num">${i + 1}</td><td><b>${esc(f.lemma)}</b></td><td class="small">${f.forms.map(esc).join(', ')}</td>
        <td class="num">${f.frequency}</td><td class="small"><b>${esc(f.pos_ru)}</b><br>${f.tags_ru.map(esc).join('<br>')}</td>
        <td class="small">${f.roles.map(esc).join(', ')}</td><td class="small">${f.morph.map(esc).join('<br>')}</td>
        <td>${tr ? `<b>${esc(tr.fr)}</b> <span class="pill ${tr.source === 'оборот' ? 'phrase' : tr.source === 'правило' ? 'rule' : 'dict'}">${esc(tr.source)}</span>`
          : (f.pos === 'PROPN' || f.pos === 'NUM' ? '<span class="pill proper">без перевода</span>' : '<span class="pill unknown">нет в словаре</span>')}</td>
        <td class="small">${esc(gramInfo(tr, f.pos))}</td></tr>`;
    }).join('');
}

function saveTxt(part) {
  if (!current || !current.id) { toast('Сначала переведите текст', true); return; }
  window.location = `/api/translations/${current.id}/report.txt?part=${part}&enc=${$('#enc').value}`;
}

function openTree(i) { $('#tree-sent').value = i; renderTree(); showTab('tree'); }
function setTreeKind(k) { treeKind = k; document.querySelectorAll('#tree-kind button').forEach(b => b.classList.toggle('on', b.dataset.k === k)); renderTree(); }

function layoutTree(root, opts) {
  const nodes = [], edges = [];
  let cursor = 0;
  const measure = n => Math.max(opts.minW, 7.2 * Math.max((n.label || '').length, (n.fr || '').length * 0.9, (n.tagText || '').length * 0.8) + 18);
  (function place(n, depth, parent) {
    n.w = measure(n); n.depth = depth;
    const kids = n.children || [];
    if (!kids.length) { n.x = cursor + n.w / 2; cursor += n.w + opts.gap; }
    else {
      kids.forEach(c => place(c, depth + 1, n));
      n.x = (kids[0].x + kids[kids.length - 1].x) / 2;
      const left = n.x - n.w / 2;
      if (nodes.length && left < 0) {  }
    }
    nodes.push(n);
    kids.forEach(c => edges.push([n, c]));
  })(root, 0, null);
  return { nodes, edges, width: cursor + 20, depth: Math.max(...nodes.map(n => n.depth)) };
}

function renderTree() {
  if (!current) return;
  const s = current.sentences[+$('#tree-sent').value || 0];
  if (!s) return;
  const dep = treeKind === 'dep';
  const tree = JSON.parse(JSON.stringify(dep ? s.dep_tree : s.const_tree));
  if (dep) (function mark(n) { n.tagText = n.tag; (n.children || []).forEach(mark); })(tree);
  const L = layoutTree(tree, { minW: dep ? 70 : 34, gap: dep ? 12 : 8 });
  const rowH = dep ? 92 : 58, boxH = dep ? 54 : 24, pad = 16;
  const W = Math.max(L.width + pad * 2, 600), H = (L.depth + 1) * rowH + pad * 2;
  const Y = n => pad + n.depth * rowH;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  L.edges.forEach(([a, b]) => {
    const x1 = pad + a.x, y1 = Y(a) + boxH, x2 = pad + b.x, y2 = Y(b);
    svg += `<path d="M${x1} ${y1} C${x1} ${(y1 + y2) / 2} ${x2} ${(y1 + y2) / 2} ${x2} ${y2}" fill="none" stroke="#98a2b3" stroke-width="1.2"/>`;
    if (dep && b.sub) svg += `<text x="${(x1 + x2) / 2 + (x2 >= x1 ? 4 : -4)}" y="${(y1 + y2) / 2 + 4}" font-size="11" fill="#b42318" text-anchor="${x2 >= x1 ? 'start' : 'end'}">${esc(b.sub)}</text>`;
  });
  L.nodes.forEach(n => {
    const x = pad + n.x, y = Y(n);
    if (dep) {
      const st = (s.tokens.find(t => t.i === n.i) || {}).status;
      const fill = st === 'unknown' ? '#ffe2a8' : n.depth === 0 ? '#dfe9ff' : '#f6f8fb';
      svg += `<g><title>${esc(n.title)}</title><rect x="${x - n.w / 2}" y="${y}" width="${n.w}" height="${boxH}" rx="6" fill="${fill}" stroke="#667085"/>
        <text x="${x}" y="${y + 17}" text-anchor="middle" font-size="13" font-weight="600" fill="#1d2433">${esc(n.label)}</text>
        <text x="${x}" y="${y + 31}" text-anchor="middle" font-size="10.5" fill="#667085">${esc(n.tag)}</text>
        <text x="${x}" y="${y + 46}" text-anchor="middle" font-size="11.5" fill="#1f6b3a">${esc(n.fr || '')}</text></g>`;
    } else if (n.leaf) {
      svg += `<text x="${x}" y="${y + 16}" text-anchor="middle" font-size="13" font-weight="600" fill="#1d2433">${esc(n.label)}</text>`;
    } else {
      const phrase = (n.children || []).some(c => !c.leaf);
      svg += `<g><title>${esc(n.title || n.label)}</title><rect x="${x - n.w / 2}" y="${y}" width="${n.w}" height="${boxH}" rx="5"
        fill="${phrase ? '#e3ecff' : '#f6f8fb'}" stroke="${phrase ? '#2f5aa8' : '#98a2b3'}"/>
        <text x="${x}" y="${y + 16}" text-anchor="middle" font-size="12" font-weight="${phrase ? 700 : 400}" fill="${phrase ? '#1f3b73' : '#475467'}">${esc(n.label)}</text></g>`;
    }
  });
  svg += '</svg>';
  $('#tree-svg').innerHTML = svg;
  $('#tree-meta').innerHTML = `<span>${esc(s.en)}</span>`;
  $('#tree-legend').innerHTML = dep
    ? 'Узел: слово, тег Penn Treebank и французский перевод; подпись дуги — синтаксическое отношение (nsubj — подлежащее, dobj — прямое дополнение, amod — определение, prep — предлог, pobj — дополнение предлога…). Жёлтым — слово, которого нет в словаре.'
    : 'S — предложение, NP — именная группа, VP — глагольная группа, PP — предложная группа, ADJP / ADVP — группы прилагательного / наречия; нижний уровень — теги слов.';
  $('#tree-bracket').textContent = s.bracket;
  $('#tree-fr').innerHTML = s.html;
  $('#tree-tokens').innerHTML = '<tr><th class="num">№</th><th>Слово</th><th>Лемма</th><th>Тег</th><th>Роль (связь)</th><th>Перевод</th><th>Источник</th></tr>' +
    s.tokens.filter(t => t.status !== 'punct').map(t => `<tr><td class="num">${t.i}</td><td><b>${esc(t.text)}</b></td><td>${esc(t.lemma)}</td>
      <td title="${esc(t.tag_ru)}">${esc(t.tag)} <span class="muted">${esc(t.tag_ru)}</span></td><td>${esc(t.role)} <span class="muted">(${esc(t.dep)} → ${esc(t.head_text)})</span></td>
      <td class="tok-fr">${esc(t.fr)}</td><td><span class="pill ${t.status}">${STATUS_RU[t.status] || t.status}</span></td></tr>`).join('');
}

async function loadDictStats() {
  const s = await api('/api/dict/stats');
  $('#dict-stats').innerHTML = [[s.total, 'записей в словаре'], [s.phrases, 'оборотов'],
    [s.by_source.seed || 0, 'исходных'], [(s.by_source.user || 0) + (s.by_source.auto || 0), 'добавлено пользователем'],
    [s.by_domain.cs || 0, 'термины computer science'], [s.by_domain.lit || 0, 'термины литературы']]
    .map(([v, l]) => `<div class="card stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  if ($('#dict-pos').options.length < 3)
    $('#dict-pos').innerHTML = '<option value="">Все части речи</option>' + s.by_pos.map(p => `<option value="${p.pos}">${POS_RU[p.pos] || p.pos} (${p.n})</option>`).join('');
}
function debounceDict() { clearTimeout(dictTimer); dictTimer = setTimeout(() => loadDict(), 250); }
async function loadDict(more) {
  dictOffset = more ? dictOffset + 100 : 0;
  const q = encodeURIComponent($('#dict-q').value.trim());
  const r = await api(`/api/dict?q=${q}&pos=${$('#dict-pos').value}&source=${$('#dict-src').value}&limit=100&offset=${dictOffset}`);
  const rows = r.items.map(e => `<tr><td><b>${esc(e.en)}</b></td><td>${POS_RU[e.pos] || e.pos}</td><td>${esc(e.fr)}</td><td>${GENDER[e.gender] || ''}</td>
    <td class="mono">${esc(e.extra)}</td><td>${e.domain === 'cs' ? 'CS' : e.domain === 'lit' ? 'лит.' : ''}</td>
    <td><span class="pill ${e.source}">${{ seed: 'исходный', user: 'пользователь', auto: 'авто' }[e.source]}</span></td>
    <td class="no-print" style="white-space:nowrap"><button class="btn sm" onclick='editEntry(${JSON.stringify(e).replace(/'/g, '&#39;')})'>Изменить</button>
      <button class="btn sm danger" onclick="delEntry(${e.id})">×</button></td></tr>`).join('');
  const head = '<tr><th>Английский</th><th>Часть речи</th><th>Французский</th><th>Род</th><th>Доп. формы и флаги</th><th>Область</th><th>Источник</th><th></th></tr>';
  if (more) $('#dict-table').insertAdjacentHTML('beforeend', rows); else $('#dict-table').innerHTML = head + rows;
  $('#dict-meta').innerHTML = `<span>Найдено: ${r.total}</span>`;
  $('#dict-more').hidden = dictOffset + 100 >= r.total;
}
function entryForm(e) {
  e = e || { en: '', pos: 'NOUN', fr: '', gender: 'm', extra: '', domain: null };
  return `<h2>${e.id ? 'Изменить запись' : 'Новая запись'}</h2>
  <div class="row"><label>Английская лемма<input type="text" id="f-en" value="${esc(e.en)}"></label>
    <label>Часть речи<select id="f-pos">${Object.entries(POS_RU).filter(([k]) => !['AUX', 'INTJ', 'X', 'SYM'].includes(k)).map(([k, v]) => `<option value="${k}" ${k === e.pos ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
    <label>Перевод<input type="text" id="f-fr" value="${esc(e.fr)}"></label>
    <label>Род<select id="f-g"><option value="">—</option><option value="m" ${e.gender === 'm' ? 'selected' : ''}>м. р.</option><option value="f" ${e.gender === 'f' ? 'selected' : ''}>ж. р.</option></select></label></div>
  <div class="row"><label style="flex:1">Доп. формы и флаги<input type="text" id="f-extra" value="${esc(e.extra)}" style="width:100%" placeholder="pl=…; f=…; pre; aux=être; obj=à; inf=de"></label>
    <label>Область<select id="f-dom"><option value="">общая</option><option value="cs" ${e.domain === 'cs' ? 'selected' : ''}>computer science</option><option value="lit" ${e.domain === 'lit' ? 'selected' : ''}>литература</option></select></label></div>
  <div class="row"><button class="btn primary" onclick="saveEntry(${e.id || 0})">Сохранить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`;
}
function editEntry(e) { $('#modal-box').innerHTML = entryForm(e); $('#modal').classList.add('open'); }
function closeModal() { $('#modal').classList.remove('open'); }
$('#modal').onclick = e => { if (e.target.id === 'modal') closeModal(); };
async function saveEntry(id) {
  const body = { en: $('#f-en').value, pos: $('#f-pos').value, fr: $('#f-fr').value, gender: $('#f-g').value || null,
    extra: $('#f-extra').value, domain: $('#f-dom').value || null, source: 'user' };
  try {
    await api(id ? `/api/dict/${id}` : '/api/dict', { method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    closeModal(); toast('Словарь обновлён'); loadDict(); loadDictStats(); loadUnknown();
  } catch (err) { toast(err.message, true); }
}
async function delEntry(id) {
  if (!confirm('Удалить запись из словаря?')) return;
  await api(`/api/dict/${id}`, { method: 'DELETE' }); loadDict(); loadDictStats();
}
async function importDict(input) {
  const f = input.files[0]; if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  try { const r = await api('/api/dict/import', { method: 'POST', body: fd }); toast(`Добавлено записей: ${r.added} из ${r.rows} (пропущено ${r.skipped})`); loadDict(); loadDictStats(); }
  catch (e) { toast(e.message, true); }
  input.value = '';
}
let unknownRows = [];
async function loadUnknown() {
  unknownRows = await api('/api/unknown');
  if (!unknownRows.length) { $('#unk-table').innerHTML = '<tr><td class="muted center">Неизвестных слов нет — переведите текст, и сюда попадут слова, которых нет в словаре.</td></tr>'; return; }
  $('#unk-table').innerHTML = `<tr><th><input type="checkbox" onchange="document.querySelectorAll('.unk-ck').forEach(c => c.checked = this.checked)"></th>
    <th>Слово</th><th>Лемма</th><th>Часть речи</th><th class="num">Встреч</th><th>Перевод</th><th>Род</th><th>Доп.</th><th>Гипотеза</th><th>Пример</th></tr>` +
    unknownRows.map((u, i) => {
      const s = u.suggestion || {};
      return `<tr><td><input type="checkbox" class="unk-ck" data-i="${i}" ${s.confidence === 'высокая' ? 'checked' : ''}></td>
        <td><b>${esc(u.word)}</b></td><td><input type="text" id="u-en-${i}" value="${esc(u.lemma)}"></td>
        <td><select id="u-pos-${i}">${['NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN', 'ADP'].map(p => `<option value="${p}" ${p === u.pos ? 'selected' : ''}>${POS_RU[p]}</option>`).join('')}</select></td>
        <td class="num">${u.freq}</td><td><input type="text" id="u-fr-${i}" value="${esc(s.fr || '')}" placeholder="перевод"></td>
        <td><select id="u-g-${i}"><option value="">—</option><option value="m" ${s.gender === 'm' ? 'selected' : ''}>м.</option><option value="f" ${s.gender === 'f' ? 'selected' : ''}>ж.</option></select></td>
        <td><input type="text" id="u-x-${i}" value="${esc(s.extra || '')}" style="width:70px"></td>
        <td class="sugg">${s.rule ? esc(s.rule) + `<br><span class="muted">достоверность: ${esc(s.confidence)}</span>` : '<span class="muted">нет гипотезы</span>'}</td>
        <td class="small muted">${esc(u.example)}</td></tr>`;
    }).join('');
}
async function acceptAll() {
  const items = [...document.querySelectorAll('.unk-ck:checked')].map(c => {
    const i = +c.dataset.i, u = unknownRows[i];
    const fr = $(`#u-fr-${i}`).value.trim();
    const edited = fr !== ((u.suggestion || {}).fr || '');
    return { en: $(`#u-en-${i}`).value, pos: $(`#u-pos-${i}`).value, fr, gender: $(`#u-g-${i}`).value || null,
      extra: $(`#u-x-${i}`).value, domain: null, source: edited ? 'user' : 'auto' };
  }).filter(x => x.fr);
  if (!items.length) { toast('Отметьте строки с переводом', true); return; }
  try { const r = await api('/api/dict/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) });
    toast(`Добавлено в словарь: ${r.added}`); loadUnknown(); loadDict(); loadDictStats(); }
  catch (e) { toast(e.message, true); }
}
async function clearUnknown() { if (!confirm('Очистить список неизвестных слов?')) return; await api('/api/unknown', { method: 'DELETE' }); loadUnknown(); }
async function loadPhrases() {
  const r = await api('/api/phrases?q=' + encodeURIComponent($('#ph-q').value.trim()));
  const KIND = { NOUN: 'именной', VERB: 'глагольный', ADJ: 'прилагательное', FIX: 'неизменяемый', PROPN: 'имя собств.' };
  $('#ph-table').innerHTML = '<tr><th>Английский (леммы)</th><th>Французский</th><th>Тип</th><th>Доп.</th><th></th></tr>' +
    r.map(p => `<tr><td><b>${esc(p.en)}</b></td><td>${esc(p.fr)}</td><td>${KIND[p.kind] || p.kind}</td><td class="mono">${esc(p.extra)}</td>
      <td class="no-print"><button class="btn sm danger" onclick="delPhrase(${p.id})">×</button></td></tr>`).join('');
}
function addPhrase() {
  $('#modal-box').innerHTML = `<h2>Новый оборот</h2><p class="muted small">Английская часть — леммы через пробел (например, «take into account»).
    Тип «именной» — оборот ведёт себя как существительное (укажите род m/f в поле «доп.»), «глагольный» — как глагол (спрягается первое слово перевода),
    «неизменяемый» — переводится как есть.</p>
    <div class="row"><label>Английский<input type="text" id="p-en"></label><label>Французский<input type="text" id="p-fr"></label>
    <label>Тип<select id="p-kind"><option value="FIX">неизменяемый</option><option value="NOUN">именной</option><option value="VERB">глагольный</option></select></label>
    <label>Доп.<input type="text" id="p-extra" placeholder="m; pl=…"></label></div>
    <div class="row"><button class="btn primary" onclick="savePhrase()">Сохранить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`;
  $('#modal').classList.add('open');
}
async function savePhrase() {
  try { await api('/api/phrases', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ en: $('#p-en').value, fr: $('#p-fr').value, kind: $('#p-kind').value, extra: $('#p-extra').value }) });
    closeModal(); toast('Оборот добавлен'); loadPhrases(); loadDictStats(); }
  catch (e) { toast(e.message, true); }
}
async function delPhrase(id) { if (!confirm('Удалить оборот?')) return; await api(`/api/phrases/${id}`, { method: 'DELETE' }); loadPhrases(); }

async function loadHistory() {
  const r = await api('/api/translations');
  $('#hist-table').innerHTML = '<tr><th class="num">№</th><th>Дата</th><th>Документ</th><th>Метод</th><th class="num">Слов</th><th class="num">Переведено</th><th class="num">Нет в словаре</th><th class="num">Покрытие</th><th></th></tr>' +
    (r.length ? r.map(t => `<tr><td class="num">${t.id}</td><td>${t.created_at}</td><td><a href="#" class="link" onclick="openHistory(${t.id});return false">${esc(t.title)}</a></td>
      <td>${t.mode === 'transfer' ? 'трансфер' : 'пословный'}</td><td class="num">${t.n_words}</td><td class="num">${t.n_translated}</td>
      <td class="num">${t.n_unknown}</td><td class="num">${fmt(t.coverage)}%</td>
      <td class="no-print" style="white-space:nowrap"><a class="btn sm" href="/api/translations/${t.id}/report.txt">TXT</a>
      <button class="btn sm danger" onclick="delHistory(${t.id})">×</button></td></tr>`).join('') : '<tr><td colspan="9" class="muted center">Переводов пока нет.</td></tr>');
}
async function openHistory(id) {
  const r = await api(`/api/translations/${id}`);
  $('#src').value = r.source_text; $('#title').value = r.title; $('#mode').value = r.mode;
  setResult(r); showTab('translate');
}
async function delHistory(id) { if (!confirm('Удалить перевод?')) return; await api(`/api/translations/${id}`, { method: 'DELETE' }); loadHistory(); }

async function runEval() {
  const part = $('#eval-part').value;
  $('#eval-table').innerHTML = '<tr><td class="muted center">Перевод и подсчёт…</td></tr>';
  const r = await api('/api/evaluate?part=' + part);
  const s = r.summary;
  $('#eval-cards').innerHTML = [
    [fmt(s.transfer.bleu), 'BLEU, система с трансфером'], [fmt(s.direct.bleu), 'BLEU, пословный перевод'],
    [fmt(s.transfer.chrf), 'chrF, система с трансфером'], [fmt(s.direct.chrf), 'chrF, пословный перевод'],
    [fmt(s.transfer.coverage) + '%', 'покрытие словарём'], [s.transfer.words, 'слов в выборке']]
    .map(([v, l]) => `<div class="card stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  $('#eval-table').innerHTML = `<tr><th>Текст</th><th>Область</th><th class="num">Слов</th><th class="num">Нет в словаре</th>
    <th class="num">BLEU трансфер</th><th class="num">BLEU пословный</th><th class="num">chrF трансфер</th><th class="num">chrF пословный</th><th class="num">Время, мс</th></tr>` +
    r.docs.map(d => `<tr><td>${esc(d.title)}</td><td>${d.domain === 'cs' ? 'CS' : 'литература'}${d.detected_domain && d.detected_domain !== d.domain ? ' <span class="pill unknown">опр. ' + d.detected_domain + '</span>' : ''}</td>
      <td class="num">${d.transfer.words}</td><td class="num">${d.transfer.unknown}</td><td class="num"><b>${fmt(d.transfer.bleu)}</b></td>
      <td class="num">${fmt(d.direct.bleu)}</td><td class="num">${fmt(d.transfer.chrf)}</td><td class="num">${fmt(d.direct.chrf)}</td>
      <td class="num">${fmt(d.transfer.time, 0)}</td></tr>`).join('');
}
