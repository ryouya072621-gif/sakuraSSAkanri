let categoryChart = null;
let dailyChart = null;
let trendChart = null;
let dateRange = { min: null, max: null };
let categoryColors = {};
let badgeStyles = {};
let isGroupMode = false;  // ランキングのグループ表示モード

document.addEventListener('DOMContentLoaded', async function() {
    // まずカテゴリ色情報とデフォルト設定を読み込む
    await Promise.all([
        loadCategoryColors(),
        loadDefaultSettings()
    ]);

    loadCategories1();
    loadStaffList();
    loadDateRange();

    document.getElementById('category1Select').addEventListener('change', onCategory1Change);
    document.getElementById('staffSelect').addEventListener('change', refreshData);
    document.getElementById('startDate').addEventListener('change', refreshData);
    document.getElementById('endDate').addEventListener('change', refreshData);
    document.getElementById('hourlyRate').addEventListener('change', refreshData);
});

async function loadCategoryColors() {
    try {
        const response = await fetch('/api/categories/colors');
        const data = await response.json();
        categoryColors = data.colors || {};
        badgeStyles = data.badge_styles || {};
    } catch (e) {
        console.error('Failed to load category colors:', e);
    }
}

async function loadDefaultSettings() {
    try {
        const response = await fetch('/api/settings/defaults');
        const data = await response.json();
        if (data.default_hourly_rate) {
            document.getElementById('hourlyRate').value = data.default_hourly_rate;
        }
    } catch (e) {
        console.error('Failed to load default settings:', e);
    }
}

async function loadCategories1() {
    const response = await fetch('/api/categories1');
    const categories = await response.json();

    const select = document.getElementById('category1Select');
    select.innerHTML = '<option value="">全部門</option>';

    categories.forEach(cat => {
        const option = document.createElement('option');
        option.value = cat;
        option.textContent = cat;
        select.appendChild(option);
    });
}

async function onCategory1Change() {
    await loadStaffList();
    refreshData();
}

async function loadStaffList() {
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
}

async function loadDateRange() {
    const response = await fetch('/api/date-range');
    dateRange = await response.json();

    if (dateRange.min_date && dateRange.max_date) {
        document.getElementById('startDate').value = dateRange.min_date;
        document.getElementById('endDate').value = dateRange.max_date;
    }

    // 初回データ読み込み
    refreshData();
}

function setDateRange(type) {
    const today = new Date();
    let start, end;

    switch(type) {
        case 'thisMonth':
            start = new Date(today.getFullYear(), today.getMonth(), 1);
            end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
            break;
        case 'lastMonth':
            start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            end = new Date(today.getFullYear(), today.getMonth(), 0);
            break;
        case 'last7Days':
            start = new Date(today);
            start.setDate(start.getDate() - 7);
            end = today;
            break;
        case 'all':
            document.getElementById('startDate').value = dateRange.min_date || '';
            document.getElementById('endDate').value = dateRange.max_date || '';
            refreshData();
            return;
    }

    document.getElementById('startDate').value = formatDate(start);
    document.getElementById('endDate').value = formatDate(end);
    refreshData();
}

function formatDate(date) {
    return date.toISOString().split('T')[0];
}

function getParams() {
    return {
        category1: document.getElementById('category1Select').value,
        staff: document.getElementById('staffSelect').value,
        start: document.getElementById('startDate').value,
        end: document.getElementById('endDate').value,
        hourly_rate: document.getElementById('hourlyRate').value
    };
}

function buildQueryString(params) {
    return Object.entries(params)
        .filter(([_, v]) => v)
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
        .join('&');
}

async function refreshData() {
    const params = getParams();
    const qs = buildQueryString(params);

    await Promise.all([
        loadSummary(qs),
        loadCategoryChart(qs),
        loadDailyChart(qs),
        loadRanking(qs),
        loadTrendChart(qs),
        loadAlerts(qs)
    ]);

    // AIインサイトは非同期で別途読み込み（遅延があっても他をブロックしない）
    if (typeof loadAIInsights === 'function') {
        loadAIInsights();
    }
}

