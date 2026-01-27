/**
 * AI Features JavaScript
 * - インサイト生成
 * - チャット機能
 * - レポート生成
 */

// ============================================
// AI インサイト
// ============================================

async function loadAIInsights() {
    const params = getParams();
    const qs = buildQueryString(params);

    const content = document.getElementById('aiInsightsContent');
    if (!content) return;

    content.innerHTML = `
        <div class="text-center py-3 text-muted">
            <div class="spinner-border spinner-border-sm me-2"></div>
            AIが分析中...
        </div>
    `;

    try {
        const response = await fetch(`/api/ai/insights?${qs}`);

        if (!response.ok) {
            throw new Error('AI service unavailable');
        }

        const data = await response.json();

        if (data.error) {
            content.innerHTML = `
                <div class="text-muted small">
                    <i class="bi bi-exclamation-circle me-1"></i>${data.error}
                </div>
            `;
            return;
        }

        let html = '';

        // ハイライト
        if (data.highlights && data.highlights.length > 0) {
            html += `
                <div class="mb-3">
                    <h6 class="text-primary mb-2"><i class="bi bi-star me-1"></i>ハイライト</h6>
                    <ul class="mb-0 ps-3">
                        ${data.highlights.map(h => `<li class="small">${escapeHtml(h)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // 懸念事項
        if (data.concerns && data.concerns.length > 0) {
            html += `
                <div class="mb-3">
                    <h6 class="text-warning mb-2"><i class="bi bi-exclamation-triangle me-1"></i>注意点</h6>
                    <ul class="mb-0 ps-3">
                        ${data.concerns.map(c => `<li class="small">${escapeHtml(c)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // 提案
        if (data.recommendations && data.recommendations.length > 0) {
            html += `
                <div class="mb-2">
                    <h6 class="text-success mb-2"><i class="bi bi-lightbulb me-1"></i>提案</h6>
                    <ul class="mb-0 ps-3">
                        ${data.recommendations.map(r => `<li class="small">${escapeHtml(r)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        if (!html) {
            html = '<div class="text-muted small">インサイトを生成できませんでした</div>';
        }

        // キャッシュ表示
        if (data.cached) {
            html += `<div class="text-muted small mt-2"><i class="bi bi-clock-history me-1"></i>キャッシュから取得</div>`;
        }

        content.innerHTML = html;

    } catch (e) {
        console.error('AI insights error:', e);
        content.innerHTML = `
            <div class="text-muted small">
                <i class="bi bi-exclamation-circle me-1"></i>
                AI機能を利用するには環境変数の設定が必要です
                <br><a href="#" onclick="loadAIInsights(); return false;" class="small">再試行</a>
            </div>
        `;
    }
}

function refreshAIInsights() {
    loadAIInsights();
}


// ============================================
// AI チャット
// ============================================

let chatHistory = [];
let chatVisible = false;

function toggleChat() {
    const widget = document.getElementById('chatWidget');
    if (!widget) return;

    chatVisible = !chatVisible;
    widget.style.display = chatVisible ? 'flex' : 'none';

    if (chatVisible && chatHistory.length === 0) {
        // 初回表示時にウェルカムメッセージ
        appendChatMessage('assistant', 'こんにちは！業務データについて質問があればお気軽にどうぞ。例: 「今週一番時間を使った業務は？」');
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chatInput');
    if (!input) return;

    const question = input.value.trim();
    if (!question) return;

    input.value = '';
    input.disabled = true;

    // ユーザーメッセージを追加
    appendChatMessage('user', question);

    // ローディング表示
    const loadingId = appendChatMessage('assistant', '<div class="spinner-border spinner-border-sm"></div> 考え中...', true);

    try {
        const response = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                history: chatHistory.slice(-10),
                filters: getParams()
            })
        });

        const data = await response.json();

        // ローディングを削除
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();

        if (data.error) {
            appendChatMessage('assistant', data.answer || 'エラーが発生しました。しばらくしてから再度お試しください。');
        } else {
            appendChatMessage('assistant', data.answer);

            // 履歴に追加
            chatHistory.push({ user: question, assistant: data.answer });
        }

    } catch (e) {
        console.error('Chat error:', e);
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();
        appendChatMessage('assistant', 'エラーが発生しました。AI機能の設定を確認してください。');
    }

    input.disabled = false;
    input.focus();
}

function appendChatMessage(role, content, isTemp = false) {
    const container = document.getElementById('chatMessages');
    if (!container) return null;

    const id = 'msg-' + Date.now();
    const isUser = role === 'user';

    const div = document.createElement('div');
    div.id = id;
    div.className = `d-flex ${isUser ? 'justify-content-end' : 'justify-content-start'} mb-2`;
    div.innerHTML = `
        <div class="px-3 py-2 rounded-3 ${isUser ? 'bg-primary text-white' : 'bg-light'}" style="max-width: 85%;">
            <div class="small">${isTemp ? content : escapeHtml(content).replace(/\n/g, '<br>')}</div>
        </div>
    `;

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;

    return id;
}

function handleChatKeypress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
}


// ============================================
// AI レポート生成
// ============================================

async function generateAIReport(type = 'weekly') {
    const btn = event.target.closest('button');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 生成中...';

    try {
        const response = await fetch('/api/ai/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: type,
                filters: getParams()
            })
        });

        const data = await response.json();

        if (data.error) {
            alert('レポート生成に失敗しました: ' + data.error);
        } else {
            showReportModal(data.report, type);
        }

    } catch (e) {
        console.error('Report generation error:', e);
        alert('レポート生成中にエラーが発生しました');
    }

    btn.disabled = false;
    btn.innerHTML = originalText;
}

function showReportModal(content, type) {
    // モーダルがなければ作成
    let modal = document.getElementById('reportModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'reportModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg modal-dialog-scrollable">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="bi bi-file-text me-2"></i>AI生成レポート</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <pre id="reportContent" class="bg-light p-3 rounded" style="white-space: pre-wrap; font-family: inherit;"></pre>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-outline-secondary" onclick="copyReport()">
                            <i class="bi bi-clipboard me-1"></i>コピー
                        </button>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">閉じる</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById('reportContent').textContent = content;

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

function copyReport() {
    const content = document.getElementById('reportContent');
    if (content) {
        navigator.clipboard.writeText(content.textContent).then(() => {
            alert('レポートをクリップボードにコピーしました');
        });
    }
}


// ============================================
// 初期化
// ============================================

// DOMContentLoaded後に実行
document.addEventListener('DOMContentLoaded', function() {
    // Enterキーでチャット送信
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.addEventListener('keypress', handleChatKeypress);
    }
});
