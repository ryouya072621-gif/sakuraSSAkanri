let categoryChart = null;
let dailyChart = null;
let dateRange = { min: null, max: null };
let categoryColors = {};
let badgeStyles = {};

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
        loadRanking(qs)
    ]);
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
    const response = await fetch(`/api/ranking?${qs}`);
    const data = await response.json();

    const tbody = document.getElementById('rankingTable');

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">データがありません</td></tr>';
        return;
    }

    tbody.innerHTML = data.map(item => {
        const style = badgeStyles[item.category] || { bg: '#f3f4f6', text: '#374151' };
        const badgeStyle = `background-color: ${style.bg}; color: ${style.text};`;
        const progressColor = item.is_reduction_target ? '#dc2626' : (categoryColors[item.category] || '#3b82f6');

        return `
        <tr>
            <td>${escapeHtml(item.work_name)}</td>
            <td><span class="category-badge" style="${badgeStyle}">${item.category}</span></td>
            <td class="text-end">${item.hours}h</td>
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
        </tr>
    `}).join('');
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
