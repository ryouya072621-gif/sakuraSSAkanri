/**
 * Project Analysis JavaScript
 * プロジェクト × 作業タイプ 分析
 */

let projectChart = null;
let taskTypeChart = null;
let taskTypePieChart = null;
let dateRange = { min: null, max: null };
let currentData = null;  // 現在のデータをキャッシュ

// 初期化
document.addEventListener('DOMContentLoaded', async () => {
    await loadDateRange();
    await loadCategories();
    await loadStaffList();
    await loadData();

    // イベントリスナー
    document.getElementById('category1Select').addEventListener('change', loadData);
    document.getElementById('staffSelect').addEventListener('change', loadData);
    document.getElementById('startDate').addEventListener('change', loadData);
    document.getElementById('endDate').addEventListener('change', loadData);

    // ビューモード切り替え
    document.querySelectorAll('input[name="viewMode"]').forEach(radio => {
        radio.addEventListener('change', (e) => switchView(e.target.value));
    });
});

function switchView(mode) {
    // 全ビューを非表示
    document.getElementById('projectView').style.display = 'none';
    document.getElementById('taskTypeView').style.display = 'none';
    document.getElementById('matrixView').style.display = 'none';

    // 選択されたビューを表示
    switch (mode) {
        case 'project':
            document.getElementById('projectView').style.display = 'block';
            break;
        case 'taskType':
            document.getElementById('taskTypeView').style.display = 'block';
            break;
        case 'matrix':
            document.getElementById('matrixView').style.display = 'block';
            break;
    }

    // データがあれば再描画
    if (currentData) {
        renderView(mode, currentData);
    }
}

async function loadDateRange() {
    try {
        const response = await fetch('/api/date-range');
        const data = await response.json();
        dateRange = data;

        if (data.min_date) {
            document.getElementById('startDate').value = data.min_date;
        }
        if (data.max_date) {
            document.getElementById('endDate').value = data.max_date;
        }
    } catch (error) {
        console.error('Error loading date range:', error);
    }
}

