// 業務倍増シミュレーター
let simData = null;
let simChart = null;

// 部門比較が読み込まれた後にシミュレーター用の部門セレクトを設定
document.addEventListener('DOMContentLoaded', function() {
    // 少し待ってから部門データを使ってセレクトボックスを更新
    setTimeout(initSimulator, 500);
});

function initSimulator() {
    // 部門セレクトを埋める（department-overview.jsのcurrentDeptDataを利用）
    const select = document.getElementById('simDepartment');
    if (typeof currentDeptData !== 'undefined' && currentDeptData.length > 0) {
        currentDeptData.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.department;
            opt.textContent = d.department;
            select.appendChild(opt);
        });
    }
    loadSimulation();
}

function loadSimulation() {
    const dept = document.getElementById('simDepartment').value;
    let url = '/api/analytics/capacity-simulation?';
    if (dept) url += `category1=${encodeURIComponent(dept)}&`;

    const start = document.getElementById('startDate').value;
    const end = document.getElementById('endDate').value;
    if (start) url += `start=${start}&`;
    if (end) url += `end=${end}&`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            simData = data;
            updateSimulation();
        })
        .catch(err => console.error('Simulation load error:', err));
}

function updateSimulation() {
    if (!simData) return;

    const cRate = parseInt(document.getElementById('simCSlider').value) / 100;
    const bRate = parseInt(document.getElementById('simBSlider').value) / 100;
    const aRate = parseInt(document.getElementById('simASlider').value) / 100;

    // ラベル更新
    document.getElementById('simCLabel').textContent = Math.round(cRate * 100) + '%';
    document.getElementById('simBLabel').textContent = Math.round(bRate * 100) + '%';
    document.getElementById('simALabel').textContent = Math.round(aRate * 100) + '%';

    const totals = simData.rank_totals;
    const sHours = totals.S || 0;
    const aHours = totals.A || 0;
    const bHours = totals.B || 0;
    const cHours = totals.C || 0;
    const totalHours = simData.total_hours;

    // 削減量を計算
    const freedFromC = cHours * cRate;
    const freedFromB = bHours * bRate;
    const freedFromA = aHours * aRate;
    const totalFreed = freedFromC + freedFromB + freedFromA;

    // 残りの業務時間
    const remaining = totalHours - totalFreed;

    // 目標: 業務量2倍 = 現在のS時間を2倍にできるだけの余力が必要
    // 目標余力 = 現在の総時間（同じ時間枠で2倍の高価値業務をするため、非高価値を全削減が理想）
    const targetFree = totalHours - sHours; // S以外を全部削減するのが100%
    const progressPct = targetFree > 0 ? Math.min((totalFreed / targetFree) * 100, 100) : 0;

    document.getElementById('simFreedHours').textContent = totalFreed.toFixed(1) + 'h';

    const progressBar = document.getElementById('simProgressBar');
    progressBar.style.width = progressPct.toFixed(0) + '%';
    progressBar.style.background = progressPct >= 80 ? '#16a34a' : progressPct >= 50 ? '#ca8a04' : '#6366f1';
    document.getElementById('simProgressLabel').textContent = progressPct.toFixed(0) + '%';

    // ウォーターフォールチャートを描画
    renderWaterfall(sHours, aHours, bHours, cHours, freedFromA, freedFromB, freedFromC, totalFreed);
}

function renderWaterfall(sH, aH, bH, cH, fA, fB, fC, totalFreed) {
    const ctx = document.getElementById('simWaterfallChart').getContext('2d');
    if (simChart) simChart.destroy();

    // ウォーターフォール風の積み上げ棒グラフ
    const labels = ['現在の業務', '削減後', '生まれる余力'];
    const datasets = [
        {
            label: 'S: 高価値',
            data: [sH, sH, 0],
            backgroundColor: '#16a34a'
        },
        {
            label: 'A: 中価値',
            data: [aH, aH - fA, 0],
            backgroundColor: '#2563eb'
        },
        {
            label: 'B: 低価値',
            data: [bH, bH - fB, 0],
            backgroundColor: '#ca8a04'
        },
        {
            label: 'C: 無駄',
            data: [cH, cH - fC, 0],
            backgroundColor: '#dc2626'
        },
        {
            label: '余力（新規業務に使える）',
            data: [0, 0, totalFreed],
            backgroundColor: '#8b5cf6'
        }
    ];

    simChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.raw > 0 ? `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}h` : null
                    }
                }
            },
            scales: {
                x: {},
                y: {
                    stacked: true,
                    title: { display: true, text: '時間 (h)' }
                }
            }
        }
    });
}
