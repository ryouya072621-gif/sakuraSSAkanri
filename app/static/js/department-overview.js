// 部門比較ダッシュボード - 月次比較（事実ベース）
let catChart = null;
let staffChart = null;
let currentDept = null;
let currentData = null;

document.addEventListener('DOMContentLoaded', function() {
    loadOverview();

    // タブ切り替え時にチャートをリサイズ
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function() {
            if (catChart) catChart.resize();
            if (staffChart) staffChart.resize();
        });
    });
});

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

// ============================================
// XSSエスケープ
// ============================================
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
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
        '<tr><td colspan="7" class="text-center text-muted py-4">' +
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
                '<tr><td colspan="7" class="text-center text-danger py-4">データの読み込みに失敗しました</td></tr>';
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
        body.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">データなし</td></tr>';
        return;
    }

    body.innerHTML = departments.map(d => `
        <tr class="dept-row ${currentDept === d.department ? 'active' : ''}"
            onclick="selectDepartment('${escapeAttr(d.department)}', '${baseMonth}', '${compMonth}')">
            <td class="fw-bold">${escapeHtml(d.department)}</td>
            <td class="text-end">${d.base_hours.toFixed(1)}h</td>
            <td class="text-end">${d.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(d.diff_hours, 'h')}</td>
            <td class="text-end">${formatCost(d.base_cost)}</td>
            <td class="text-end">${formatCost(d.compare_cost)}</td>
            <td class="text-end">${formatCostDiff(d.diff_cost)}</td>
        </tr>
    `).join('');
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

    // 最初のタブに戻す
    const catTabBtn = document.getElementById('catTab');
    if (catTabBtn) {
        const tab = new bootstrap.Tab(catTabBtn);
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

    fetch(`/api/analytics/department-month-detail?department=${encodeURIComponent(dept)}&base_month=${bm}&compare_month=${cm}`)
        .then(r => r.json())
        .then(data => {
            currentData = data;
            renderDetailKPIs(data.summary);
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
    const diffCostCls = getDiffClass(diffCost);

    container.innerHTML = `
        <div class="col-6 col-md-3">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">前月 時間</div>
                    <div class="value">${summary.base_hours.toFixed(1)}h</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-md-3">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">今月 時間</div>
                    <div class="value">${summary.compare_hours.toFixed(1)}h</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-md-3">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">時間 差分</div>
                    <div class="value ${diffHoursCls}">${summary.diff_hours > 0 ? '+' : ''}${summary.diff_hours.toFixed(1)}h</div>
                    <div class="label">${formatPct(summary.diff_pct)}</div>
                </div>
            </div>
        </div>
        <div class="col-6 col-md-3">
            <div class="card kpi-card h-100">
                <div class="card-body py-3">
                    <div class="label">コスト 差分</div>
                    <div class="value ${diffCostCls}">${diffCost > 0 ? '+' : ''}¥${Math.abs(diffCost).toLocaleString()}</div>
                </div>
            </div>
        </div>
    `;
}

// ============================================
// カテゴリ別タブ
// ============================================
function renderCategoryTab(breakdown) {
    // テーブル
    const tbody = document.querySelector('#catTable tbody');
    if (!breakdown || breakdown.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">データなし</td></tr>';
        return;
    }

    tbody.innerHTML = breakdown.map(item => `
        <tr>
            <td>${escapeHtml(item.category)}</td>
            <td class="text-end">${item.base_hours.toFixed(1)}h</td>
            <td class="text-end">${item.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(item.diff_hours, 'h')}</td>
            <td class="text-end">${formatPct(item.diff_pct)}</td>
        </tr>
    `).join('');

    // チャート
    renderGroupedBarChart('catChart', breakdown, 'category');
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
            <td>${escapeHtml(item.staff_name)}</td>
            <td class="text-end">${item.base_hours.toFixed(1)}h</td>
            <td class="text-end">${item.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(item.diff_hours, 'h')}</td>
            <td class="text-end">${formatPct(item.diff_pct)}</td>
        </tr>
    `).join('');

    // チャート
    renderGroupedBarChart('staffChart', breakdown, 'staff_name');
}

// ============================================
// 業務変動TOPタブ
// ============================================
function renderWorkTab(changes) {
    const tbody = document.querySelector('#workTable tbody');
    if (!changes || changes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">データなし</td></tr>';
        return;
    }

    tbody.innerHTML = changes.map(item => `
        <tr>
            <td>${escapeHtml(item.work_name)}</td>
            <td class="text-end">${item.base_hours.toFixed(1)}h</td>
            <td class="text-end">${item.compare_hours.toFixed(1)}h</td>
            <td class="text-end">${formatDiff(item.diff_hours, 'h')}</td>
            <td class="text-end">${formatPct(item.diff_pct)}</td>
        </tr>
    `).join('');
}

// ============================================
// Grouped Bar Chart 共通描画
// ============================================
function renderGroupedBarChart(canvasId, data, labelKey) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // 既存チャートを破棄
    if (canvasId === 'catChart' && catChart) {
        catChart.destroy();
        catChart = null;
    }
    if (canvasId === 'staffChart' && staffChart) {
        staffChart.destroy();
        staffChart = null;
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

    if (canvasId === 'catChart') catChart = chart;
    if (canvasId === 'staffChart') staffChart = chart;
}

// ============================================
// AI分析レポート生成
// ============================================
function generateAIReport() {
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
        content.innerHTML = renderMarkdown(data.report);
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
function renderMarkdown(text) {
    if (!text) return '';

    // XSSエスケープ
    let html = escapeHtml(text);

    // 見出し（h5, h4）
    html = html.replace(/^##### (.+)$/gm, '<h6 class="mt-3 mb-1">$1</h6>');
    html = html.replace(/^#### (.+)$/gm, '<h5 class="mt-3 mb-2">$1</h5>');
    html = html.replace(/^### (.+)$/gm, '<h5 class="mt-3 mb-2" style="color:#4338ca">$1</h5>');
    html = html.replace(/^## (.+)$/gm, '<h5 class="mt-4 mb-2" style="color:#4338ca;font-size:1.1rem">$1</h5>');

    // 太字・斜体
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // リスト
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    // 連続する<li>を<ul>で囲む
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul class="mb-2">$1</ul>');

    // 水平線
    html = html.replace(/^---$/gm, '<hr class="my-3">');

    // 改行
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';

    // 空の<p>を除去
    html = html.replace(/<p>\s*<\/p>/g, '');

    return html;
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