async function loadCategories() {
    try {
        const response = await fetch('/api/categories1');
        const categories = await response.json();
        const select = document.getElementById('category1Select');

        categories.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat;
            option.textContent = cat;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

async function loadStaffList() {
    try {
        const category1 = document.getElementById('category1Select').value;
        const url = category1 ? `/api/staff?category1=${encodeURIComponent(category1)}` : '/api/staff';
        const response = await fetch(url);
        const staff = await response.json();

        const select = document.getElementById('staffSelect');
        select.innerHTML = '<option value="">全スタッフ</option>';
        staff.forEach(s => {
            const option = document.createElement('option');
            option.value = s.name;
            option.textContent = s.name;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading staff list:', error);
    }
}

function getFilterParams() {
    const params = new URLSearchParams();
    const category1 = document.getElementById('category1Select').value;
    const staff = document.getElementById('staffSelect').value;
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    if (category1) params.append('category1', category1);
    if (staff) params.append('staff', staff);
    if (startDate) params.append('start', startDate);
    if (endDate) params.append('end', endDate);

    return params.toString();
}

async function loadData() {
    const params = getFilterParams();

    try {
        // 並行してデータを取得
        const [breakdownRes, summaryRes, unmappedRes] = await Promise.all([
            fetch(`/api/project-breakdown?${params}`),
            fetch(`/api/project-summary?${params}`),
            fetch(`/api/unmapped-work-items?${params}&limit=100`)
        ]);

        const breakdown = await breakdownRes.json();
        const summary = await summaryRes.json();
        const unmapped = await unmappedRes.json();

        // データをキャッシュ
        currentData = { breakdown, summary, unmapped };

        // KPIを更新
        document.getElementById('projectCount').textContent = breakdown.projects.length;
        document.getElementById('totalHours').textContent = breakdown.grand_total.toLocaleString();
        document.getElementById('topProject').textContent = breakdown.projects[0] || '-';
        document.getElementById('unmappedCount').textContent = unmapped.total;

        // 現在のビューモードで描画
        const currentMode = document.querySelector('input[name="viewMode"]:checked').value;
        renderView(currentMode, currentData);

    } catch (error) {
        console.error('Error loading data:', error);
    }
}

function renderView(mode, data) {
    const { breakdown, summary } = data;

    switch (mode) {
        case 'project':
            updateProjectChart(summary.projects);
            updateProjectRanking(summary.projects, breakdown);
            break;
        case 'taskType':
            updateTaskTypeCharts(breakdown.task_type_totals, breakdown);
            updateTaskTypeRanking(breakdown);
            break;
        case 'matrix':
            updateMatrixTable(breakdown);
            break;
    }
}

function updateProjectChart(projects) {
    const ctx = document.getElementById('projectChart').getContext('2d');

    if (projectChart) {
        projectChart.destroy();
    }

    const colors = generateColors(projects.length);

    projectChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: projects.map(p => p.name),
            datasets: [{
                data: projects.map(p => p.total_hours),
                backgroundColor: colors
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        boxWidth: 12,
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const p = projects[context.dataIndex];
                            return `${p.name}: ${p.total_hours}h (${p.percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

function updateProjectRanking(projects, breakdown) {
    const tbody = document.getElementById('projectRankingBody');
    tbody.innerHTML = '';

    if (projects.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">データがありません</td></tr>';
        return;
    }

    projects.forEach((p, index) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <span class="badge bg-secondary me-2">${index + 1}</span>
                ${escapeHtml(p.name)}
            </td>
            <td class="text-end fw-bold">${p.total_hours.toFixed(1)}h</td>
            <td>
                <div class="progress" style="height: 20px; width: 100px;">
                    <div class="progress-bar bg-primary" style="width: ${p.percentage}%">${p.percentage.toFixed(1)}%</div>
                </div>
            </td>
            <td><span class="badge bg-light text-dark">${escapeHtml(p.top_task_type)}</span></td>
        `;
        tbody.appendChild(row);
    });
}

function updateTaskTypeCharts(taskTypeTotals, breakdown) {
    // 棒グラフ
    const barCtx = document.getElementById('taskTypeChart').getContext('2d');
    if (taskTypeChart) {
        taskTypeChart.destroy();
    }

    const labels = Object.keys(taskTypeTotals);
    const data = Object.values(taskTypeTotals);
    const total = data.reduce((a, b) => a + b, 0);

    taskTypeChart = new Chart(barCtx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '時間',
                data: data,
                backgroundColor: 'rgba(59, 130, 246, 0.7)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    title: { display: true, text: '時間 (h)' }
                }
            }
        }
    });

    // 円グラフ
    const pieCtx = document.getElementById('taskTypePieChart').getContext('2d');
    if (taskTypePieChart) {
        taskTypePieChart.destroy();
    }

    const colors = generateColors(labels.length);

    taskTypePieChart = new Chart(pieCtx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        boxWidth: 12,
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const value = data[context.dataIndex];
                            const pct = total > 0 ? (value / total * 100).toFixed(1) : 0;
                            return `${labels[context.dataIndex]}: ${value.toFixed(1)}h (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function updateTaskTypeRanking(breakdown) {
    const tbody = document.getElementById('taskTypeRankingBody');
    tbody.innerHTML = '';

    const taskTypes = breakdown.task_types;
    const totals = breakdown.task_type_totals;
    const matrix = breakdown.matrix;
    const grandTotal = breakdown.grand_total;

    if (taskTypes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">データがありません</td></tr>';
        return;
    }

    taskTypes.forEach((tt, index) => {
        const hours = totals[tt] || 0;
        const pct = grandTotal > 0 ? (hours / grandTotal * 100) : 0;

        // このタスクタイプで最も時間が多いプロジェクトを探す
        let topProject = '-';
        let maxHours = 0;
        for (const proj of breakdown.projects) {
            const h = matrix[proj]?.[tt] || 0;
            if (h > maxHours) {
                maxHours = h;
                topProject = proj;
            }
        }

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <span class="badge bg-secondary me-2">${index + 1}</span>
                ${escapeHtml(tt)}
            </td>
            <td class="text-end fw-bold">${hours.toFixed(1)}h</td>
            <td>
                <div class="progress" style="height: 20px; width: 100px;">
                    <div class="progress-bar bg-success" style="width: ${pct}%">${pct.toFixed(1)}%</div>
                </div>
            </td>
            <td><span class="badge bg-light text-dark">${escapeHtml(topProject)}</span></td>
        `;
        tbody.appendChild(row);
    });
}

