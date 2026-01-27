/**
 * アップロードプレビュー画面のJavaScript
 * ハイブリッドAI処理: ローカル正規表現 + AIカテゴリ分類
 */

// バッチ処理の設定
const BATCH_SIZE = 500;
let cancelRequested = false;

// AI分類を実行（ハイブリッド処理）
async function runAICategorization() {
    const btn = document.getElementById('aiCategorizeBtn');
    const cancelBtn = document.getElementById('cancelCategorizeBtn');
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    const progressBar = document.getElementById('progressBar');
    const progressContainer = document.getElementById('progressContainer');

    btn.disabled = true;
    cancelRequested = false;
    overlay.style.display = 'flex';

    if (cancelBtn) cancelBtn.style.display = 'inline-block';
    if (progressContainer) progressContainer.style.display = 'block';

    // テーブルからアイテムを収集
    const rows = document.querySelectorAll('#previewTable tr');
    const items = [];

    rows.forEach((row, index) => {
        const comboKey = row.dataset.comboKey;
        if (comboKey) {
            const parts = comboKey.split('|');
            items.push({
                index: index,
                category1: parts[0] || '',
                category2: parts[1] || '',
                work_name: parts[2] || ''
            });
        }
    });

    if (items.length === 0) {
        alert('分類するアイテムがありません');
        resetUI();
        return;
    }

    const uniqueWorkNames = [...new Set(items.map(item => item.work_name))].filter(n => n);

    try {
        // ========================================
        // Step 1: ローカルグルーピング（高速・APIなし）
        // ========================================
        loadingText.textContent = `Step 1/2: タスクグルーピング中... (${uniqueWorkNames.length.toLocaleString()}件)`;
        progressBar.style.width = '10%';
        progressBar.textContent = '10%';

        const groupResponse = await fetch('/api/ai/categorize/group-tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ work_names: uniqueWorkNames, use_ai: false })
        });

        const groupingResult = await groupResponse.json();

        if (groupingResult.error) {
            throw new Error(groupingResult.error);
        }

        if (cancelRequested) {
            alert('AI分類がキャンセルされました');
            resetUI();
            return;
        }

        console.log(`ローカルグルーピング: ${groupingResult.original_count}件 → ${groupingResult.grouped_count}グループ`);

        // グループマッピングを作成
        const memberToRepresentative = {};
        groupingResult.groups.forEach(group => {
            group.members.forEach(member => {
                memberToRepresentative[member] = group.representative;
            });
        });

        // ========================================
        // Step 2: AIカテゴリ分類（グループ代表のみ）
        // ========================================
        loadingText.textContent = `Step 2/2: カテゴリ分類中... (${groupingResult.grouped_count}グループ)`;
        progressBar.style.width = '30%';
        progressBar.textContent = '30%';

        // グループ代表のアイテムを作成
        const representativeItems = groupingResult.groups.map(group => {
            const originalItem = items.find(item => item.work_name === group.representative);
            return {
                category1: originalItem?.category1 || '',
                category2: originalItem?.category2 || '',
                work_name: group.representative
            };
        });

        // カテゴリ分類をバッチで実行
        const categorySuggestions = await categorizeInBatches(representativeItems, loadingText, progressBar);

        if (cancelRequested) {
            alert('AI分類がキャンセルされました');
            resetUI();
            return;
        }

        // ========================================
        // Step 3: 結果をすべての行に適用
        // ========================================
        loadingText.textContent = '結果を適用中...';
        progressBar.style.width = '90%';
        progressBar.textContent = '90%';

        // 代表名 → カテゴリ提案のマップ
        const representativeToCategory = {};
        categorySuggestions.forEach((suggestion, index) => {
            const rep = representativeItems[index]?.work_name;
            if (rep) representativeToCategory[rep] = suggestion;
        });

        // 全アイテムに結果を適用
        const allSuggestions = [];
        items.forEach((item, index) => {
            const representative = memberToRepresentative[item.work_name] || item.work_name;
            const categorySuggestion = representativeToCategory[representative];

            if (categorySuggestion) {
                allSuggestions.push({
                    item_index: index,
                    suggested_category_id: categorySuggestion.suggested_category_id,
                    confidence: categorySuggestion.confidence,
                    reasoning: categorySuggestion.reasoning +
                        (representative !== item.work_name ? ` (グループ: ${representative})` : '')
                });
            }
        });

        applySuggestions(allSuggestions, false);

        progressBar.style.width = '100%';
        progressBar.textContent = '100%';

        const successMessage = `AI分類が完了しました!\n` +
            `• ${groupingResult.original_count.toLocaleString()}件 → ${groupingResult.grouped_count.toLocaleString()}グループに統合\n` +
            `• ${allSuggestions.length.toLocaleString()}件にカテゴリを適用`;

        showToast(successMessage, 'success');
        console.log(successMessage);

    } catch (error) {
        console.error('AI categorization error:', error);
        alert('AI分類中にエラーが発生しました: ' + error.message);
    } finally {
        resetUI();
    }
}

