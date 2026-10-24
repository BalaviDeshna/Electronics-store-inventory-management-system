from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app, abort
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

        if (
            user is not None
            and user.is_active
            and user.check_password(password)
        ):
            login_user(user)
            return redirect(url_for("main.home"))

        flash("Invalid username or password, or account deactivated.", "error")

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

@auth_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template("users.html", users=users)


@auth_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)

    if user is None:
        abort(404)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "").strip().lower()

        if not username or len(username) > 80:
            flash("Enter a username of 1–80 characters.", "error")
            return render_template("edit_user.html", user=user), 400

        if role not in ALLOWED_ROLES:
            flash("Choose a valid role.", "error")
            return render_template("edit_user.html", user=user), 400

        duplicate = User.query.filter(
            User.username == username,
            User.id != user.id,
        ).first()

        if duplicate:
            flash("That username is already taken.", "error")
            return render_template("edit_user.html", user=user), 409

        user.username = username
        user.role = role

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That username is already taken.", "error")
            return render_template("edit_user.html", user=user), 409

        flash("User updated successfully.", "success")
        return redirect(url_for("auth.list_users"))

    return render_template("edit_user.html", user=user)


@auth_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@admin_required
def deactivate_user(user_id):
    user = db.session.get(User, user_id)

    if user is None:
        abort(404)

    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("auth.list_users"))

    user.is_active = False
    db.session.commit()

    flash("User deactivated.", "success")
    return redirect(url_for("auth.list_users"))


@auth_bp.route("/users/<int:user_id>/reactivate", methods=["POST"])
@admin_required
def reactivate_user(user_id):
    user = db.session.get(User, user_id)

    if user is None:
        abort(404)

    user.is_active = True
    db.session.commit()

    flash("User reactivated.", "success")
    return redirect(url_for("auth.list_users"))