async function loadSummary(qs) {
    const response = await fetch(`/api/summary?${qs}`);
    const data = await response.json();

    document.getElementById('totalHours').textContent = data.total_hours.toLocaleString();
    document.getElementById('totalCost').textContent = data.total_cost.toLocaleString();
    document.getElementById('taskTypes').textContent = data.task_types;
    document.getElementById('reductionRatio').textContent = data.reduction_ratio;
}

async function loadCategoryChart(qs) {
    const response = await fetch(`/api/category-breakdown?${qs}`);
    const data = await response.json();

    const ctx = document.getElementById('categoryChart').getContext('2d');

    if (categoryChart) {
        categoryChart.destroy();
    }

    categoryChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.category),
            datasets: [{
                data: data.map(d => d.hours),
                backgroundColor: data.map(d => categoryColors[d.category] || '#999'),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        usePointStyle: true,
                        padding: 15
                    }
                }
            },
            cutout: '60%'
        }
    });
}

async function loadDailyChart(qs) {
    const response = await fetch(`/api/daily-breakdown?${qs}`);
    const data = await response.json();

    const ctx = document.getElementById('dailyChart').getContext('2d');

    if (dailyChart) {
        dailyChart.destroy();
    }

    dailyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: data.datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 10
                    }
                }
            },
            scales: {
                x: {
                    stacked: true,
                    grid: {
                        display: false
                    }
                },
                y: {
                    stacked: true,
                    title: {
                        display: true,
                        text: '時間(h)'
                    }
                }
            }
        }
    });
}

async function loadRanking(qs) {
    // グループモードの場合はパラメータを追加
    const url = isGroupMode ? `/api/ranking?${qs}&group=true` : `/api/ranking?${qs}`;
    const response = await fetch(url);
    const data = await response.json();

    const tbody = document.getElementById('rankingTable');
    const thead = document.getElementById('rankingTableHead');
    const badge = document.getElementById('rankingBadge');

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">データがありません</td></tr>';
        return;
    }

    if (isGroupMode) {
        // グループモード用のヘッダー
        thead.innerHTML = `
            <tr>
                <th style="width: 30px;"></th>
                <th>業務グループ</th>
                <th>中分類</th>
                <th>カテゴリ</th>
                <th class="text-end">合計時間</th>
                <th class="text-end">推定コスト</th>
                <th class="text-center">件数</th>
                <th class="text-center">操作</th>
            </tr>
        `;
        badge.textContent = `${data.length}グループ`;
        renderGroupedRanking(data, tbody);
    } else {
        // 通常モード用のヘッダー
        thead.innerHTML = `
            <tr>
                <th>業務名</th>
                <th>カテゴリ</th>
                <th class="text-end">合計時間</th>
                <th>割合</th>
                <th class="text-end">推定コスト</th>
                <th>判定</th>
                <th class="text-center">操作</th>
            </tr>
        `;
        badge.textContent = `上位${data.length}項目`;
        renderNormalRanking(data, tbody);
    }
}

