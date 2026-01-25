from flask import Blueprint, render_template, redirect, url_for
from app.models import WorkRecord

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return redirect(url_for('main.dashboard'))


@bp.route('/dashboard')
def dashboard():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return render_template('dashboard.html')
