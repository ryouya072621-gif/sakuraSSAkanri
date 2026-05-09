from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required
from app.models import WorkRecord

bp = Blueprint('main', __name__)


@bp.route('/')
@login_required
def index():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return redirect(url_for('main.dashboard'))


@bp.route('/dashboard')
@login_required
def dashboard():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return render_template('dashboard.html')


@bp.route('/staff-comparison')
@login_required
def staff_comparison():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return render_template('staff_comparison.html')


@bp.route('/project-analysis')
@login_required
def project_analysis():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return render_template('project_analysis.html')


@bp.route('/department-overview')
@login_required
def department_overview():
    return redirect(url_for('main.dashboard'))


@bp.route('/staff-evaluation')
@login_required
def staff_evaluation():
    record_count = WorkRecord.query.count()
    if record_count == 0:
        return redirect(url_for('upload.index'))
    return render_template('staff_evaluation.html')