function renderNormalRanking(data, tbody) {
    tbody.innerHTML = data.map(item => {
        const style = badgeStyles[item.category] || { bg: '#f3f4f6', text: '#374151' };
        const badgeStyle = `background-color: ${style.bg}; color: ${style.text};`;
        const progressColor = item.is_reduction_target ? '#dc2626' : (categoryColors[item.category] || '#3b82f6');

        // 業務名固有の削減対象かどうかでボタン表示を変える
        const isTaskTarget = item.is_task_reduction_target;
        const toggleBtn = isTaskTarget
            ? `<button class="btn btn-sm btn-warning toggle-reduction-btn" data-work-name="${escapeHtmlAttr(item.work_name)}" title="削減対象を解除"><i class="bi bi-exclamation-triangle-fill"></i></button>`
            : `<button class="btn btn-sm btn-outline-secondary toggle-reduction-btn" data-work-name="${escapeHtmlAttr(item.work_name)}" title="削減対象に指定"><i class="bi bi-bullseye"></i></button>`;

        // 単位サフィックスを取得（APIから提供されない場合はデフォルトで'h'）
        const unitSuffix = item.unit_suffix || 'h';

        return `
        <tr>
            <td>${escapeHtml(item.work_name)}</td>
            <td><span class="category-badge" style="${badgeStyle}">${item.category}</span></td>
            <td class="text-end">${item.hours}${unitSuffix}</td>
            <td>
                <div class="d-flex align-items-center">
                    <div class="progress progress-thin flex-grow-1 me-2" style="width: 80px;">
                        <div class="progress-bar" style="width: ${item.ratio}%; background-color: ${progressColor}"></div>
                    </div>
                    <span>${item.ratio}%</span>
                </div>
            </td>
            <td class="text-end">¥${item.cost.toLocaleString()}</td>
            <td>${item.is_reduction_target ? '<span class="reduction-target">削減対象</span>' : '-'}</td>
            <td class="text-center">${toggleBtn}</td>
        </tr>
    `}).join('');

    // トグルボタンにイベントリスナーを追加
    document.querySelectorAll('.toggle-reduction-btn').forEach(btn => {
        btn.addEventListener('click', handleToggleReduction);
    });
}

