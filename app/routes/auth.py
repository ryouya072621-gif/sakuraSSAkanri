from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash('IDまたはパスワードが間違っています', 'danger')

    return render_template('login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