// カテゴリ分類をバッチで実行
async function categorizeInBatches(items, loadingText, progressBar) {
    const totalBatches = Math.ceil(items.length / BATCH_SIZE);
    let allSuggestions = [];

    for (let i = 0; i < totalBatches; i++) {
        if (cancelRequested) return [];

        const progressPercent = 30 + Math.round(((i + 1) / totalBatches) * 60);
        if (loadingText) {
            loadingText.textContent = `Step 2/2: カテゴリ分類中... ${i + 1}/${totalBatches} バッチ`;
        }
        if (progressBar) {
            progressBar.style.width = `${progressPercent}%`;
            progressBar.textContent = `${progressPercent}%`;
        }

        const batchItems = items.slice(i * BATCH_SIZE, (i + 1) * BATCH_SIZE);

        const response = await fetch('/api/ai/categorize/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: batchItems })
        });

        const data = await response.json();

        if (data.error && !data.fallback) {
            throw new Error(data.error);
        }

        data.suggestions.forEach(suggestion => {
            suggestion.item_index += i * BATCH_SIZE;
        });

        allSuggestions = allSuggestions.concat(data.suggestions);

        if (i < totalBatches - 1) {
            await sleep(300);
        }
    }

    return allSuggestions;
}

// UI状態をリセット
function resetUI() {
    const btn = document.getElementById('aiCategorizeBtn');
    const cancelBtn = document.getElementById('cancelCategorizeBtn');
    const overlay = document.getElementById('loadingOverlay');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');

    btn.disabled = false;
    overlay.style.display = 'none';

    if (cancelBtn) cancelBtn.style.display = 'none';
    if (progressContainer) progressContainer.style.display = 'none';
    if (progressBar) {
        progressBar.style.width = '0%';
        progressBar.textContent = '';
    }
}

// キャンセル処理
function cancelCategorization() {
    cancelRequested = true;
}

// スリープ関数
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// トースト通知を表示
function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.ai-toast');
    if (existingToast) existingToast.remove();

    const toast = document.createElement('div');
    toast.className = `ai-toast alert alert-${type === 'success' ? 'success' : 'info'} alert-dismissible fade show`;
    toast.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000; min-width: 350px; white-space: pre-line;';
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    document.body.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) toast.remove();
    }, 8000);
}

// AI提案をテーブルに反映
function applySuggestions(suggestions, isFallback) {
    const rows = document.querySelectorAll('#previewTable tr');

    suggestions.forEach(suggestion => {
        const row = rows[suggestion.item_index];
        if (!row) return;

        const select = row.querySelector('.category-select');
        const confidenceCell = row.querySelector('.confidence-cell');

        if (suggestion.suggested_category_id) {
            select.value = suggestion.suggested_category_id;
        }

        const confidence = Math.round(suggestion.confidence * 100);
        let badgeClass = 'bg-success';
        let rowClass = 'confidence-high';

        if (confidence < 50) {
            badgeClass = 'bg-danger';
            rowClass = 'confidence-low';
        } else if (confidence < 70) {
            badgeClass = 'bg-warning';
            rowClass = 'confidence-medium';
        }

        confidenceCell.innerHTML = `<span class="badge ${badgeClass}">${confidence}%</span>`;

        row.classList.remove('confidence-high', 'confidence-medium', 'confidence-low');
        row.classList.add(rowClass);
        row.dataset.confidence = confidence;

        if (suggestion.reasoning) {
            select.title = suggestion.reasoning;
        }
    });
}

// 行をフィルタリング
function filterRows(filter) {
    const rows = document.querySelectorAll('#previewTable tr');

    rows.forEach(row => {
        const confidence = parseInt(row.dataset.confidence) || 100;

        if (filter === 'all') {
            row.style.display = '';
        } else if (filter === 'low') {
            row.style.display = confidence < 70 ? '' : 'none';
        }
    });
}

// アップロードを確定
async function confirmUpload() {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');

    overlay.style.display = 'flex';
    loadingText.textContent = 'データを保存中...';

    const rows = document.querySelectorAll('#previewTable tr');
    const approvedCategories = {};

    rows.forEach(row => {
        const comboKey = row.dataset.comboKey;
        const select = row.querySelector('.category-select');
        if (comboKey && select && select.value) {
            approvedCategories[comboKey] = select.value;
        }
    });

    try {
        const response = await fetch('/upload/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(approvedCategories)
        });

        const data = await response.json();

        if (data.success) {
            window.location.href = '/';
        } else {
            alert('保存中にエラーが発生しました: ' + (data.error || '不明なエラー'));
        }
    } catch (error) {
        console.error('Confirm error:', error);
        alert('保存中にエラーが発生しました');
    } finally {
        overlay.style.display = 'none';
    }
}

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', function() {
    // 自動的にAI分類を実行（オプション）
    // runAICategorization();
});
