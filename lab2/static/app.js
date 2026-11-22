const LANGS = { en: 'Английский', fr: 'Французский' };
const METHODS = { frequent: 'Частотных слов', short: 'Коротких слов', neural: 'Нейросетевой' };
const COLORS = { frequent: '#2f4a8c', short: '#d9822b', neural: '#3a9a6a' };
const charts = {};
Chart.defaults.animation = false;

function $(id) { return document.getElementById(id); }

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function api(url, options = {}) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Ошибка ${res.status}`);
    return data;
}

function jsonPost(url, body, method = 'POST') {
    return api(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

function setStatus(id, text, isError = false) {
    const el = $(id);
    el.textContent = text;
    el.style.color = isError ? '#c0504a' : '';
}

function langBadge(code) {
    return code ? `<span class="lang ${code}">${LANGS[code]}</span>` : '<span class="lang none">—</span>';
}

function selectedMethods() {
    return [...document.querySelectorAll('.method-cb:checked')].map(cb => cb.value);
}

function pct(x) { return x == null ? '—' : (x * 100).toFixed(1) + '%'; }

function drawChart(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id), config);
}

function openTab(name, anchor) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === name));
    if (name === 'stats') loadStats();
    if (name === 'profiles') loadProfiles();
    if (anchor) setTimeout(() => $(anchor).scrollIntoView({ behavior: 'smooth' }), 50);
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => openTab(t.dataset.tab)));

let documents = [];

function renderDocs() {
    const methods = Object.keys(METHODS);
    if (!documents.length) {
        $('docs-table').innerHTML = '<p class="hint">Документов пока нет. Загрузите PDF-файлы или тестовую коллекцию.</p>';
        $('summary-cards').innerHTML = '';
        return;
    }
    const rows = documents.map(d => {
        const cells = methods.map(m => {
            const r = d.results[m];
            if (!r) return '<td>—</td>';
            const wrong = d.true_lang && r.lang !== d.true_lang;
            return `<td class="${wrong ? 'wrong' : ''}">${langBadge(r.lang)}
                <span class="sub">уверенность ${r.confidence.toFixed(2)} · ${r.time_ms.toFixed(2)} мс</span></td>`;
        }).join('');
        return `<tr>
            <td>${d.id}</td>
            <td><a href="${d.url}" target="_blank" title="Открыть PDF">${esc(d.filename)}</a>
                <span class="sub">${d.pages} стр. · ${d.chars} симв. · ${d.words} слов</span></td>
            <td><select onchange="setLabel(${d.id}, this.value)">
                <option value="" ${!d.true_lang ? 'selected' : ''}>неизвестен</option>
                <option value="en" ${d.true_lang === 'en' ? 'selected' : ''}>Английский</option>
                <option value="fr" ${d.true_lang === 'fr' ? 'selected' : ''}>Французский</option>
            </select></td>
            ${cells}
            <td class="no-print">
                <button class="small ghost" onclick="viewDoc(${d.id})">Текст</button>
                <button class="small danger" onclick="deleteDoc(${d.id})">Удалить</button>
            </td>
        </tr>`;
    }).join('');
    $('docs-table').innerHTML = `<table>
        <tr><th>id</th><th>Документ</th><th>Эталон</th>
            ${methods.map(m => `<th>${METHODS[m]}</th>`).join('')}<th class="no-print"></th></tr>
        ${rows}</table>`;
}

function renderSummaryCards(summary) {
    const cards = Object.entries(summary.methods).filter(([, s]) => s.processed).map(([m, s]) => `
        <div class="stat-card">
            <h4>${METHODS[m]}</h4>
            <div class="big">${pct(s.accuracy)}</div>
            <div class="small-text">точность (${s.correct} из ${s.labeled} с эталоном)</div>
            <div class="small-text">Англ.: ${s.by_lang.en || 0} · Франц.: ${s.by_lang.fr || 0}</div>
            <div class="small-text">Среднее время: ${s.avg_ms} мс на документ</div>
        </div>`).join('');
    $('summary-cards').innerHTML = cards;
}

async function loadDocs() {
    documents = await api('/api/documents');
    renderDocs();
    const stats = await api('/api/stats');
    renderSummaryCards(stats.summary);
}

async function uploadFiles(files) {
    const pdfs = [...files];
    if (!pdfs.length) return;
    const form = new FormData();
    pdfs.forEach(f => form.append('files', f));
    form.append('true_lang', $('upload-lang').value);
    setStatus('detect-status', `Загрузка ${pdfs.length} файл(ов)...`);
    try {
        const r = await api('/api/documents/upload', { method: 'POST', body: form });
        const errs = r.errors.map(e => `${e.file}: ${e.error}`).join('; ');
        setStatus('detect-status', `Добавлено: ${r.added.length}. Ошибок: ${r.errors.length}${errs ? ' — ' + errs : ''}`, r.errors.length > 0);
        await loadDocs();
    } catch (e) { setStatus('detect-status', e.message, true); }
}

const dz = $('dropzone');
$('pick-files').addEventListener('click', e => { e.preventDefault(); $('file-input').click(); });
$('file-input').addEventListener('change', e => { uploadFiles(e.target.files); e.target.value = ''; });
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('dragover'); uploadFiles(e.dataTransfer.files); });

$('btn-import').addEventListener('click', async () => {
    setStatus('detect-status', 'Загрузка тестовой коллекции...');
    try {
        const r = await api('/api/documents/import-test', { method: 'POST' });
        setStatus('detect-status', `Тестовая коллекция загружена: ${r.added.length} документов.`);
        await loadDocs();
    } catch (e) { setStatus('detect-status', e.message, true); }
});

$('btn-detect').addEventListener('click', async () => {
    const methods = selectedMethods();
    if (!methods.length) return setStatus('detect-status', 'Выберите хотя бы один метод.', true);
    setStatus('detect-status', 'Распознавание...');
    const t0 = performance.now();
    try {
        const r = await jsonPost('/api/detect', { methods });
        documents = r.documents;
        renderDocs();
        renderSummaryCards(r.summary);
        setStatus('detect-status', `Обработано документов: ${r.processed} за ${((performance.now() - t0) / 1000).toFixed(2)} с.`);
    } catch (e) { setStatus('detect-status', e.message, true); }
});

$('btn-refresh').addEventListener('click', loadDocs);

$('btn-clear').addEventListener('click', async () => {
    if (!confirm('Удалить все документы и результаты распознавания?')) return;
    await api('/api/documents', { method: 'DELETE' });
    setStatus('detect-status', 'База очищена.');
    await loadDocs();
});

async function setLabel(id, lang) {
    await jsonPost(`/api/documents/${id}/label`, { true_lang: lang || null }, 'PUT');
    await loadDocs();
}

async function deleteDoc(id) {
    if (!confirm('Удалить документ?')) return;
    await api(`/api/documents/${id}`, { method: 'DELETE' });
    await loadDocs();
}

async function viewDoc(id) {
    const d = await api(`/api/documents/${id}/text`);
    $('viewer-title').textContent = d.title;
    $('viewer-meta').innerHTML = `<a href="/documents/${id}/file" target="_blank">${esc(d.filename)}</a>`;
    $('viewer-text').textContent = d.text;
    $('viewer').style.display = 'flex';
}
function closeViewer() { $('viewer').style.display = 'none'; }
$('viewer').addEventListener('click', e => { if (e.target.id === 'viewer') closeViewer(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeViewer(); });

function saveReport(fmt) { window.location.href = `/api/report?fmt=${fmt}`; }
function printReport() { window.print(); }

const SAMPLES = {
    en: 'The weather was so pleasant that we decided to walk along the river and have lunch in a small cafe near the old bridge.',
    fr: "Le temps était si agréable que nous avons décidé de nous promener le long de la rivière et de déjeuner dans un petit café près du vieux pont.",
    mix: 'Paris est magnifique',
};
function sampleText(k) { $('free-text').value = SAMPLES[k]; }

$('btn-text').addEventListener('click', async () => {
    const text = $('free-text').value;
    setStatus('text-status', 'Распознавание...');
    try {
        const r = await jsonPost('/api/detect/text', { text, methods: selectedMethods() });
        setStatus('text-status', `Слов после предобработки: ${r.words}`);
        $('text-result').innerHTML = Object.entries(r.results).map(([m, x]) => `
            <div class="stat-card">
                <h4>${METHODS[m]}</h4>
                <div>${langBadge(x.lang)}</div>
                <div class="small-text" style="margin-top:8px">d(en) = ${x.scores.en.toFixed(4)}<br>d(fr) = ${x.scores.fr.toFixed(4)}</div>
                <div class="small-text">уверенность ${x.confidence.toFixed(3)}</div>
                <div class="bar"><span style="width:${(x.confidence * 100).toFixed(0)}%"></span></div>
                <div class="small-text">время ${x.time_ms.toFixed(3)} мс</div>
                ${m === 'short' && r.short_votes ? `<div class="small-text">голоса предложений: англ. ${r.short_votes.en}, франц. ${r.short_votes.fr}</div>` : ''}
            </div>`).join('');
    } catch (e) { setStatus('text-status', e.message, true); }
});

async function loadStats() {
    const { summary } = await api('/api/stats');
    const ms = Object.entries(summary.methods);
    if (!summary.documents) {
        $('stats-body').innerHTML = '<p class="hint">Нет документов.</p>';
        return;
    }
    const confusion = ms.filter(([, s]) => s.labeled).map(([m, s]) => `
        <div class="stat-card"><h4>${METHODS[m]} — матрица ошибок</h4>
        <table><tr><th>эталон \\ ответ</th><th>Англ.</th><th>Франц.</th></tr>
        ${Object.keys(LANGS).map(t => `<tr><td>${LANGS[t]}</td><td>${s.confusion[t].en}</td><td>${s.confusion[t].fr}</td></tr>`).join('')}
        </table></div>`).join('');
    $('stats-body').innerHTML = `
        <p>Документов в коллекции: <b>${summary.documents}</b>.
           Все методы дали одинаковый ответ для <b>${summary.agreement}</b> из ${summary.compared} документов.</p>
        <table>
            <tr><th>Метод</th><th>Обработано</th><th>Английский</th><th>Французский</th><th>Точность</th>
                <th>Среднее время, мс</th><th>Суммарное время, мс</th></tr>
            ${ms.map(([m, s]) => `<tr><td>${METHODS[m]}</td><td>${s.processed}</td><td>${s.by_lang.en || 0}</td>
                <td>${s.by_lang.fr || 0}</td><td>${pct(s.accuracy)}</td><td>${s.avg_ms ?? '—'}</td><td>${s.total_ms}</td></tr>`).join('')}
        </table>
        <div class="stat-cards">${confusion}</div>`;
    drawChart('stats-chart', {
        type: 'bar',
        data: {
            labels: ms.map(([m]) => METHODS[m]),
            datasets: [
                { label: 'Английский', data: ms.map(([, s]) => s.by_lang.en || 0), backgroundColor: '#6f8fd6' },
                { label: 'Французский', data: ms.map(([, s]) => s.by_lang.fr || 0), backgroundColor: '#e6a26b' },
            ],
        },
        options: { plugins: { title: { display: true, text: 'Распределение документов по распознанным языкам' } } },
    });
}

$('btn-bench').addEventListener('click', async () => {
    const methods = selectedMethods();
    setStatus('bench-status', 'Выполняется сравнение (может занять несколько секунд)...');
    try {
        const r = await jsonPost('/api/benchmark', { methods, per_doc: +$('per-doc').value || 10 });
        setStatus('bench-status', `Документов с эталоном: ${r.documents}.`);
        const label = k => k === 'full' ? 'весь документ' : `${k} сл.`;
        const ms = Object.keys(r.table);
        $('bench-table').innerHTML = `<table>
            <tr><th>Длина фрагмента</th><th>Фрагментов</th>
                ${ms.map(m => `<th>${METHODS[m]}<br><small>точность / время, мс</small></th>`).join('')}</tr>
            ${r.lengths.map(k => `<tr><td>${label(k)}</td><td>${r.table[ms[0]][k].samples}</td>
                ${ms.map(m => `<td>${pct(r.table[m][k].accuracy)} / ${r.table[m][k].avg_ms}</td>`).join('')}</tr>`).join('')}
        </table>`;
        drawChart('bench-chart', {
            type: 'line',
            data: {
                labels: r.lengths.map(label),
                datasets: ms.map(m => ({ label: METHODS[m], data: r.lengths.map(k => r.table[m][k].accuracy * 100),
                    borderColor: COLORS[m], backgroundColor: COLORS[m], tension: .2 })),
            },
            options: { plugins: { title: { display: true, text: 'Точность распознавания, % (по длине фрагмента)' } },
                scales: { y: { suggestedMin: 50, max: 100 } } },
        });
        drawChart('bench-time', {
            type: 'bar',
            data: {
                labels: r.lengths.map(label),
                datasets: ms.map(m => ({ label: METHODS[m], data: r.lengths.map(k => r.table[m][k].avg_ms),
                    backgroundColor: COLORS[m] })),
            },
            options: { plugins: { title: { display: true, text: 'Среднее время распознавания одного фрагмента, мс (логарифмическая шкала)' } },
                scales: { y: { type: 'logarithmic' } } },
        });
    } catch (e) { setStatus('bench-status', e.message, true); }
});

function profileTable(rows) {
    return `<table><tr><th>#</th><th>Слово</th><th>Вероятность</th></tr>
        ${rows.map(([w, p], i) => `<tr><td>${i + 1}</td><td>${esc(w)}</td><td>${p.toFixed(5)}</td></tr>`).join('')}</table>`;
}

async function loadProfiles() {
    const p = await api('/api/profiles');
    const ti = p.train_info;
    const corpus = Object.entries(ti.corpus).map(([l, c]) =>
        `${LANGS[l]}: ${(c.bytes / 1024).toFixed(1)} КБ, ${c.words} слов`).join('; ');
    const nn = ti.neural;
    $('profiles-body').innerHTML = `
        <p class="hint">Обучающий набор — ${corpus}. Профили построены ${ti.trained_at}.
            Время построения: частотные слова ${ti.train_ms.frequent} мс, короткие слова ${ti.train_ms.short} мс,
            нейросеть ${ti.train_ms.neural} мс.</p>
        <h3>Метод частотных слов (top-${p.params.frequent_top_n}, показаны первые 40)</h3>
        <div class="profile-cols">
            ${Object.keys(LANGS).map(l => `<div><b>${LANGS[l]}</b> (${p.frequent_size[l]} слов)${profileTable(p.frequent[l])}</div>`).join('')}
        </div>
        <h3>Метод коротких слов (длина ≤ ${p.params.short_max_len}, частота > ${p.params.short_min_count})</h3>
        <div class="profile-cols">
            ${Object.keys(LANGS).map(l => `<div><b>${LANGS[l]}</b> (${p.short_size[l]} лексем)${profileTable(p.short[l])}</div>`).join('')}
        </div>
        <h3>Нейросетевой метод</h3>
        <p>Многослойный перцептрон: вход — ${nn.features} признаков (TF-IDF символьных N-грамм, N = 1…3),
            скрытый слой — ${nn.hidden} нейронов (ReLU), выход — вероятности языков.
            Обучающих фрагментов: ${nn.samples}, эпох: ${nn.epochs}, точность на валидационной выборке: ${pct(nn.val_accuracy)}.</p>
        ${Object.keys(LANGS).map(l => `<div><b>N-граммы, наиболее характерные для языка «${LANGS[l]}»:</b>
            <div class="chips">${p.neural_ngrams[l].map(g => `<span>${esc(g)}</span>`).join('')}</div></div>`).join('')}`;
}

$('btn-train').addEventListener('click', async () => {
    setStatus('profiles-status', 'Построение профилей...');
    try {
        await api('/api/train', { method: 'POST' });
        setStatus('profiles-status', 'Профили построены заново.');
        await loadProfiles();
    } catch (e) { setStatus('profiles-status', e.message, true); }
});

loadDocs();
