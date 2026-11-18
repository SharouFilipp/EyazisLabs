document.querySelectorAll('.tab').forEach(btn => {
    btn.onclick = () => {
        document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.tab).classList.add('active');
        if (btn.dataset.tab === 'eval') loadAllDocsForEval();
    };
});

async function api(url, method='GET', body=null) {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    return r.json();
}

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
}

function highlightText(text, lemmas) {
    let safe = escapeHtml(text);
    if (!lemmas || !lemmas.length) return safe;

    const terms = [...new Set(lemmas.filter(t => t && t.length >= 3))];
    if (!terms.length) return safe;

    const escaped = terms
        .map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .sort((a, b) => b.length - a.length)
        .join('|');

    const re = new RegExp(`(${escaped})[а-яё]*`, 'gi');
    return safe.replace(re, '<span class="hl">$&</span>');
}

let categoryClasses = [];

function categorySelect(d) {
    const options = categoryClasses.map(c =>
        `<option value="${c}" ${d.category_manual && c === d.category ? 'selected' : ''}>${c}</option>`
    ).join('');
    const autoLabel = d.category_manual ? 'авто' : `${d.category} (авто)`;
    return `
        <select class="category-select ${d.category_manual ? 'manual' : ''}"
                data-cat="${d.id}"
                title="${d.category_manual ? 'Тема указана вручную — документ используется для обучения'
                                            : 'Тема определена классификатором. Выберите другую, чтобы исправить'}">
            <option value="" ${d.category_manual ? '' : 'selected'}>${autoLabel}</option>
            ${options}
        </select>
        ${d.category_manual ? '<span class="manual-mark" title="Размечено вручную">✎</span>' : ''}`;
}