function renderGroupedRanking(data, tbody) {
    let html = '';

    data.forEach((group, idx) => {
        const style = badgeStyles[group.category] || { bg: '#f3f4f6', text: '#374151' };
        const badgeStyle = `background-color: ${style.bg}; color: ${style.text};`;
        const groupId = `group-${idx}`;
        const hasMembers = group.members && group.members.length > 1;

        // メンバーの業務名リストをJSON形式で保存
        const memberWorkNames = group.members ? group.members.map(m => m.work_name) : [group.normalized_name];
        const memberWorkNamesJson = JSON.stringify(memberWorkNames).replace(/"/g, '&quot;');

        // グループ内に削減対象があるかチェック
        const hasReductionTarget = group.members && group.members.some(m => m.is_reduction_target || m.is_task_reduction_target);

        // グループ行（親行）
        html += `
        <tr class="group-row" data-group-id="${groupId}" style="cursor: ${hasMembers ? 'pointer' : 'default'};">
            <td class="text-center expand-cell">
                ${hasMembers ? `<i class="bi bi-chevron-right group-toggle" data-group-id="${groupId}"></i>` : ''}
            </td>
            <td>
                <strong>${escapeHtml(group.normalized_name)}</strong>
                ${hasMembers ? `<small class="text-muted ms-1">(他${group.member_count - 1}件)</small>` : ''}
            </td>
            <td><span class="badge bg-light text-dark">${escapeHtml(group.group_name)}</span></td>
            <td><span class="category-badge" style="${badgeStyle}">${group.category || '-'}</span></td>
            <td class="text-end"><strong>${group.total_hours}h</strong></td>
            <td class="text-end">¥${group.total_cost.toLocaleString()}</td>
            <td class="text-center">${group.member_count}件</td>
            <td class="text-center action-cell">
                <button class="btn btn-sm ${hasReductionTarget ? 'btn-warning' : 'btn-outline-secondary'} bulk-reduction-btn"
                        data-work-names="${memberWorkNamesJson}"
                        data-is-target="${hasReductionTarget}"
                        title="${hasReductionTarget ? 'グループ全体を削減対象から解除' : 'グループ全体を削減対象に指定'}"
                        onclick="event.stopPropagation();">
                    <i class="bi ${hasReductionTarget ? 'bi-exclamation-triangle-fill' : 'bi-bullseye'}"></i>
                </button>
            </td>
        </tr>
        `;

        // メンバー行（子行）- 初期状態は非表示
        if (hasMembers && group.members) {
            group.members.forEach(member => {
                const isTarget = member.is_reduction_target || member.is_task_reduction_target;
                const memberUnitSuffix = member.unit_suffix || 'h';
                html += `
                <tr class="member-row" data-parent-group="${groupId}" style="display: none; background-color: #f9fafb;">
                    <td></td>
                    <td class="ps-4">
                        <i class="bi bi-arrow-return-right text-muted me-1"></i>
                        ${escapeHtml(member.work_name)}
                        ${isTarget ? '<span class="badge bg-danger ms-1">削減対象</span>' : ''}
                    </td>
                    <td></td>
                    <td></td>
                    <td class="text-end text-muted">${member.hours}${memberUnitSuffix}</td>
                    <td class="text-end text-muted">¥${member.cost.toLocaleString()}</td>
                    <td></td>
                    <td></td>
                </tr>
                `;
            });
        }
    });

    tbody.innerHTML = html;

    // グループ行の展開/折りたたみ（操作ボタン以外をクリックした時）
    document.querySelectorAll('.group-row').forEach(row => {
        row.addEventListener('click', function(e) {
            // 操作ボタンのセルをクリックした場合は展開しない
            if (e.target.closest('.action-cell') || e.target.closest('.bulk-reduction-btn')) {
                return;
            }
            const groupId = this.dataset.groupId;
            toggleGroupExpand(groupId);
        });
    });

    // バルク削減対象ボタンにイベントリスナーを追加
    document.querySelectorAll('.bulk-reduction-btn').forEach(btn => {
        btn.addEventListener('click', handleBulkToggleReduction);
    });
}

function toggleGroupExpand(groupId) {
    const memberRows = document.querySelectorAll(`.member-row[data-parent-group="${groupId}"]`);
    const toggleIcon = document.querySelector(`.group-toggle[data-group-id="${groupId}"]`);

    if (memberRows.length === 0) return;

    const isExpanded = memberRows[0].style.display !== 'none';

    memberRows.forEach(row => {
        row.style.display = isExpanded ? 'none' : '';
    });

    if (toggleIcon) {
        toggleIcon.classList.toggle('bi-chevron-right', isExpanded);
        toggleIcon.classList.toggle('bi-chevron-down', !isExpanded);
    }
}

function toggleRankingMode(groupMode) {
    isGroupMode = groupMode;
    refreshData();
}

async function handleToggleReduction(event) {
    const btn = event.currentTarget;
    const workName = btn.getAttribute('data-work-name');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    try {
        const response = await fetch('/api/task/toggle-reduction-target', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ work_name: workName })
        });

        if (response.ok) {
            // データを再読み込み
            refreshData();
        } else {
            alert('削減対象の切り替えに失敗しました');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-bullseye"></i>';
        }
    } catch (e) {
        console.error('Toggle reduction target error:', e);
        alert('エラーが発生しました');
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-bullseye"></i>';
    }
}

async function handleBulkToggleReduction(event) {
    const btn = event.currentTarget;
    const workNamesJson = btn.getAttribute('data-work-names');
    const isCurrentlyTarget = btn.getAttribute('data-is-target') === 'true';

    let workNames;
    try {
        workNames = JSON.parse(workNamesJson);
    } catch (e) {
        console.error('Failed to parse work names:', e);
        return;
    }

    // 現在削減対象なら解除、そうでなければ設定
    const setAsTarget = !isCurrentlyTarget;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    try {
        const response = await fetch('/api/task/bulk-toggle-reduction-target', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                work_names: workNames,
                set_as_target: setAsTarget
            })
        });

        if (response.ok) {
            const result = await response.json();
            console.log(`${result.updated_count}件を${setAsTarget ? '削減対象に設定' : '削減対象から解除'}しました`);
            // データを再読み込み
            refreshData();
        } else {
            alert('削減対象の一括切り替えに失敗しました');
            btn.disabled = false;
            btn.innerHTML = `<i class="bi ${isCurrentlyTarget ? 'bi-exclamation-triangle-fill' : 'bi-bullseye'}"></i>`;
        }
    } catch (e) {
        console.error('Bulk toggle reduction target error:', e);
        alert('エラーが発生しました');
        btn.disabled = false;
        btn.innerHTML = `<i class="bi ${isCurrentlyTarget ? 'bi-exclamation-triangle-fill' : 'bi-bullseye'}"></i>`;
    }
}

