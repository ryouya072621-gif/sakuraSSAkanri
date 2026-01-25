import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from openpyxl import load_workbook
from app import db
from app.models import WorkRecord

bp = Blueprint('upload', __name__, url_prefix='/upload')


@bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('ファイルが選択されていません', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('ファイルが選択されていません', 'error')
            return redirect(request.url)

        if not file.filename.endswith('.xlsx'):
            flash('Excelファイル(.xlsx)を選択してください', 'error')
            return redirect(request.url)

        try:
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            count = process_excel(filepath)
            os.remove(filepath)
            flash(f'{count}件のデータを取り込みました', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            flash(f'エラーが発生しました: {str(e)}', 'error')
            return redirect(request.url)

    record_count = WorkRecord.query.count()
    return render_template('upload.html', record_count=record_count)


def process_excel(filepath):
    """Excelファイルを処理してDBに登録"""
    wb = load_workbook(filepath, read_only=True, data_only=True)
    total_count = 0

    # 既存データを削除
    WorkRecord.query.delete()
    db.session.commit()

    # 月次シートを処理（SSA〇月請求）
    for sheet_name in wb.sheetnames:
        if '月請求' not in sheet_name:
            continue

        ws = wb[sheet_name]
        rows = list(ws.iter_rows(min_row=2, values_only=True))

        batch = []
        for row in rows:
            if not row[0]:  # 請求日が空なら終了
                continue

            work_date = row[0]
            if isinstance(work_date, datetime):
                work_date = work_date.date()
            elif isinstance(work_date, str):
                try:
                    work_date = datetime.strptime(work_date, '%Y-%m-%d').date()
                except ValueError:
                    continue

            record = WorkRecord(
                work_date=work_date,
                staff_name=str(row[1]) if row[1] else '',
                department=str(row[2]) if row[2] else '',
                category1=str(row[3]) if row[3] else '',
                category2=str(row[4]) if row[4] else '',
                work_name=str(row[5]) if row[5] else '',
                unit_price=int(row[6]) if row[6] else 0,
                quantity=int(row[7]) if row[7] else 0,
                total_amount=int(row[8]) if row[8] else 0,
                status=str(row[9]) if row[9] else '',
                source_month=sheet_name
            )
            batch.append(record)

            if len(batch) >= 1000:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                total_count += len(batch)
                batch = []

        if batch:
            db.session.bulk_save_objects(batch)
            db.session.commit()
            total_count += len(batch)

    wb.close()
    return total_count


@bp.route('/clear', methods=['POST'])
def clear_data():
    """データをクリア"""
    WorkRecord.query.delete()
    db.session.commit()
    flash('データをクリアしました', 'success')
    return redirect(url_for('upload.index'))
