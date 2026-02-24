// 部門比較ダッシュボード
let deptBarChart = null;
let detailPieChart = null;
let detailReductionChart = null;
let detailStaffChart = null;
let currentDeptData = [];

let goalRankingChart = null;
let goalTrendChart = null;
let goalData = null;

document.addEventListener('DOMContentLoaded', function() {
    loadData();
    loadGoalData();
});

function getDateParams() {
    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    let params = '';
    if (start) params += `&start=${start}`;
    if (end) params += `&end=${end}`;
    return params;
}

function loadData() {
    fetch(`/api/analytics/department-comparison?${getDateParams()}`)
        .then(r => r.json())
        .then(data => {
            currentDeptData = data.departments;
            renderKPIs(data.departments);
            renderBarChart(data.departments, data.rank_colors);
            renderRanking(data.departments);
            renderDeptCards(data.departments);
        })
        .catch(err => console.error('Failed to load department data:', err));
}

function renderKPIs(depts) {
    document.getElementById('kpiDeptCount').textContent = depts.length;

    if (depts.length === 0) return;

    const totalHours = depts.reduce((s, d) => s + d.total_hours, 0);
    const totalS = depts.reduce((s, d) => s + d.rank_hours.S, 0);
    const totalBC = depts.reduce((s, d) => s + d.rank_hours.B + d.rank_hours.C, 0);

    document.getElementById('kpiHighValueRatio').textContent =
        totalHours > 0 ? (totalS / totalHours * 100).toFixed(1) + '%' : '0%';
    document.getElementById('kpiWasteRatio').textContent =
        totalHours > 0 ? (totalBC / totalHours * 100).toFixed(1) + '%' : '0%';
    document.getElementById('kpiBestDept').textContent = depts[0].department;
}

function renderBarChart(depts, colors) {
    const ctx = document.getElementById('deptBarChart').getContext('2d');
    if (deptBarChart) deptBarChart.destroy();

    const labels = depts.map(d => d.department);
    const datasets = [
        { label: 'S: 高価値', data: depts.map(d => d.rank_hours.S), backgroundColor: colors.S },
        { label: 'A: 中価値', data: depts.map(d => d.rank_hours.A), backgroundColor: colors.A },
        { label: 'B: 低価値', data: depts.map(d => d.rank_hours.B), backgroundColor: colors.B },
        { label: 'C: 無駄',   data: depts.map(d => d.rank_hours.C), backgroundColor: colors.C },
    ];

    deptBarChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}h`
                    }
                }
            },
            scales: {
                x: { stacked: true, title: { display: true, text: '時間 (h)' } },
                y: { stacked: true }
            },
            onClick: (evt, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    selectDepartment(depts[idx].department);
                }
            }
        }
    });
}

function renderRanking(depts) {
    const container = document.getElementById('deptRanking');
    if (depts.length === 0) {
        container.innerHTML = '<p class="text-muted text-center">データなし</p>';
        return;
    }

    container.innerHTML = depts.map((d, i) => {
        const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`;
        const scoreColor = d.efficiency_score >= 0 ? 'text-success' : 'text-danger';
        return `
            <div class="d-flex justify-content-between align-items-center py-2 ${i < depts.length - 1 ? 'border-bottom' : ''}"
                 style="cursor:pointer" onclick="selectDepartment('${escapeAttr(d.department)}')">
                <div>
                    <span class="me-2">${medal}</span>
                    <strong>${escapeHtml(d.department)}</strong>
                    <small class="text-muted ms-2">${d.total_hours.toFixed(0)}h / ${d.staff_count}名</small>
                </div>
                <span class="fw-bold ${scoreColor}">${d.efficiency_score.toFixed(1)}</span>
            </div>
        `;
    }).join('');
}

