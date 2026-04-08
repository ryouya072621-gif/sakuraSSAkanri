"""
SSA スクレイパー ルート
管理画面からスクレイピングを手動実行したり、取得データを確認するAPI
"""
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request, render_template_string
from app import db
from app.models import SSADailyRecord

bp = Blueprint("scraper", __name__, url_prefix="/admin/ssa")


# ─────────────────────────────────────────────
# 管理画面 HTML
# ─────────────────────────────────────────────

SCRAPER_PAGE = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>SSA 自動取得</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body { padding: 2rem; background: #f8f9fa; }
    .card { margin-bottom: 1.5rem; }
    #log { font-family: monospace; font-size: 0.85rem; background: #212529; color: #adb5bd;
           padding: 1rem; border-radius: 6px; height: 200px; overflow-y: auto; }
  </style>
</head>
<body>
  <h2>SSA 売上データ 自動取得</h2>

  <div class="card">
    <div class="card-body">
      <h5 class="card-title">手動取得</h5>
      <div class="row g-2 align-items-end">
        <div class="col-auto">
          <label class="form-label">対象日</label>
          <input type="date" id="targetDate" class="form-control" value="{{ yesterday }}">
        </div>
        <div class="col-auto">
          <button class="btn btn-primary" onclick="runScrape()">取得実行</button>
          <button class="btn btn-outline-secondary ms-2" onclick="loadRecent()">最新データ確認</button>
        </div>
      </div>
      <div id="log" class="mt-3">待機中...</div>
    </div>
  </div>

  <div class="card">
    <div class="card-body">
      <h5 class="card-title">取得済みデータ <span id="recordCount" class="badge bg-secondary">-</span></h5>
      <div class="table-responsive">
        <table class="table table-sm table-hover" id="dataTable">
          <thead class="table-dark">
            <tr>
              <th>日付</th><th>スタッフ名</th><th>目標(千円)</th>
              <th>受領累計</th><th>確認中残</th><th>当月予測</th><th>前月</th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    function log(msg) {
      const el = document.getElementById('log');
      const time = new Date().toLocaleTimeString('ja-JP');
      el.textContent += `[${time}] ${msg}\\n`;
      el.scrollTop = el.scrollHeight;
    }

    async function runScrape() {
      const d = document.getElementById('targetDate').value;
      log(`取得開始: ${d}`);
      try {
        const res = await fetch('/admin/ssa/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({date: d})
        });
        const data = await res.json();
        if (data.error) {
          log(`エラー: ${data.error}`);
        } else {
          log(`完了: 取得${data.fetched}件 / DB保存${data.saved}件`);
          loadRecent();
        }
      } catch(e) {
        log(`通信エラー: ${e.message}`);
      }
    }

    async function loadRecent() {
      const res = await fetch('/admin/ssa/records');
      const data = await res.json();
      const tbody = document.getElementById('tableBody');
      tbody.innerHTML = '';
      document.getElementById('recordCount').textContent = data.total;
      for (const r of data.records) {
        tbody.innerHTML += `<tr>
          <td>${r.fetch_date}</td>
          <td>${r.staff_name}</td>
          <td class="text-end">${r.target_amount.toLocaleString()}</td>
          <td class="text-end">${r.received_cumulative.toLocaleString()}</td>
          <td class="text-end">${r.confirmed_remaining.toLocaleString()}</td>
          <td class="text-end">${r.confirmed_prediction.toLocaleString()}</td>
          <td class="text-end">${r.prev_month.toLocaleString()}</td>
        </tr>`;
      }
    }

    loadRecent();
  </script>
</body>
</html>
"""


@bp.route("/", methods=["GET"])
def index():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return render_template_string(SCRAPER_PAGE, yesterday=yesterday)


# ─────────────────────────────────────────────
# API エンドポイント
# ─────────────────────────────────────────────

@bp.route("/run", methods=["POST"])
def run_scrape():
    """スクレイピングを実行してDBに保存する"""
    from app.services.ssa_scraper import scrape_and_save

    data = request.get_json(silent=True) or {}
    target_date = None
    if data.get("date"):
        try:
            target_date = date.fromisoformat(data["date"])
        except ValueError:
            return jsonify({"error": "日付フォーマットが不正です (YYYY-MM-DD)"}), 400

    result = scrape_and_save(target_date)
    status = 500 if result["error"] else 200
    return jsonify(result), status


@bp.route("/records", methods=["GET"])
def get_records():
    """取得済みレコードを返す"""
    year_month = request.args.get("year_month")  # YYYY-MM
    fetch_date = request.args.get("fetch_date")   # YYYY-MM-DD
    limit = int(request.args.get("limit", 200))

    q = SSADailyRecord.query

    if year_month:
        q = q.filter(SSADailyRecord.year_month == year_month)
    if fetch_date:
        try:
            q = q.filter(SSADailyRecord.fetch_date == date.fromisoformat(fetch_date))
        except ValueError:
            pass

    q = q.order_by(SSADailyRecord.fetch_date.desc(), SSADailyRecord.staff_name)
    records = q.limit(limit).all()

    return jsonify({
        "total": q.count(),
        "records": [r.to_dict() for r in records],
    })


@bp.route("/records/summary", methods=["GET"])
def get_summary():
    """月別・スタッフ別サマリーを返す"""
    year_month = request.args.get("year_month", date.today().strftime("%Y-%m"))

    # 当月の最新日付のデータを取得
    latest = (
        db.session.query(db.func.max(SSADailyRecord.fetch_date))
        .filter(SSADailyRecord.year_month == year_month)
        .scalar()
    )
    if not latest:
        return jsonify({"year_month": year_month, "fetch_date": None, "records": []})

    records = (
        SSADailyRecord.query
        .filter(SSADailyRecord.fetch_date == latest)
        .order_by(SSADailyRecord.confirmed_prediction.desc())
        .all()
    )

    return jsonify({
        "year_month": year_month,
        "fetch_date": latest.isoformat(),
        "records": [r.to_dict() for r in records],
    })
