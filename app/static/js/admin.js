// カテゴリ管理
let categoryModal = null;

function loadCategories() {
    fetch('/admin/api/categories')
        .then(response => response.json())
        .then(data => {
            renderCategoriesTable(data.categories);
        });
}

function renderCategoriesTable(categories) {
    const tbody = document.getElementById('categoriesTable');
    if (!categories || categories.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">カテゴリがありません</td></tr>';
        return;
    }

    tbody.innerHTML = categories.map((cat, index) => `
        <tr data-id="${cat.id}">
            <td>
                <div class="btn-group-vertical btn-group-sm">
                    <button class="btn btn-outline-secondary btn-sm py-0" onclick="moveCategory(${cat.id}, 'up')" ${index === 0 ? 'disabled' : ''}>
                        <i class="bi bi-chevron-up"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-sm py-0" onclick="moveCategory(${cat.id}, 'down')" ${index === categories.length - 1 ? 'disabled' : ''}>
                        <i class="bi bi-chevron-down"></i>
                    </button>
                </div>
            </td>
            <td><strong>${escapeHtml(cat.name)}</strong></td>
            <td>
                <div class="d-flex align-items-center">
                    <div style="width: 24px; height: 24px; background-color: ${cat.color}; border-radius: 4px; border: 1px solid #ddd;"></div>
                    <code class="ms-2 small">${cat.color}</code>
                </div>
            </td>
            <td>
                <span class="category-badge" style="background-color: ${cat.badge_bg_color}; color: ${cat.badge_text_color};">
                    ${escapeHtml(cat.name)}
                </span>
            </td>
            <td>
                ${cat.is_reduction_target
                    ? '<span class="badge bg-danger">削減対象</span>'
                    : '<span class="text-muted">-</span>'}
            </td>
            <td>
                <span class="badge bg-secondary">${cat.keyword_count}件</span>
            </td>
            <td>
                <button class="btn btn-outline-primary btn-sm me-1" onclick="editCategory(${cat.id})">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" onclick="deleteCategory(${cat.id}, '${escapeHtml(cat.name)}')">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

function showAddModal() {
    document.getElementById('modalTitle').textContent = 'カテゴリ追加';
    document.getElementById('categoryId').value = '';
    document.getElementById('categoryName').value = '';
    document.getElementById('categoryColor').value = '#6B7280';
    document.getElementById('categoryColorText').value = '#6B7280';
    document.getElementById('badgeBgColor').value = '#f3f4f6';
    document.getElementById('badgeBgColorText').value = '#f3f4f6';
    document.getElementById('badgeTextColor').value = '#374151';
    document.getElementById('badgeTextColorText').value = '#374151';
    document.getElementById('isReductionTarget').checked = false;
    updateBadgePreview();

    if (!categoryModal) {
        categoryModal = new bootstrap.Modal(document.getElementById('categoryModal'));
    }
    categoryModal.show();
}

function editCategory(id) {
    fetch(`/admin/api/categories`)
        .then(response => response.json())
        .then(data => {
            const cat = data.categories.find(c => c.id === id);
            if (!cat) return;

            document.getElementById('modalTitle').textContent = 'カテゴリ編集';
            document.getElementById('categoryId').value = cat.id;
            document.getElementById('categoryName').value = cat.name;
            document.getElementById('categoryColor').value = cat.color;
            document.getElementById('categoryColorText').value = cat.color;
            document.getElementById('badgeBgColor').value = cat.badge_bg_color;
            document.getElementById('badgeBgColorText').value = cat.badge_bg_color;
            document.getElementById('badgeTextColor').value = cat.badge_text_color;
            document.getElementById('badgeTextColorText').value = cat.badge_text_color;
            document.getElementById('isReductionTarget').checked = cat.is_reduction_target;
            updateBadgePreview();

            if (!categoryModal) {
                categoryModal = new bootstrap.Modal(document.getElementById('categoryModal'));
            }
            categoryModal.show();
        });
}

function saveCategory() {
    const id = document.getElementById('categoryId').value;
    const data = {
        name: document.getElementById('categoryName').value,
        color: document.getElementById('categoryColorText').value,
        badge_bg_color: document.getElementById('badgeBgColorText').value,
        badge_text_color: document.getElementById('badgeTextColorText').value,
        is_reduction_target: document.getElementById('isReductionTarget').checked
    };

    const url = id ? `/admin/api/categories/${id}` : '/admin/api/categories';
    const method = id ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            categoryModal.hide();
            loadCategories();
        } else {
            alert(result.error || '保存に失敗しました');
        }
    });
}

function deleteCategory(id, name) {
    if (!confirm(`カテゴリ「${name}」を削除しますか？`)) return;

    fetch(`/admin/api/categories/${id}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                loadCategories();
            } else {
                alert(result.error || '削除に失敗しました');
            }
        });
}