function renderDeptCards(depts) {
    const container = document.getElementById('deptCards');
    if (depts.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-muted text-center">データなし</p></div>';
        return;
    }

    container.innerHTML = depts.map(d => {
        const total = d.total_hours || 1;
        const sPct = (d.rank_hours.S / total * 100).toFixed(0);
        const aPct = (d.rank_hours.A / total * 100).toFixed(0);
        const bPct = (d.rank_hours.B / total * 100).toFixed(0);
        const cPct = (d.rank_hours.C / total * 100).toFixed(0);

        return `
        <div class="col-md-4 col-lg-3">
            <div class="card dept-card h-100" id="card-${escapeAttr(d.department)}"
                 onclick="selectDepartment('${escapeAttr(d.department)}')">
                <div class="card-body">
                    <h6 class="card-title mb-2">${escapeHtml(d.department)}</h6>
                    <div class="d-flex justify-content-between mb-2">
                        <small class="text-muted">${d.total_hours.toFixed(0)}h</small>
                        <small class="text-muted">${d.staff_count}名</small>
                    </div>
                    <div class="progress mb-2" style="height: 12px;">
                        <div class="progress-bar" style="width:${sPct}%;background:#16a34a" title="S:${sPct}%"></div>
                        <div class="progress-bar" style="width:${aPct}%;background:#2563eb" title="A:${aPct}%"></div>
                        <div class="progress-bar" style="width:${bPct}%;background:#ca8a04" title="B:${bPct}%"></div>
                        <div class="progress-bar" style="width:${cPct}%;background:#dc2626" title="C:${cPct}%"></div>
                    </div>
                    <div class="d-flex justify-content-between">
                        <small class="rank-S fw-bold">S: ${sPct}%</small>
                        <small class="rank-C fw-bold">C: ${cPct}%</small>
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');
}

function selectDepartment(dept) {
    // カードのアクティブ状態を更新
    document.querySelectorAll('.dept-card').forEach(c => c.classList.remove('active'));
    const card = document.getElementById(`card-${dept}`);
    if (card) card.classList.add('active');

    document.getElementById('detailSection').style.display = 'block';
    document.getElementById('detailDeptName').textContent = dept;

    fetch(`/api/analytics/department-detail?department=${encodeURIComponent(dept)}${getDateParams()}`)
        .then(r => r.json())
        .then(data => {
            renderDetailPie(data);
            renderReductionChart(data.reduction_candidates);
            renderStaffChart(data.staff_comparison, data.rank_colors);
        })
        .catch(err => console.error('Failed to load detail:', err));

    // 詳細セクションにスクロール
    document.getElementById('detailSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeDetail() {
    document.getElementById('detailSection').style.display = 'none';
    document.querySelectorAll('.dept-card').forEach(c => c.classList.remove('active'));
}

function renderDetailPie(data) {
    const ctx = document.getElementById('detailPieChart').getContext('2d');
    if (detailPieChart) detailPieChart.destroy();

    const ranks = ['S', 'A', 'B', 'C'];
    const labels = ['S: 高価値', 'A: 中価値', 'B: 低価値', 'C: 無駄'];
    const colors = [data.rank_colors.S, data.rank_colors.A, data.rank_colors.B, data.rank_colors.C];
    const values = ranks.map(r => data.rank_hours[r] || 0);

    detailPieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? (ctx.raw / total * 100).toFixed(1) : 0;
                            return `${ctx.label}: ${ctx.raw.toFixed(1)}h (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderReductionChart(candidates) {
    const ctx = document.getElementById('detailReductionChart').getContext('2d');
    if (detailReductionChart) detailReductionChart.destroy();

    if (!candidates || candidates.length === 0) {
        detailReductionChart = new Chart(ctx, {
            type: 'bar',
            data: { labels: ['データなし'], datasets: [{ data: [0] }] },
            options: { responsive: true }
        });
        return;
    }

    const labels = candidates.map(c => c.work_name.length > 20 ? c.work_name.slice(0, 20) + '...' : c.work_name);
    const values = candidates.map(c => c.hours);
    const bgColors = candidates.map(c => c.rank === 'C' ? '#dc2626' : '#ca8a04');

    detailReductionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: '削減可能時間 (h)',
                data: values,
                backgroundColor: bgColors,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => candidates[items[0].dataIndex].work_name,
                        label: ctx => `${ctx.raw.toFixed(1)}h（${candidates[ctx.dataIndex].rank}ランク）`
                    }
                }
            },
            scales: {
                x: { title: { display: true, text: '時間 (h)' } }
            }
        }
    });
}

