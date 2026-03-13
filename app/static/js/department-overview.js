// 部門比較ダッシュボード - 月次比較（事実ベース）
// ※ dashboard.js と同一ページで読み込まれるため、グローバル名に dept プレフィックスを付与
let deptCatChart = null;
let deptStaffChart = null;
let deptTrendChart = null;
let currentDept = null;
let currentData = null;

// ============================================
// 初期化（dashboard.js から呼ばれる）
// ============================================
function initDepartmentOverview() {
    // 月セレクターを埋める（データ取得はしない）
    populateMonthSelectorsFromAPI();

    // 詳細セクション内のタブ切り替え時にチャートをリサイズ
    document.querySelectorAll('#detailSection [data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function() {
            if (deptCatChart) deptCatChart.resize();
            if (deptStaffChart) deptStaffChart.resize();
            if (deptTrendChart) deptTrendChart.resize();
        });
    });
}

async function populateMonthSelectorsFromAPI() {
    try {
        const response = await fetch('/api/analytics/department-month-comparison');
        const data = await response.json();
        populateMonthSelectors(data.available_months, data.base_month, data.compare_month);
    } catch (e) {
        console.error('Failed to populate month selectors:', e);
    }
}

// ============================================
// 月フォーマット
// ============================================
function formatMonth(ym) {
    if (!ym) return '';
    const parts = ym.split('-');
    if (parts.length !== 2) return ym;
    return `${parts[0]}年${parseInt(parts[1])}月`;
}

// ============================================
// 差分表示ヘルパー
// ============================================
function getDiffClass(val) {
    if (val > 0) return 'diff-positive';
    if (val < 0) return 'diff-negative';
    return 'diff-zero';
}

function getArrow(val) {
    if (val > 0) return '▲';
    if (val < 0) return '▼';
    return '→';
}

function formatDiff(val, suffix) {
    if (val === 0) return `<span class="diff-zero">→ 0${suffix}</span>`;
    const cls = getDiffClass(val);
    const arrow = getArrow(val);
    const sign = val > 0 ? '+' : '';
    return `<span class="${cls}">${arrow} ${sign}${val.toFixed(1)}${suffix}</span>`;
}

function formatPct(pct) {
    if (pct === null || pct === undefined) return '<span class="text-muted">新規</span>';
    if (pct === 0) return '<span class="diff-zero">0%</span>';
    const cls = getDiffClass(pct);
    const sign = pct > 0 ? '+' : '';
    return `<span class="${cls}">${sign}${pct}%</span>`;
}

function formatCost(val) {
    if (val === undefined || val === null) return '¥0';
    return '¥' + Math.round(val).toLocaleString();
}

function formatCostDiff(val) {
    if (val === 0) return `<span class="diff-zero">→ ¥0</span>`;
    const cls = getDiffClass(val);
    const arrow = getArrow(val);
    const sign = val > 0 ? '+' : '';
    return `<span class="${cls}">${arrow} ${sign}¥${Math.abs(Math.round(val)).toLocaleString()}</span>`;
}

function formatRevPerHour(val) {
    if (val === null || val === undefined) return '<span class="text-muted">-</span>';
    return '¥' + Math.round(val).toLocaleString() + '/h';
}

// 売上差分: 増加=緑(良)、減少=赤(悪) → 時間差分と逆方向
function getRevDiffClass(val) {
    if (val > 0) return 'diff-negative';  // 緑（増収は良い）
    if (val < 0) return 'diff-positive';  // 赤（減収は悪い）
    return 'diff-zero';
}

function formatRevDiff(val) {
    if (val === null || val === undefined) return '<span class="text-muted">-</span>';
    if (val === 0) return `<span class="diff-zero">→ ¥0</span>`;
    const cls = getRevDiffClass(val);
    const arrow = val > 0 ? '▲' : '▼';
    const sign = val > 0 ? '+' : '';
    return `<span class="${cls}">${arrow} ${sign}¥${Math.abs(Math.round(val)).toLocaleString()}</span>`;
}

function formatRevPerHourDiff(val) {
    if (val === null || val === undefined) return '<span class="text-muted">-</span>';
    if (val === 0) return `<span class="diff-zero">→ ¥0/h</span>`;
    const cls = getRevDiffClass(val);
    const arrow = val > 0 ? '▲' : '▼';
    const sign = val > 0 ? '+' : '';
    return `<span class="${cls}">${arrow} ${sign}¥${Math.abs(Math.round(val)).toLocaleString()}/h</span>`;
}