function updateMatrixTable(breakdown) {
    const headerRow = document.getElementById('matrixHeaderRow');
    const tbody = document.getElementById('matrixBody');

    // ヘッダーを構築
    headerRow.innerHTML = '<th class="sticky-top bg-light" style="min-width: 150px;">プロジェクト</th>';
    breakdown.task_types.forEach(tt => {
        headerRow.innerHTML += `<th class="sticky-top bg-light matrix-cell">${escapeHtml(tt)}</th>`;
    });
    headerRow.innerHTML += '<th class="sticky-top bg-light matrix-cell fw-bold">合計</th>';

    // ボディを構築
    tbody.innerHTML = '';

    if (breakdown.projects.length === 0) {
        tbody.innerHTML = '<tr><td colspan="' + (breakdown.task_types.length + 2) + '" class="text-center py-4 text-muted">データがありません。AI抽出を実行してください。</td></tr>';
        return;
    }

    const maxValue = Math.max(...Object.values(breakdown.project_totals));

    breakdown.projects.forEach(proj => {
        const row = document.createElement('tr');
        row.className = 'project-row';

        // プロジェクト名
        row.innerHTML = `<td class="fw-bold">${escapeHtml(proj)}</td>`;

        // 各作業タイプの値
        breakdown.task_types.forEach(tt => {
            const value = breakdown.matrix[proj]?.[tt] || 0;
            const cellClass = value > 0 ? (value > maxValue * 0.3 ? 'high-value' : 'has-value') : '';
            row.innerHTML += `<td class="matrix-cell ${cellClass}">${value > 0 ? value.toFixed(1) : '-'}</td>`;
        });

        // 合計
        const total = breakdown.project_totals[proj] || 0;
        row.innerHTML += `<td class="matrix-cell fw-bold">${total.toFixed(1)}</td>`;

        tbody.appendChild(row);
    });

    // 合計行
    const totalRow = document.createElement('tr');
    totalRow.className = 'table-light fw-bold';
    totalRow.innerHTML = '<td>合計</td>';
    breakdown.task_types.forEach(tt => {
        const total = breakdown.task_type_totals[tt] || 0;
        totalRow.innerHTML += `<td class="matrix-cell">${total.toFixed(1)}</td>`;
    });
    totalRow.innerHTML += `<td class="matrix-cell">${breakdown.grand_total.toFixed(1)}</td>`;
    tbody.appendChild(totalRow);
}

async function showUnmappedItems() {
    const params = getFilterParams();

    try {
        const response = await fetch(`/api/unmapped-work-items?${params}&limit=100`);
        const data = await response.json();

        const tbody = document.getElementById('unmappedTableBody');
        tbody.innerHTML = '';

        if (data.items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-success"><i class="bi bi-check-circle me-2"></i>全ての業務が分類済みです</td></tr>';
        } else {
            data.items.forEach(item => {
                tbody.innerHTML += `
                    <tr>
                        <td>${escapeHtml(item.work_name)}</td>
                        <td><span class="badge bg-secondary">${escapeHtml(item.category1 || '-')}</span></td>
                        <td>${escapeHtml(item.category2 || '-')}</td>
                        <td class="text-end">${item.total_hours.toFixed(1)}h</td>
                    </tr>
                `;
            });
        }

        const modal = new bootstrap.Modal(document.getElementById('unmappedModal'));
        modal.show();

    } catch (error) {
        console.error('Error loading unmapped items:', error);
        alert('未分類業務の取得に失敗しました');
    }
}