function renderStaffChart(staffData, colors) {
    const ctx = document.getElementById('detailStaffChart').getContext('2d');
    if (detailStaffChart) detailStaffChart.destroy();

    if (!staffData || staffData.length === 0) {
        detailStaffChart = new Chart(ctx, {
            type: 'bar',
            data: { labels: ['データなし'], datasets: [{ data: [0] }] },
            options: { responsive: true }
        });
        return;
    }

    const labels = staffData.map(s => s.name);
    const datasets = [
        { label: 'S: 高価値', data: staffData.map(s => s.rank_hours.S), backgroundColor: colors.S },
        { label: 'A: 中価値', data: staffData.map(s => s.rank_hours.A), backgroundColor: colors.A },
        { label: 'B: 低価値', data: staffData.map(s => s.rank_hours.B), backgroundColor: colors.B },
        { label: 'C: 無駄',   data: staffData.map(s => s.rank_hours.C), backgroundColor: colors.C },
    ];

    detailStaffChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}h`
                    }
                }
            },
            scales: {
                x: { stacked: true, title: { display: true, text: '時間 (h)' } },
                y: { stacked: true }
            }
        }
    });
}

// ユーティリティ
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
// 月次目標進捗
// ============================================

function loadGoalData() {
    const monthSelect = document.getElementById('goalMonth');
    const month = monthSelect ? monthSelect.value : '';
    const qs = month ? `?year_month=${month}` : '';

    fetch(`/api/analytics/monthly-goals${qs}`)
        .then(r => r.json())
        .then(data => {
            goalData = data;
            const section = document.getElementById('goalSection');
            if (!section) return;

            // データがあれば表示
            if (Object.keys(data.departments).length > 0) {
                section.style.display = 'block';

                // 月セレクタを設定
                if (monthSelect && data.months && data.months.length > 0) {
                    const currentVal = monthSelect.value;
                    monthSelect.innerHTML = '<option value="">最新月</option>' +
                        data.months.map(m => `<option value="${m}" ${m === currentVal ? 'selected' : ''}>${formatYearMonth(m)}</option>`).join('');
                }

                renderGoalRanking(data.departments);
                renderGoalTrend(data.trend);
            }
        })
        .catch(err => console.error('Failed to load goal data:', err));
}

function formatYearMonth(ym) {
    if (!ym || ym.length !== 4) return ym;
    return `20${ym.substring(0, 2)}年${parseInt(ym.substring(2))}月`;
}

function renderGoalRanking(depts) {
    const ctx = document.getElementById('goalRankingChart');
    if (!ctx) return;

    if (goalRankingChart) goalRankingChart.destroy();

    const entries = Object.entries(depts)
        .map(([name, data]) => ({ name, avg: data.avg_progress || 0 }))
        .sort((a, b) => b.avg - a.avg);

    const labels = entries.map(e => e.name.length > 15 ? e.name.slice(0, 15) + '...' : e.name);
    const values = entries.map(e => e.avg);
    const colors = values.map(v => v >= 80 ? '#16a34a' : v >= 50 ? '#2563eb' : v >= 30 ? '#ca8a04' : '#dc2626');

    goalRankingChart = new Chart(ctx.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: '平均目標達成率 (%)',
                data: values,
                backgroundColor: colors,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => entries[items[0].dataIndex].name,
                        label: ctx => `達成率: ${ctx.raw}%`
                    }
                }
            },
            scales: {
                x: {
                    min: 0, max: 100,
                    title: { display: true, text: '達成率 (%)' }
                }
            },
            onClick: (evt, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    showGoalDetail(entries[idx].name);
                }
            }
        }
    });
}

function renderGoalTrend(trend) {
    const ctx = document.getElementById('goalTrendChart');
    if (!ctx) return;

    if (goalTrendChart) goalTrendChart.destroy();

    const months = Object.keys(trend).sort();
    const values = months.map(m => trend[m]);

    goalTrendChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            labels: months.map(formatYearMonth),
            datasets: [{
                label: '全部門平均 目標達成率',
                data: values,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 5,
                pointHoverRadius: 8,
                borderWidth: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    callbacks: {
                        label: ctx => `達成率: ${ctx.raw}%`
                    }
                }
            },
            scales: {
                y: {
                    min: 0, max: 100,
                    title: { display: true, text: '達成率 (%)' }
                }
            }
        }
    });
}

function showGoalDetail(deptName) {
    if (!goalData || !goalData.departments[deptName]) return;

    const card = document.getElementById('goalDetailCard');
    const title = document.getElementById('goalDetailTitle');
    const content = document.getElementById('goalDetailContent');
    if (!card || !content) return;

    card.style.display = 'block';
    title.textContent = `${deptName} - 目標詳細`;

    const deptInfo = goalData.departments[deptName];
    const latestMonth = deptInfo.latest_month;
    const goals = deptInfo.months[latestMonth] || [];

    if (goals.length === 0) {
        content.innerHTML = '<div class="col-12 text-muted text-center py-3">目標データがありません</div>';
        return;
    }

    content.innerHTML = goals.map(g => {
        const pct = g.progress_pct || 0;
        const barColor = pct >= 80 ? '#16a34a' : pct >= 50 ? '#2563eb' : pct >= 30 ? '#ca8a04' : '#dc2626';
        return `
            <div class="col-md-6 col-lg-4">
                <div class="card h-100">
                    <div class="card-body">
                        <div class="d-flex justify-content-between mb-2">
                            <strong class="small">目標 ${g.goal_index}</strong>
                            <span class="badge" style="background:${barColor};color:white">${pct}%</span>
                        </div>
                        <p class="small mb-2">${escapeHtml(g.goal_name || '(名称なし)')}</p>
                        <div class="progress" style="height: 8px;">
                            <div class="progress-bar" style="width:${pct}%;background:${barColor}"></div>
                        </div>
                        ${g.details ? `<p class="small text-muted mt-2 mb-0">${escapeHtml(g.details).substring(0, 100)}</p>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
