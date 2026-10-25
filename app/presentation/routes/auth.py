from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app, abort
from flask_login import current_user, login_user, logout_user
from app.data.models import User
from sqlalchemy.exc import IntegrityError
from app.data.extensions import db
from app.presentation.authz import admin_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.business.password_reset_email import send_reset_email

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


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _make_reset_token(user):
    return _reset_serializer().dumps(
        {"user_id": user.id, "email": user.email},
        salt="password-reset-v1",
    )


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email, is_active=True).first()

        # Same public response for known/unknown emails.
        if user is not None:
            token = _make_reset_token(user)
            reset_url = url_for(
                "auth.reset_password",
                token=token,
                _external=True,
            )

            try:
                send_reset_email(user.email, reset_url)
            except Exception:
                current_app.logger.exception("Could not send reset email")

        flash(
            "If an active account uses that email, a reset link will be sent.",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        data = _reset_serializer().loads(
            token,
            salt="password-reset-v1",
            max_age=1800,
        )
    except (BadSignature, SignatureExpired):
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    user = db.session.get(User, data.get("user_id"))

    if (
        user is None
        or not user.is_active
        or not user.email
        or user.email != data.get("email")
    ):
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html"), 400

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html"), 400

        user.set_password(password)
        db.session.commit()

        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")


@auth_bp.route("/users/create", methods=["GET", "POST"])
@admin_required
def create_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff").strip().lower()
        email = request.form.get("email", "").strip().lower() or None

        if email and User.query.filter_by(email=email).first():
            flash("That email is already in use.", "error")
            return render_template("create_user.html"), 409

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

        user = User(username=username, role=role, email=email)
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
        email = request.form.get("email", "").strip().lower() or None

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

        duplicate_email = User.query.filter(
            User.email == email,
            User.id != user.id,
        ).first() if email else None

        if duplicate_email:
            flash("That email is already in use.", "error")
            return render_template("edit_user.html", user=user), 409

        user.username = username
        user.role = role
        user.email = email

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