async function refreshDocs() {
    if (!categoryClasses.length) categoryClasses = await api('/api/classifier/classes');
    const docs = await api('/api/documents');
    const tbody = document.querySelector('#docs-table tbody');
    tbody.innerHTML = '';
    docs.forEach(d => {
        let link;
        if (d.source_type === 'url' && d.source_url) {
            link = `<a href="${d.source_url}" target="_blank">${d.source_url}</a>`;
        } else {
            link = `<a href="/api/documents/download/${encodeURIComponent(d.filename)}">
                    ${d.filename}</a>`;
        }
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${d.id}</td>
            <td>${d.title}</td>
            <td>${categorySelect(d)}</td>
            <td>${link}</td>
            <td>${d.date}</td>
            <td>${d.size}</td>
            <td>
                <button class="small ghost" data-view="${d.id}">Просмотр</button>
                <button class="small danger" data-fn="${d.filename}">Удалить</button>
            </td>`;
        tbody.appendChild(tr);
    });
    tbody.querySelectorAll('button[data-fn]').forEach(btn => {
        btn.onclick = async () => {
            if (!confirm('Удалить этот документ?')) return;
            await api('/api/documents/delete', 'POST', { filename: btn.dataset.fn });
            refreshDocs();
        };
    });
    tbody.querySelectorAll('button[data-view]').forEach(btn => {
        btn.onclick = () => openViewer(parseInt(btn.dataset.view));
    });
    tbody.querySelectorAll('select[data-cat]').forEach(sel => {
        sel.onchange = async () => {
            const status = document.getElementById('docs-status');
            status.textContent = 'Переобучение классификатора...';
            sel.disabled = true;
            const res = await api(`/api/documents/${sel.dataset.cat}/category`, 'POST',
                                  { category: sel.value || null });
            await refreshDocs();
            status.textContent = res.ok
                ? `Классификатор переобучен: ${res.total_examples} примеров ` +
                  `(из них размечено вами: ${res.user_examples}). Темы остальных документов пересчитаны.`
                : (res.detail || 'Ошибка');
        };
    });
    document.getElementById('docs-status').textContent =
        docs.length ? `Всего документов: ${docs.length}`
                    : 'База пуста — загрузите документы на вкладке «Загрузка».';
}

document.getElementById('btn-load-urls').onclick = async () => {
    const urls = document.getElementById('urls').value
        .split('\n').map(s => s.trim()).filter(Boolean);
    if (!urls.length) { alert('Введите хотя бы один URL'); return; }
    document.getElementById('load-status').textContent = 'Загрузка страниц...';
    const res = await api('/api/documents/load_urls', 'POST', { urls });
    if (res.ok) {
        const parts = [];
        if (res.added.length)   parts.push(`добавлено: ${res.added.length}`);
        if (res.updated.length) parts.push(`обновлено: ${res.updated.length}`);
        if (res.errors.length)  parts.push(`ошибок: ${res.errors.length}`);
        document.getElementById('load-status').textContent =
            parts.join(', ') + `. Всего в базе: ${res.total}`;
    } else {
        document.getElementById('load-status').textContent = res.detail || 'Ошибка';
    }
    refreshDocs();
};

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
document.getElementById('browse').onclick = e => { e.preventDefault(); fileInput.click(); };
dropzone.onclick = () => fileInput.click();
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    uploadFiles(e.dataTransfer.files);
});
fileInput.onchange = () => uploadFiles(fileInput.files);

async function uploadFiles(list) {
    if (!list.length) return;
    const fd = new FormData();
    for (const f of list) fd.append('files', f);
    document.getElementById('load-status').textContent = 'Загрузка файлов...';
    const r = await fetch('/api/documents/upload', { method: 'POST', body: fd });
    const res = await r.json();
    if (res.ok) {
        const parts = [];
        if (res.added.length)   parts.push(`добавлено: ${res.added.length}`);
        if (res.updated.length) parts.push(`обновлено: ${res.updated.length}`);
        if (res.errors.length)  parts.push(`ошибок: ${res.errors.length}`);
        document.getElementById('load-status').textContent =
            parts.join(', ') + `. Всего в базе: ${res.total}`;
    } else {
        document.getElementById('load-status').textContent = res.detail || 'Ошибка';
    }
    refreshDocs();
}

document.getElementById('btn-refresh').onclick = refreshDocs;
document.getElementById('btn-clear').onclick = async () => {
    if (!confirm('Удалить все документы и очистить индекс?')) return;
    await api('/api/documents/clear', 'POST');
    refreshDocs();
};

function renderResults(container, results, withCb=false) {
    container.innerHTML = '';
    if (!results.length) {
        container.innerHTML = '<p class="hint">Ничего не найдено. Попробуйте переформулировать запрос.</p>';
        return;
    }
    results.forEach(r => {
        let link;
        if (r.source_type === 'url' && r.source_url) {
            link = `<a href="${r.source_url}" target="_blank">${r.source_url}</a>`;
        } else {
            link = `<a href="/api/documents/download/${encodeURIComponent(r.filename)}">${r.filename}</a>`;
        }
        const cb = withCb
            ? `<label style="display:inline-flex;align-items:center;gap:6px;
                            font-size:12px;margin-top:6px">
                 <input type="checkbox" value="${r.document_id}" class="rel-cb">
                 релевантен
               </label>`
            : '';

        const titleHtml   = highlightText(r.title,   r.matched_terms);
        const snippetHtml = highlightText(r.snippet, r.matched_terms);

        const div = document.createElement('div');
        div.className = 'result';
        div.innerHTML = `
            <span class="rank">ранг ${r.rank.toFixed(4)}</span>
            <h3>${titleHtml}</h3>
            <div class="meta"><span class="category-tag">${r.category}</span> ${link} · ${r.date}</div>
            <div class="snippet">${snippetHtml}</div>
            <div class="terms">Совпавшие слова: ${r.matched_terms.join(', ') || '—'}</div>
            <div style="margin-top:10px">
                <button class="small ghost" data-view="${r.document_id}">Открыть текст</button>
            </div>
            ${cb}`;
        container.appendChild(div);
    });
    container.querySelectorAll('button[data-view]').forEach(btn => {
        btn.onclick = () => {
            const id = parseInt(btn.dataset.view);
            const r = results.find(x => x.document_id === id);
            openViewer(id, r ? r.matched_terms : []);
        };
    });
}

document.getElementById('btn-search').onclick = async () => {
    const query = document.getElementById('query').value.trim();
    const top_k = parseInt(document.getElementById('topk').value) || 10;
    const category = document.getElementById('filter-category').value || null;
    if (!query) { alert('Введите запрос'); return; }
    document.getElementById('search-status').textContent = 'Поиск...';
    const res = await api('/api/search', 'POST', { query, top_k, category });
    if (res.ok) {
        document.getElementById('search-status').textContent =
            res.results.length
                ? `Найдено документов: ${res.results.length}`
                : 'Ничего не найдено';
        renderResults(document.getElementById('results'), res.results);
    } else {
        document.getElementById('search-status').textContent = res.detail || 'Ошибка';
    }
};

document.getElementById('query').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('btn-search').click();
});

let evalRetrieved = [];
let evalRelevant = new Set();
let chart = null;

async function loadAllDocsForEval() {
    const docs = await api('/api/documents');
    const box = document.getElementById('all-docs-list');
    box.innerHTML = '';
    if (!docs.length) {
        box.innerHTML = '<p class="hint" style="padding:12px">В базе нет документов.</p>';
        return;
    }
    docs.forEach(d => {
        const label = document.createElement('label');
        label.innerHTML = `
            <input type="checkbox" value="${d.id}" class="rel-doc-cb">
            <span class="doc-id">#${d.id}</span>
            <span class="doc-title">${d.title || d.filename}</span>
            <span class="doc-size">${d.size} симв.</span>
        `;
        box.appendChild(label);
    });
    box.querySelectorAll('.rel-doc-cb').forEach(cb => {
        cb.onchange = () => {
            const id = parseInt(cb.value);
            if (cb.checked) evalRelevant.add(id);
            else evalRelevant.delete(id);
        };
    });
}

document.getElementById('btn-eval-search').onclick = async () => {
    const query = document.getElementById('eval-query').value.trim();
    if (!query) { alert('Введите запрос'); return; }
    const res = await api('/api/search', 'POST', { query, top_k: 10 });
    if (!res.ok) return;
    evalRetrieved = res.results.map(r => r.document_id);
    renderResults(document.getElementById('eval-results'), res.results, false);
};

document.getElementById('btn-eval-calc').onclick = async () => {
    if (!evalRetrieved.length) { alert('Сначала выполните поиск'); return; }
    if (!evalRelevant.size)    { alert('Отметьте хотя бы один релевантный документ'); return; }
    const res = await api('/api/evaluate', 'POST', {
        retrieved: evalRetrieved,
        relevant: Array.from(evalRelevant),
    });
    if (!res.ok) return;
    const m = res.metrics;
    document.querySelector('#metrics-table tbody').innerHTML =
        `<tr><td>${m.precision}</td><td>${m.recall}</td>
             <td>${m.f1}</td><td>${m.ap}</td></tr>`;

    const ctx = document.getElementById('metrics-chart');
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Precision', 'Recall', 'F1', 'AP'],
            datasets: [{
                label: 'Значение',
                data: [m.precision, m.recall, m.f1, m.ap],
                backgroundColor: ['#2f4a8c', '#5c74b8', '#3aa76d', '#c98a3d'],
                borderRadius: 6,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 1, ticks: { stepSize: 0.2 } }
            }
        }
    });
};

document.getElementById('btn-eval-reset').onclick = () => {
    evalRetrieved = [];
    evalRelevant = new Set();
    document.querySelectorAll('.rel-doc-cb').forEach(cb => cb.checked = false);
    document.getElementById('eval-results').innerHTML = '';
    document.querySelector('#metrics-table tbody').innerHTML =
        '<tr><td>—</td><td>—</td><td>—</td><td>—</td></tr>';
    if (chart) { chart.destroy(); chart = null; }
};

async function openViewer(docId, highlightTerms = []) {
    const res = await api(`/api/document/${docId}/text`);
    if (!res || res.detail) { alert('Не удалось открыть документ'); return; }

    document.getElementById('viewer-title').textContent = res.title || res.filename;

    const src = (res.source_type === 'url' && res.source_url)
        ? `<a href="${res.source_url}" target="_blank">${res.source_url}</a>`
        : `Файл: ${res.filename}`;
    document.getElementById('viewer-source').innerHTML = src;
    document.getElementById('viewer-date').textContent = `Добавлен: ${res.date}`;
    document.getElementById('viewer-size').textContent = `${res.size} символов`;
    document.getElementById('viewer-category').textContent = `Тема: ${res.category}`;

    document.getElementById('viewer-text').innerHTML =
        highlightText(res.text, highlightTerms);

    document.getElementById('viewer').style.display = 'flex';
}

function closeViewer() {
    document.getElementById('viewer').style.display = 'none';
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeViewer();
});
document.addEventListener('click', e => {
    if (e.target && e.target.id === 'viewer') closeViewer();
});

async function loadCategories() {
    const select = document.getElementById('filter-category');
    const classes = await api('/api/classifier/classes');
    for (const c of classes) {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        select.appendChild(opt);
    }
}

loadCategories();
refreshDocs();
loadAllDocsForEval();