async function runProjectExtraction() {
    const params = getFilterParams();

    // 進捗モーダルを表示
    const progressModal = new bootstrap.Modal(document.getElementById('extractionModal'));
    progressModal.show();

    try {
        // 未分類の業務を取得
        document.getElementById('extractionStatus').textContent = '未分類業務を取得中...';
        document.getElementById('extractionProgress').style.width = '10%';

        const unmappedRes = await fetch(`/api/unmapped-work-items?${params}&limit=500`);
        const unmapped = await unmappedRes.json();

        if (unmapped.items.length === 0) {
            document.getElementById('extractionStatus').textContent = '分類が必要な業務はありません';
            document.getElementById('extractionProgress').style.width = '100%';
            setTimeout(() => {
                progressModal.hide();
            }, 1500);
            return;
        }

        // AI抽出を実行
        document.getElementById('extractionStatus').textContent = `${unmapped.items.length}件の業務をAIで分析中...`;
        document.getElementById('extractionProgress').style.width = '30%';

        const extractRes = await fetch('/api/ai/extract-projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                items: unmapped.items.map(item => ({
                    work_name: item.work_name,
                    category1: item.category1,
                    category2: item.category2
                })),
                save: true
            })
        });

        if (!extractRes.ok) {
            throw new Error('AI抽出に失敗しました');
        }

        const extractResult = await extractRes.json();

        document.getElementById('extractionStatus').textContent = `${extractResult.results.length}件の抽出が完了しました`;
        document.getElementById('extractionProgress').style.width = '100%';
        document.getElementById('extractionProgress').classList.remove('progress-bar-animated');
        document.getElementById('extractionProgress').classList.add('bg-success');

        // データを再読み込み
        setTimeout(async () => {
            progressModal.hide();
            // プログレスバーをリセット
            document.getElementById('extractionProgress').classList.remove('bg-success');
            document.getElementById('extractionProgress').classList.add('progress-bar-animated');
            await loadData();
        }, 1500);

    } catch (error) {
        console.error('Error during extraction:', error);
        document.getElementById('extractionStatus').textContent = `エラー: ${error.message}`;
        document.getElementById('extractionProgress').classList.add('bg-danger');

        setTimeout(() => {
            progressModal.hide();
            document.getElementById('extractionProgress').classList.remove('bg-danger');
        }, 3000);
    }
}

function setDateRange(preset) {
    const today = new Date();
    let start, end;

    switch (preset) {
        case 'thisMonth':
            start = new Date(today.getFullYear(), today.getMonth(), 1);
            end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
            break;
        case 'lastMonth':
            start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            end = new Date(today.getFullYear(), today.getMonth(), 0);
            break;
        case 'all':
            start = dateRange.min ? new Date(dateRange.min) : today;
            end = dateRange.max ? new Date(dateRange.max) : today;
            break;
        default:
            return;
    }

    document.getElementById('startDate').value = formatDate(start);
    document.getElementById('endDate').value = formatDate(end);
    loadData();
}

function formatDate(date) {
    return date.toISOString().split('T')[0];
}

function generateColors(count) {
    const baseColors = [
        '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
        '#06B6D4', '#EC4899', '#84CC16', '#F97316', '#6366F1',
        '#14B8A6', '#A855F7', '#22C55E', '#0EA5E9', '#D946EF'
    ];

    const colors = [];
    for (let i = 0; i < count; i++) {
        colors.push(baseColors[i % baseColors.length]);
    }
    return colors;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