function moveCategory(id, direction) {
    fetch('/admin/api/categories')
        .then(response => response.json())
        .then(data => {
            const categories = data.categories;
            const index = categories.findIndex(c => c.id === id);
            if (index === -1) return;

            const newIndex = direction === 'up' ? index - 1 : index + 1;
            if (newIndex < 0 || newIndex >= categories.length) return;

            // 入れ替え
            [categories[index], categories[newIndex]] = [categories[newIndex], categories[index]];

            // 順序を保存
            const order = categories.map(c => c.id);
            fetch('/admin/api/categories/order', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order })
            })
            .then(() => loadCategories());
        });
}

function setupColorPickers() {
    // グラフ色
    document.getElementById('categoryColor').addEventListener('input', function() {
        document.getElementById('categoryColorText').value = this.value;
    });
    document.getElementById('categoryColorText').addEventListener('input', function() {
        if (/^#[0-9A-Fa-f]{6}$/.test(this.value)) {
            document.getElementById('categoryColor').value = this.value;
        }
    });

    // バッジ背景色
    document.getElementById('badgeBgColor').addEventListener('input', function() {
        document.getElementById('badgeBgColorText').value = this.value;
        updateBadgePreview();
    });
    document.getElementById('badgeBgColorText').addEventListener('input', function() {
        if (/^#[0-9A-Fa-f]{6}$/.test(this.value)) {
            document.getElementById('badgeBgColor').value = this.value;
            updateBadgePreview();
        }
    });

    // バッジ文字色
    document.getElementById('badgeTextColor').addEventListener('input', function() {
        document.getElementById('badgeTextColorText').value = this.value;
        updateBadgePreview();
    });
    document.getElementById('badgeTextColorText').addEventListener('input', function() {
        if (/^#[0-9A-Fa-f]{6}$/.test(this.value)) {
            document.getElementById('badgeTextColor').value = this.value;
            updateBadgePreview();
        }
    });
}

function updateBadgePreview() {
    const preview = document.getElementById('badgePreview');
    const name = document.getElementById('categoryName').value || 'サンプル';
    preview.textContent = name;
    preview.style.backgroundColor = document.getElementById('badgeBgColorText').value;
    preview.style.color = document.getElementById('badgeTextColorText').value;
}


// キーワード管理
let keywordModal = null;

function loadKeywords() {
    const categoryId = document.getElementById('filterCategory')?.value || '';
    const activeOnly = document.getElementById('filterActive')?.checked ?? true;

    let url = '/admin/api/keywords?';
    if (categoryId) url += `category_id=${categoryId}&`;
    if (activeOnly) url += 'active_only=true';

    fetch(url)
        .then(response => response.json())
        .then(data => {
            renderKeywordsTable(data.keywords);
        });
}

function renderKeywordsTable(keywords) {
    const tbody = document.getElementById('keywordsTable');
    if (!keywords || keywords.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">キーワードがありません</td></tr>';
        return;
    }

    const matchTypeLabels = {
        'contains': '含む',
        'exact': '完全一致',
        'startswith': '前方一致'
    };

    tbody.innerHTML = keywords.map(kw => `
        <tr>
            <td><code>${escapeHtml(kw.keyword)}</code></td>
            <td><span class="badge bg-primary">${escapeHtml(kw.display_category_name)}</span></td>
            <td>${matchTypeLabels[kw.match_type] || kw.match_type}</td>
            <td><span class="badge bg-secondary">${kw.priority}</span></td>
            <td>
                ${kw.is_active
                    ? '<i class="bi bi-check-circle text-success"></i>'
                    : '<i class="bi bi-x-circle text-muted"></i>'}
            </td>
            <td>
                <button class="btn btn-outline-primary btn-sm me-1" onclick="editKeyword(${kw.id})">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" onclick="deleteKeyword(${kw.id}, '${escapeHtml(kw.keyword)}')">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

function showAddKeywordModal() {
    document.getElementById('keywordModalTitle').textContent = 'ルール追加';
    document.getElementById('keywordId').value = '';
    document.getElementById('keywordText').value = '';
    document.getElementById('matchType').value = 'contains';
    document.getElementById('keywordCategory').selectedIndex = 0;
    document.getElementById('keywordPriority').value = '10';
    document.getElementById('keywordActive').checked = true;

    if (!keywordModal) {
        keywordModal = new bootstrap.Modal(document.getElementById('keywordModal'));
    }
    keywordModal.show();
}

function editKeyword(id) {
    fetch('/admin/api/keywords')
        .then(response => response.json())
        .then(data => {
            const kw = data.keywords.find(k => k.id === id);
            if (!kw) return;

            document.getElementById('keywordModalTitle').textContent = 'ルール編集';
            document.getElementById('keywordId').value = kw.id;
            document.getElementById('keywordText').value = kw.keyword;
            document.getElementById('matchType').value = kw.match_type;
            document.getElementById('keywordCategory').value = kw.display_category_id;
            document.getElementById('keywordPriority').value = kw.priority;
            document.getElementById('keywordActive').checked = kw.is_active;

            if (!keywordModal) {
                keywordModal = new bootstrap.Modal(document.getElementById('keywordModal'));
            }
            keywordModal.show();
        });
}

function saveKeyword() {
    const id = document.getElementById('keywordId').value;
    const data = {
        keyword: document.getElementById('keywordText').value,
        display_category_id: parseInt(document.getElementById('keywordCategory').value),
        match_type: document.getElementById('matchType').value,
        priority: parseInt(document.getElementById('keywordPriority').value),
        is_active: document.getElementById('keywordActive').checked
    };

    const url = id ? `/admin/api/keywords/${id}` : '/admin/api/keywords';
    const method = id ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            keywordModal.hide();
            loadKeywords();
        } else {
            alert(result.error || '保存に失敗しました');
        }
    });
}

function deleteKeyword(id, keyword) {
    if (!confirm(`キーワード「${keyword}」を削除しますか？`)) return;

    fetch(`/admin/api/keywords/${id}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                loadKeywords();
            } else {
                alert(result.error || '削除に失敗しました');
            }
        });
}