// ============================================
// XSSエスケープ（dashboard.js の escapeHtml と衝突回避）
// ============================================
function deptEscapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function deptEscapeAttr(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ============================================
// メインデータ読み込み
// ============================================
function loadOverview() {
    const baseSelect = document.getElementById('baseMonth');
    const compSelect = document.getElementById('compareMonth');
    const baseVal = baseSelect.value;
    const compVal = compSelect.value;

    let qs = '';
    if (baseVal) qs += `&base_month=${baseVal}`;
    if (compVal) qs += `&compare_month=${compVal}`;

    document.getElementById('overviewBody').innerHTML =
        '<tr><td colspan="10" class="text-center text-muted py-4">' +
        '<span class="spinner-border spinner-border-sm me-2"></span>読み込み中...</td></tr>';

    fetch(`/api/analytics/department-month-comparison?${qs}`)
        .then(r => r.json())
        .then(data => {
            populateMonthSelectors(data.available_months, data.base_month, data.compare_month);
            document.getElementById('periodLabel').innerHTML =
                `<i class="bi bi-calendar3 me-2"></i>${formatMonth(data.base_month)} → ${formatMonth(data.compare_month)}`;
            renderOverviewTable(data.departments, data.base_month, data.compare_month);
        })
        .catch(err => {
            console.error('Failed to load overview:', err);
            document.getElementById('overviewBody').innerHTML =
                '<tr><td colspan="10" class="text-center text-danger py-4">データの読み込みに失敗しました</td></tr>';
        });
}

function populateMonthSelectors(months, baseSel, compSel) {
    const baseSelect = document.getElementById('baseMonth');
    const compSelect = document.getElementById('compareMonth');

    const opts = months.map(m =>
        `<option value="${m}">${formatMonth(m)}</option>`
    ).join('');

    baseSelect.innerHTML = opts;
    compSelect.innerHTML = opts;

    if (baseSel) baseSelect.value = baseSel;
    if (compSel) compSelect.value = compSel;
}

// ============================================
// 全部門一覧テーブル
// ============================================
function renderOverviewTable(departments, baseMonth, compMonth) {
    const body = document.getElementById('overviewBody');

    if (!departments || departments.length === 0) {
        body.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4">データなし</td></tr>';
        return;
    }

    body.innerHTML = departments.map(d => {
        const isTotal = d.is_total;
        const rowCls = isTotal
            ? 'dept-row table-primary fw-bold'
            : `dept-row ${currentDept === d.department ? 'active' : ''}`;
        const clickAttr = isTotal
            ? `onclick="selectDepartment('全体', '${baseMonth}', '${compMonth}')"`
            : `onclick="selectDepartment('${deptEscapeAttr(d.department)}', '${baseMonth}', '${compMonth}')"`;
        return `
        <tr class="${rowCls}" ${clickAttr}>
            <td class="fw-bold">${deptEscapeHtml(d.department)}</td>
            <td class="text-end">${d.base_hours.toFixed(1)}h</td>
            <td class="text-end">${d.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(d.diff_hours, 'h')}</td>
            <td class="text-end">${formatCost(d.base_cost)}</td>
            <td class="text-end">${formatCost(d.compare_cost)}</td>
            <td class="text-end">${formatRevDiff(d.diff_cost)}</td>
            <td class="text-end">${formatRevPerHour(d.base_rev_per_hour)}</td>
            <td class="text-end">${formatRevPerHour(d.compare_rev_per_hour)}</td>
            <td class="text-end">${formatRevPerHourDiff(d.diff_rev_per_hour)}</td>
        </tr>
        `;
    }).join('');
}

// ============================================
// 部門詳細を選択・表示
// ============================================
function selectDepartment(dept, baseMonth, compMonth) {
    currentDept = dept;

    // 行のアクティブ状態を更新
    document.querySelectorAll('.dept-row').forEach(r => r.classList.remove('active'));
    event.currentTarget.classList.add('active');

    document.getElementById('detailSection').style.display = 'block';
    document.getElementById('detailDeptName').textContent = dept;

    // AI分析をリセット
    document.getElementById('aiReportPlaceholder').style.display = 'block';
    document.getElementById('aiReportContent').style.display = 'none';
    document.getElementById('aiReportBtn').disabled = false;
    document.getElementById('aiReportBtn').innerHTML = '<i class="bi bi-robot me-1"></i>AI分析を実行';

    // 最初のタブ（月次推移）に戻す
    const trendTabBtn = document.getElementById('deptTrendTab');
    if (trendTabBtn) {
        const tab = new bootstrap.Tab(trendTabBtn);
        tab.show();
    }

    // KPI表示をリセット
    document.getElementById('detailKPIs').innerHTML =
        '<div class="col-12 text-center text-muted py-3"><span class="spinner-border spinner-border-sm me-2"></span>読み込み中...</div>';

    // テーブルをリセット
    ['catTable', 'staffTable', 'workTable'].forEach(id => {
        const tbody = document.querySelector(`#${id} tbody`);
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">読み込み中...</td></tr>';
    });

    const bm = baseMonth || document.getElementById('baseMonth').value;
    const cm = compMonth || document.getElementById('compareMonth').value;

    // 詳細データと月次推移を並行取得
    const detailUrl = `/api/analytics/department-month-detail?department=${encodeURIComponent(dept)}&base_month=${bm}&compare_month=${cm}`;
    const trendUrl = `/api/analytics/department-monthly-trend?department=${encodeURIComponent(dept)}`;

    Promise.all([
        fetch(detailUrl).then(r => r.json()),
        fetch(trendUrl).then(r => r.json()),
    ])
    .then(([data, trendData]) => {
        currentData = data;
        renderDetailKPIs(data.summary);
        renderTrendChart(trendData);
        renderCategoryTab(data.category_breakdown);
        renderStaffTab(data.staff_breakdown);
        renderWorkTab(data.work_changes);
    })
    .catch(err => {
        console.error('Failed to load detail:', err);
        document.getElementById('detailKPIs').innerHTML =
            '<div class="col-12 text-center text-danger py-3">詳細データの読み込みに失敗しました</div>';
    });

    // スクロール
    document.getElementById('detailSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============================================
// KPIカード
// ============================================
function renderDetailKPIs(summary) {
    const container = document.getElementById('detailKPIs');
    const diffHoursCls = getDiffClass(summary.diff_hours);
    const diffCost = summary.compare_cost - summary.base_cost;
    const diffRevCls = getRevDiffClass(diffCost);
    const diffRphCls = summary.diff_rev_per_hour != null ? getRevDiffClass(summary.diff_rev_per_hour) : '';

    container.innerHTML = `
        <div class="col-4 col-md-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">前月 時間</div>
                    <div class="value">${summary.base_hours.toFixed(1)}h</div>
                </div>
            </div>
        </div>
        <div class="col-4 col-md-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">今月 時間</div>
                    <div class="value">${summary.compare_hours.toFixed(1)}h</div>
                </div>
            </div>
        </div>
        <div class="col-4 col-md-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">時間 差分</div>
                    <div class="value ${diffHoursCls}">${summary.diff_hours > 0 ? '+' : ''}${summary.diff_hours.toFixed(1)}h</div>
                    <div class="label">${formatPct(summary.diff_pct)}</div>
                </div>
            </div>
        </div>
        <div class="col-4 col-md-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">前月 売上</div>
                    <div class="value">${formatCost(summary.base_cost)}</div>
                </div>
            </div>
        </div>
        <div class="col-4 col-md-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">今月 売上</div>
                    <div class="value">${formatCost(summary.compare_cost)}</div>
                </div>
            </div>
        </div>
        <div class="col-4 col-md-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">売上 差分</div>
                    <div class="value ${diffRevCls}">${diffCost > 0 ? '+' : ''}¥${Math.abs(diffCost).toLocaleString()}</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-md-4 mt-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">前月 時間あたり売上</div>
                    <div class="value">${formatRevPerHour(summary.base_rev_per_hour)}</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-md-4 mt-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">今月 時間あたり売上</div>
                    <div class="value">${formatRevPerHour(summary.compare_rev_per_hour)}</div>
                </div>
            </div>
        </div>
        <div class="col-12 col-md-4 mt-2">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">時間あたり売上 差分</div>
                    <div class="value ${diffRphCls}">${summary.diff_rev_per_hour != null ? (summary.diff_rev_per_hour > 0 ? '+' : '') + '¥' + Math.abs(summary.diff_rev_per_hour).toLocaleString() + '/h' : '-'}</div>
                </div>
            </div>
        </div>
    `;
}

// ============================================
// カテゴリ別タブ
// ============================================
function renderCategoryTab(breakdown) {
    const tbody = document.querySelector('#catTable tbody');
    if (!breakdown || breakdown.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">データなし</td></tr>';
        return;
    }

    tbody.innerHTML = breakdown.map(item => `
        <tr>
            <td>${deptEscapeHtml(item.category)}</td>
            <td class="text-end">${item.base_hours.toFixed(1)}h</td>
            <td class="text-end">${item.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(item.diff_hours, 'h')}</td>
            <td class="text-end">${formatPct(item.diff_pct)}</td>
        </tr>
    `).join('');

    // チャート
    renderGroupedBarChart('deptCatCanvas', breakdown, 'category');
}

// ============================================
// スタッフ別タブ
// ============================================
function renderStaffTab(breakdown) {
    const tbody = document.querySelector('#staffTable tbody');
    if (!breakdown || breakdown.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">データなし</td></tr>';
        return;
    }

    tbody.innerHTML = breakdown.map(item => `
        <tr>
            <td>${deptEscapeHtml(item.staff_name)}</td>
            <td class="text-end">${item.base_hours.toFixed(1)}h</td>
            <td class="text-end">${item.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(item.diff_hours, 'h')}</td>
            <td class="text-end">${formatPct(item.diff_pct)}</td>
        </tr>
    `).join('');

    // チャート
    renderGroupedBarChart('deptStaffCanvas', breakdown, 'staff_name');
}

// ============================================
// 業務変動TOPタブ
// ============================================
function renderWorkTab(changes) {
    const tbody = document.querySelector('#workTable tbody');
    if (!changes || changes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">データなし</td></tr>';
        return;
    }

    tbody.innerHTML = changes.map(item => {
        const suffix = item.unit_suffix || 'h';
        const isCount = item.unit_type === 'count';
        const rowClass = isCount ? 'text-muted' : '';
        return `
        <tr class="${rowClass}">
            <td>${deptEscapeHtml(item.work_name)}${isCount ? ' <span class="badge bg-secondary">件数</span>' : ''}</td>
            <td class="text-end">${item.base_value.toFixed(1)}${suffix}</td>
            <td class="text-end">${item.compare_value.toFixed(1)}${suffix}</td>
            <td class="text-end">${formatDiff(item.diff_value, suffix)}</td>
            <td class="text-end">${formatPct(item.diff_pct)}</td>
        </tr>
        `;
    }).join('');
}

// ============================================
// Grouped Bar Chart 共通描画
// ============================================
function renderGroupedBarChart(canvasId, data, labelKey) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // 既存チャートを破棄
    if (canvasId === 'deptCatCanvas' && deptCatChart) {
        deptCatChart.destroy();
        deptCatChart = null;
    }
    if (canvasId === 'deptStaffCanvas' && deptStaffChart) {
        deptStaffChart.destroy();
        deptStaffChart = null;
    }

    // 上位15件に制限（見やすさのため）
    const sliced = data.slice(0, 15);
    const labels = sliced.map(d => {
        const name = d[labelKey] || '(未分類)';
        return name.length > 18 ? name.slice(0, 18) + '...' : name;
    });

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '前月',
                    data: sliced.map(d => d.base_hours),
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: 'rgba(59, 130, 246, 1)',
                    borderWidth: 1,
                    borderRadius: 3,
                },
                {
                    label: '今月',
                    data: sliced.map(d => d.compare_hours),
                    backgroundColor: 'rgba(249, 115, 22, 0.7)',
                    borderColor: 'rgba(249, 115, 22, 1)',
                    borderWidth: 1,
                    borderRadius: 3,
                }
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}h`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    title: { display: true, text: '時間 (h)' }
                },
                y: {
                    ticks: { font: { size: 11 } }
                }
            }
        }
    });

    if (canvasId === 'deptCatCanvas') deptCatChart = chart;
    if (canvasId === 'deptStaffCanvas') deptStaffChart = chart;
}

// ============================================
// AI分析レポート生成（dashboard の generateAIReport と衝突回避）
// ============================================
function generateDeptAIReport() {
    if (!currentData || !currentDept) return;

    const btn = document.getElementById('aiReportBtn');
    const placeholder = document.getElementById('aiReportPlaceholder');
    const content = document.getElementById('aiReportContent');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>AI分析中...';

    const bm = document.getElementById('baseMonth').value;
    const cm = document.getElementById('compareMonth').value;

    fetch('/api/ai/department-month-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            department: currentDept,
            base_month: bm,
            compare_month: cm,
        })
    })
    .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
    })
    .then(data => {
        placeholder.style.display = 'none';
        content.style.display = 'block';
        content.innerHTML = renderDeptMarkdown(data.report);
    })
    .catch(err => {
        console.error('AI report failed:', err);
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-robot me-1"></i>再試行';
        content.style.display = 'block';
        content.innerHTML = '<div class="alert alert-danger">AI分析に失敗しました。しばらく待ってから再試行してください。</div>';
    });
}

// ============================================
// 簡易Markdownレンダラ
// ============================================
function renderDeptMarkdown(text) {
    if (!text) return '';

    let html = deptEscapeHtml(text);

    html = html.replace(/^##### (.+)$/gm, '<h6 class="mt-3 mb-1">$1</h6>');
    html = html.replace(/^#### (.+)$/gm, '<h5 class="mt-3 mb-2">$1</h5>');
    html = html.replace(/^### (.+)$/gm, '<h5 class="mt-3 mb-2" style="color:#4338ca">$1</h5>');
    html = html.replace(/^## (.+)$/gm, '<h5 class="mt-4 mb-2" style="color:#4338ca;font-size:1.1rem">$1</h5>');

    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul class="mb-2">$1</ul>');

    html = html.replace(/^---$/gm, '<hr class="my-3">');

    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p>\s*<\/p>/g, '');

    return html;
}

// ============================================
// 月次推移折れ線グラフ
// ============================================
function renderTrendChart(data) {
    const canvas = document.getElementById('deptTrendCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (deptTrendChart) {
        deptTrendChart.destroy();
        deptTrendChart = null;
    }

    if (!data || !data.months || data.months.length === 0) {
        return;
    }

    const labels = data.months.map(m => formatMonth(m));
    const hasRevenue = data.rev_per_hour && data.rev_per_hour.some(v => v !== null);

    const datasets = [{
        label: '業務時間 (h)',
        data: data.hours,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99, 102, 241, 0.1)',
        borderWidth: 2,
        pointBackgroundColor: '#6366f1',
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        fill: true,
        tension: 0.3,
        yAxisID: 'y',
    }];

    if (hasRevenue) {
        datasets.push({
            label: '時間あたり売上 (¥/h)',
            data: data.rev_per_hour,
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            borderWidth: 2,
            pointBackgroundColor: '#f59e0b',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 5,
            pointHoverRadius: 7,
            fill: false,
            tension: 0.3,
            yAxisID: 'y1',
            borderDash: [5, 3],
        });
    }

    const scales = {
        x: { grid: { display: false } },
        y: {
            beginAtZero: true,
            title: { display: true, text: '時間 (h)' },
            position: 'left',
        },
    };

    if (hasRevenue) {
        scales.y1 = {
            beginAtZero: true,
            title: { display: true, text: '¥/h' },
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: {
                callback: function(val) {
                    return '¥' + val.toLocaleString();
                }
            }
        };
    }

    deptTrendChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: hasRevenue, position: 'top' },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            if (ctx.dataset.yAxisID === 'y1') {
                                return ctx.raw != null ? `¥${ctx.raw.toLocaleString()}/h` : '-';
                            }
                            return `${ctx.raw.toFixed(1)}h`;
                        }
                    }
                }
            },
            scales: scales,
        }
    });
}

// ============================================
// 詳細セクションを閉じる
// ============================================
function closeDetail() {
    document.getElementById('detailSection').style.display = 'none';
    document.querySelectorAll('.dept-row').forEach(r => r.classList.remove('active'));
    currentDept = null;
    currentData = null;
}