async function loadTrendChart(qs) {
    try {
        const response = await fetch(`/api/analytics/weekly-trend?${qs}`);
        const data = await response.json();

        const ctx = document.getElementById('trendChart').getContext('2d');

        if (trendChart) {
            trendChart.destroy();
        }

        // 目標ラインの設定
        let goalAnnotation = null;
        if (data.goal && data.goal.target_hours) {
            goalAnnotation = {
                type: 'line',
                yMin: data.goal.target_hours,
                yMax: data.goal.target_hours,
                borderColor: '#dc2626',
                borderWidth: 2,
                borderDash: [5, 5],
                label: {
                    display: true,
                    content: `目標: ${data.goal.target_hours}h`,
                    position: 'end',
                    backgroundColor: '#dc2626',
                    color: '#fff',
                    font: { size: 10 }
                }
            };
            // 目標インジケーターを表示
            document.getElementById('goalIndicator').style.display = 'block';
            document.getElementById('goalPercent').textContent = data.goal.target_percent;
        } else {
            document.getElementById('goalIndicator').style.display = 'none';
        }

        trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: data.datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 15
                        }
                    },
                    annotation: goalAnnotation ? {
                        annotations: {
                            goalLine: goalAnnotation
                        }
                    } : {}
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: '時間(h)'
                        }
                    }
                }
            }
        });
    } catch (e) {
        console.error('Failed to load trend chart:', e);
    }
}

async function loadAlerts(qs) {
    try {
        const response = await fetch(`/api/analytics/alerts?${qs}`);
        const data = await response.json();

        const section = document.getElementById('alertsSection');

        if (!data.alerts || data.alerts.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';
        section.innerHTML = data.alerts.map(alert => {
            let bgClass, iconClass, textClass;
            switch (alert.level) {
                case 'critical':
                    bgClass = 'alert-danger';
                    iconClass = 'bi-exclamation-octagon-fill';
                    textClass = 'text-danger';
                    break;
                case 'warning':
                    bgClass = 'alert-warning';
                    iconClass = 'bi-exclamation-triangle-fill';
                    textClass = 'text-warning';
                    break;
                case 'success':
                    bgClass = 'alert-success';
                    iconClass = 'bi-check-circle-fill';
                    textClass = 'text-success';
                    break;
                default:
                    bgClass = 'alert-info';
                    iconClass = 'bi-info-circle-fill';
                    textClass = 'text-info';
            }

            let details = '';
            if (alert.type === 'week_over_week') {
                details = `<small class="ms-2 text-muted">(${alert.previous_value}h → ${alert.current_value}h)</small>`;
            } else if (alert.type === 'threshold_exceeded') {
                details = `<small class="ms-2 text-muted">(閾値: ${alert.threshold}%)</small>`;
            } else if (alert.type === 'goal_progress') {
                details = `<small class="ms-2 text-muted">(達成率: ${alert.progress_percent}%)</small>`;
            }

            return `
                <div class="alert ${bgClass} d-flex align-items-center py-2 mb-2" role="alert">
                    <i class="bi ${iconClass} ${textClass} me-2"></i>
                    <span>${alert.message}</span>
                    ${details}
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load alerts:', e);
        document.getElementById('alertsSection').style.display = 'none';
    }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeHtmlAttr(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