// 設定管理
function loadSettings() {
    fetch('/admin/api/settings')
        .then(response => response.json())
        .then(data => {
            const settings = data.settings;
            if (settings.default_hourly_rate) {
                document.getElementById('default_hourly_rate').value = settings.default_hourly_rate.value;
            }
            if (settings.ranking_limit) {
                document.getElementById('ranking_limit').value = settings.ranking_limit.value;
            }
            if (settings.default_category) {
                document.getElementById('default_category').value = settings.default_category.value;
            }
        });
}

function saveSettings() {
    const data = {
        default_hourly_rate: document.getElementById('default_hourly_rate').value,
        ranking_limit: document.getElementById('ranking_limit').value,
        default_category: document.getElementById('default_category').value
    };

    fetch('/admin/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            alert('設定を保存しました');
        } else {
            alert('保存に失敗しました');
        }
    });
}


// 自動提案機能
let suggestionsModal = null;
let currentSuggestions = [];

function showSuggestionsModal() {
    if (!suggestionsModal) {
        suggestionsModal = new bootstrap.Modal(document.getElementById('suggestionsModal'));
    }

    document.getElementById('suggestionsLoading').style.display = 'block';
    document.getElementById('suggestionsContent').style.display = 'none';

    suggestionsModal.show();

    fetch('/admin/api/suggest-keywords')
        .then(response => response.json())
        .then(data => {
            currentSuggestions = data.suggestions;
            renderSuggestions(data.suggestions, data.categories);
            document.getElementById('suggestionsLoading').style.display = 'none';
            document.getElementById('suggestionsContent').style.display = 'block';
        })
        .catch(err => {
            console.error(err);
            document.getElementById('suggestionsLoading').innerHTML = '<div class="alert alert-danger">読み込みに失敗しました</div>';
        });
}

function renderSuggestions(suggestions, categories) {
    if (!suggestions || suggestions.length === 0) {
        document.getElementById('suggestionsEmpty').style.display = 'block';
        document.getElementById('suggestionsList').style.display = 'none';
        document.getElementById('applySuggestionsBtn').disabled = true;
        return;
    }

    document.getElementById('suggestionsEmpty').style.display = 'none';
    document.getElementById('suggestionsList').style.display = 'block';

    const tbody = document.getElementById('suggestionsTable');
    tbody.innerHTML = suggestions.map((s, idx) => `
        <tr>
            <td>
                <input type="checkbox" class="form-check-input suggestion-checkbox"
                    data-index="${idx}" onchange="updateApplyButton()">
            </td>
            <td><code>${escapeHtml(s.keyword)}</code></td>
            <td>
                <select class="form-select form-select-sm suggestion-category" data-index="${idx}">
                    ${categories.map(c => `<option value="${escapeHtml(c.name)}" ${c.name === s.suggested_category ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}
                </select>
            </td>
            <td><span class="badge bg-info">${s.match_count.toLocaleString()}件</span></td>
        </tr>
    `).join('');

    updateApplyButton();
}

function toggleAllSuggestions() {
    const selectAll = document.getElementById('selectAllSuggestions').checked;
    document.querySelectorAll('.suggestion-checkbox').forEach(cb => {
        cb.checked = selectAll;
    });
    updateApplyButton();
}

function updateApplyButton() {
    const checked = document.querySelectorAll('.suggestion-checkbox:checked').length;
    const btn = document.getElementById('applySuggestionsBtn');
    btn.disabled = checked === 0;
    btn.textContent = checked > 0 ? `選択した${checked}件のキーワードを登録` : '選択したキーワードを登録';
}

function applySuggestions() {
    const keywords = [];
    document.querySelectorAll('.suggestion-checkbox:checked').forEach(cb => {
        const idx = parseInt(cb.dataset.index);
        const categorySelect = document.querySelector(`.suggestion-category[data-index="${idx}"]`);
        keywords.push({
            keyword: currentSuggestions[idx].keyword,
            category: categorySelect.value
        });
    });

    if (keywords.length === 0) return;

    fetch('/admin/api/apply-suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keywords })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            alert(`${result.added_count}件のキーワードを登録しました`);
            suggestionsModal.hide();
            loadKeywords();
        } else {
            alert('登録に失敗しました');
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
