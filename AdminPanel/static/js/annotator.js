/* Аннотатор изображений: запуск задачи, опрос статуса, показ результата,
 * перенос итогов в стандартную форму «Признаки» (openEditFeatures из biological_edit.html).
 * Зависит от глобальных FEATURE_CATALOG и openEditFeatures на странице объекта. */
(function () {
    const POLL_MS = 2000;
    const MAX_POLL_ERRORS = 3;
    const EXEC_SHORT = { clip: 'CLIP', grounding_dino: 'DINO', owlv2: 'OWLv2', phenovision: 'PhenoVision', gigachat: 'GigaChat' };

    const st = { resourceId: null, title: '', current: {}, config: null, selected: new Set(),
                 executors: new Set(), timer: null, pollErrors: 0, result: null, taskId: null };
    const $ = (id) => document.getElementById(id);
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const modalEl = () => $('annotatorModal');

    // ---------- каталог признаков БД (что реально можно сохранить) ----------
    function dbCatalog() {
        const list = (typeof FEATURE_CATALOG !== 'undefined' && FEATURE_CATALOG.image) || [];
        const map = {};
        list.forEach((f) => { map[f.name.trim().toLowerCase()] = f; });
        return map;
    }

    function showError(msg) {
        const box = $('annError');
        box.textContent = msg;
        box.classList.toggle('d-none', !msg);
    }

    function stage(name) {
        $('annSetup').classList.toggle('d-none', name !== 'setup');
        $('annProgress').classList.toggle('d-none', name !== 'progress');
        $('annSummary').classList.toggle('d-none', name !== 'result');
        $('annResult').classList.toggle('d-none', name !== 'result');
        $('annFooter').classList.toggle('d-none', name !== 'result');
    }

    function stopPolling() {
        if (st.timer) { clearTimeout(st.timer); st.timer = null; }
    }

    // ---------- шаг 1: форма ----------
    async function loadConfig() {
        const lifeform = modalEl().dataset.lifeform || '';
        const url = '/admin/annotator/config' + (lifeform ? '?lifeform=' + encodeURIComponent(lifeform) : '');
        const resp = await fetch(url);
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || 'не удалось получить настройки аннотатора');
        return data;
    }

    function renderSetup() {
        const cat = dbCatalog();
        const hasCatalog = Object.keys(cat).length > 0;
        const feats = st.config.features;
        if (st.selected.size === 0) {
            feats.forEach((f) => { if (!hasCatalog || cat[f.name.toLowerCase()]) st.selected.add(f.name); });
        }
        $('annFeatures').innerHTML = feats.map((f) => {
            const on = st.selected.has(f.name);
            const nocat = hasCatalog && !cat[f.name.toLowerCase()];
            return `<label class="ann-chip ${on ? 'on' : ''}" title="${esc(f.values.join(', '))}">
                <input type="checkbox" data-feat="${esc(f.name)}" ${on ? 'checked' : ''}>${esc(f.name)}
                ${nocat ? '<span class="ann-nocat" title="Нет в каталоге «Признаки ресурсов» — сохранить не получится">нет в каталоге</span>' : ''}
            </label>`;
        }).join('') || '<span class="text-muted small">Сервис не вернул признаков</span>';
        $('annFeatures').querySelectorAll('input[data-feat]').forEach((cb) => {
            cb.addEventListener('change', () => {
                cb.checked ? st.selected.add(cb.dataset.feat) : st.selected.delete(cb.dataset.feat);
                cb.parentElement.classList.toggle('on', cb.checked);
                updateCounters();
            });
        });

        const execs = st.config.executors;
        if (st.executors.size === 0) execs.filter((e) => e.loaded).forEach((e) => st.executors.add(e.id));
        $('annExecutors').innerHTML = execs.map((e) => {
            const on = e.loaded && st.executors.has(e.id);
            const sub = e.loaded ? `${esc(e.kind || '')} · вес ${esc(e.weight)}` : `не загружена: ${esc(e.error || '')}`;
            return `<div class="col-md-6"><label class="ann-exec ${on ? 'on' : ''} ${e.loaded ? '' : 'disabled'}">
                <span><span class="fw-bold d-block">${esc(e.title || e.id)}</span><span class="ann-muted">${sub}</span></span>
                <input class="form-check-input m-0" type="checkbox" data-exec="${esc(e.id)}" ${on ? 'checked' : ''} ${e.loaded ? '' : 'disabled'}>
            </label></div>`;
        }).join('');
        $('annExecutors').querySelectorAll('input[data-exec]').forEach((cb) => {
            cb.addEventListener('change', () => {
                cb.checked ? st.executors.add(cb.dataset.exec) : st.executors.delete(cb.dataset.exec);
                cb.closest('.ann-exec').classList.toggle('on', cb.checked);
                updateCounters();
            });
        });
        updateCounters();
    }

    function updateCounters() {
        $('annSelCount').textContent = `${st.selected.size} из ${st.config.features.length}`;
        $('annToggleAll').textContent = st.selected.size === st.config.features.length ? 'Снять все' : 'Выбрать все';
        $('annRunBtn').disabled = st.selected.size === 0 || st.executors.size === 0;
    }

    // ---------- шаг 2: запуск и опрос ----------
    async function run() {
        showError('');
        $('annRunBtn').disabled = true;
        try {
            const resp = await fetch(`/admin/annotator/start/${st.resourceId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    features: [...st.selected],
                    executors: [...st.executors],
                    lifeform: modalEl().dataset.lifeform || null,
                }),
            });
            const data = await resp.json();
            if (!data.ok) throw new Error(data.error);
            st.taskId = data.task.task_id;
            stage('progress');
            renderProgress(data.task);
            st.pollErrors = 0;
            poll(data.task.task_id);
        } catch (e) {
            showError('Не удалось запустить: ' + e.message);
            $('annRunBtn').disabled = false;
        }
    }

    function renderProgress(task) {
        const colors = { pending: 'text-bg-secondary', running: 'text-bg-primary', completed: 'text-bg-success', failed: 'text-bg-danger' };
        $('annStatus').className = 'badge ' + (colors[task.status] || 'text-bg-secondary');
        $('annStatus').textContent = task.status;
        $('annQueue').textContent = task.queue_position ? `в очереди: ${task.queue_position}` : '';
        $('annPct').textContent = `${task.progress || 0}%`;
        $('annBar').style.width = `${task.progress || 0}%`;
    }

    function poll(taskId) {
        st.timer = setTimeout(async () => {
            try {
                const data = await (await fetch(`/admin/annotator/tasks/${taskId}`)).json();
                if (!data.ok) throw new Error(data.error);
                st.pollErrors = 0;
                const task = data.task;
                renderProgress(task);
                if (task.status === 'completed') { st.result = task.result; renderResult(); return; }
                if (task.status === 'failed') { st.taskId = null; showError('Задача завершилась с ошибкой: ' + (task.error || '')); stage('setup'); updateCounters(); return; }
                poll(taskId);
            } catch (e) {
                if (++st.pollErrors >= MAX_POLL_ERRORS) { st.taskId = null; showError('Потеряна связь с аннотатором: ' + e.message); stage('setup'); updateCounters(); return; }
                poll(taskId);
            }
        }, POLL_MS);
    }

    // ---------- шаг 3: результат ----------
    function renderResult() {
        const r = st.result;
        const execs = r.executors;
        const pct = (x) => Math.round((x || 0) * 100);
        const thr = pct(r.threshold);
        const names = Object.keys(r.features);
        const determined = names.filter((n) => r.features[n].verdict);

        $('annSummary').innerHTML = `<span class="badge text-bg-success mb-2">completed</span>
            <div class="fs-5 fw-bold">Определено ${determined.length} из ${names.length} признаков</div>
            <div class="small text-secondary">Моделей: ${execs.length} · порог уверенности ${thr}% ·
            время ${esc(Object.values(r.timing_sec || {}).reduce((a, b) => a + b, 0).toFixed(1))} с</div>`;

        $('annResultTable').querySelector('thead').innerHTML = `<tr>
            <th>Признак</th><th>Итог</th><th>Уверенность</th><th>Согласие</th>
            ${execs.map((e) => `<th>${esc(EXEC_SHORT[e] || e)}</th>`).join('')}</tr>`;

        $('annResultTable').querySelector('tbody').innerHTML = names.map((name) => {
            const f = r.features[name];
            const by = {};
            f.by_executor.forEach((a) => { by[a.executor] = a; });
            const ok = !!f.verdict;
            const cells = execs.map((e) => {
                const a = by[e];
                if (!a) return '<td class="ann-muted">—</td>';
                if (a.error) return `<td class="ann-muted" title="${esc(a.error)}">ошибка</td>`;
                if (!a.value) return `<td class="ann-muted" title="${esc(a.note || '')}">воздержалась</td>`;
                const conf = a.confidence == null ? 'без вероятности' : a.confidence.toFixed(2);
                return `<td><span class="fw-semibold ${a.value === f.top_value ? '' : 'ann-diff'}">${esc(a.value)}</span>
                        <div class="ann-muted">${conf}</div></td>`;
            }).join('');
            return `<tr>
                <td class="fw-bold">${esc(name)}</td>
                <td><span class="ann-verdict ${ok ? 'ok' : 'none'}">${esc(ok ? f.verdict : 'Не определено')}</span></td>
                <td><div class="d-flex align-items-center gap-2"><div class="ann-bar flex-grow-1">
                    <span style="width:${pct(f.confidence)}%; background:${ok ? 'var(--accent)' : '#94a3b8'}"></span></div>
                    <b>${pct(f.confidence)}%</b></div></td>
                <td class="text-secondary fw-semibold">${esc(f.agreement)}</td>${cells}</tr>`;
        }).join('');

        $('annCaption').innerHTML = r.caption
            ? `<span class="ann-label">Подпись · BLIP</span><div>${esc(r.caption)}</div>` : '';
        const skipped = Object.entries(r.skipped_features || {});
        $('annSkipped').innerHTML = skipped.length
            ? 'Пропущены: ' + skipped.map(([n, why]) => `${esc(n)} (${esc(why)})`).join('; ') : '';
        $('annApplyBtn').disabled = determined.length === 0;
        stage('result');
    }

    // Переносим итоги в стандартную форму «Признаки» — пользователь проверяет и сохраняет сам
    function applyToFeatures() {
        const cat = dbCatalog();
        const merged = { ...st.current };
        const manual = [];   // признак есть в каталоге, но такого значения нет — выбрать вручную
        const missing = [];  // признака нет в каталоге вообще
        Object.entries(st.result.features_for_db || {}).forEach(([name, value]) => {
            const c = cat[name.toLowerCase()];
            if (!c) { missing.push(name); return; }
            // тот же регистр ключа, что уже у ресурса, иначе «Время года» (как ищет бот)
            const existing = Object.keys(merged).find((k) => k.toLowerCase() === c.name.toLowerCase());
            const key = existing || (c.name.charAt(0).toUpperCase() + c.name.slice(1).toLowerCase());
            if (c.values && c.values.length && !c.values.includes(value)) { manual.push({ key, value }); return; }
            merged[key] = value;
        });
        const m = bootstrap.Modal.getInstance(modalEl());
        modalEl().addEventListener('hidden.bs.modal', () => {
            openEditFeatures(st.resourceId, 'image', st.title, merged);
            showHints(manual, missing);
        }, { once: true });
        m.hide();
    }

    // Плашка над формой «Признаки»: что заполнено автоматически и что выбрать вручную
    function showHints(manual, missing) {
        const body = document.getElementById('editResFeatBody');
        if (!body) return;
        const lines = [];
        manual.forEach(({ key, value }) => {
            lines.push(`<b>${esc(key)}</b>: нейросеть ответила «${esc(value)}» — выберите подходящее значение вручную`);
            const field = [...body.querySelectorAll('[data-feat-name]')].find((el) => el.dataset.featName === key);
            if (field) field.classList.add('border-warning', 'border-2');
        });
        if (missing.length) lines.push(`Нет в каталоге признаков: ${missing.map(esc).join(', ')}`);
        const note = document.createElement('div');
        note.className = 'alert ' + (lines.length ? 'alert-warning' : 'alert-info') + ' py-2 small';
        note.innerHTML = '<i class="bi bi-magic"></i> Признаки заполнены аннотатором. Проверьте и нажмите «Сохранить».'
            + (lines.length ? '<br>' + lines.join('<br>') : '');
        body.prepend(note);
    }

    // ---------- вход ----------
    window.openAnnotator = async function (btn) {
        // Та же картинка, задача ещё идёт или уже готова — просто показываем окно в текущем состоянии
        if (st.taskId && st.resourceId === btn.dataset.resourceId) {
            bootstrap.Modal.getOrCreateInstance(modalEl()).show();
            return;
        }
        stopPolling();
        st.taskId = null;
        st.resourceId = btn.dataset.resourceId;
        st.title = btn.dataset.title || 'изображение';
        try { st.current = JSON.parse(btn.dataset.features || '{}') || {}; } catch (e) { st.current = {}; }
        st.selected = new Set(); st.executors = new Set(); st.result = null;
        $('annTitle').textContent = st.title;
        $('annImage').src = btn.dataset.url || '';
        showError(''); stage('setup');
        $('annFeatures').innerHTML = '<span class="text-muted small">Загрузка…</span>';
        $('annExecutors').innerHTML = '';
        bootstrap.Modal.getOrCreateInstance(modalEl()).show();
        try {
            st.config = await loadConfig();
            renderSetup();
        } catch (e) {
            showError(e.message);
            $('annRunBtn').disabled = true;
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        if (!modalEl()) return;
        $('annRunBtn').addEventListener('click', run);
        $('annApplyBtn').addEventListener('click', applyToFeatures);
        $('annAgainBtn').addEventListener('click', () => { st.result = null; st.taskId = null; stage('setup'); updateCounters(); });
        $('annToggleAll').addEventListener('click', () => {
            const all = st.selected.size === st.config.features.length;
            st.selected = new Set(all ? [] : st.config.features.map((f) => f.name));
            renderSetup();
        });
    });
})();
