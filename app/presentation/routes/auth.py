from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_user, logout_user
from app.data.models import User
from sqlalchemy.exc import IntegrityError
from app.data.extensions import db
from app.presentation.authz import admin_required

auth_bp = Blueprint("auth", __name__)
ALLOWED_ROLES = {"admin", "staff"}

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user is not None and user.check_password(password):
            login_user(user)
            return redirect(url_for("main.home"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/users/create", methods=["GET", "POST"])
@admin_required
def create_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff").strip().lower()

        if role not in ALLOWED_ROLES:
            flash("Choose a valid role.", "error")
            return render_template("create_user.html"), 400

        if not username:
            flash("Username is required.", "error")
            return render_template("create_user.html"), 400

        if len(username) > 80:
            flash("Username must be 80 characters or fewer.", "error")
            return render_template("create_user.html"), 400

        if not password:
            flash("Password is required.", "error")
            return render_template("create_user.html"), 400

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("create_user.html"), 400

        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
            return render_template("create_user.html"), 409

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That username is already taken.", "error")
            return render_template("create_user.html"), 409
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to create user account")
            flash("The account could not be created. Please try again.", "error")
            return render_template("create_user.html"), 500

        flash("User account created successfully.", "success")
        return redirect(url_for("auth.create_user"))

    return render_template("create_user.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("main.home"))