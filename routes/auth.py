
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import check_password_hash

from models.user import User

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Redirect an already authenticated user.
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "warning")
            return render_template("auth/login.html")

        user = User.query.filter_by(email=email).first()

        if (
            user
            and user.active
            and check_password_hash(user.password_hash, password)
        ):
            login_user(user)
            flash("Welcome back to VSTV6!", "success")

            next_page = request.args.get("next")

            # Only allow safe local relative redirects.
            if (
                next_page
                and next_page.startswith("/")
                and not next_page.startswith("//")
                and "\\" not in next_page
            ):
                return redirect(next_page)

            return redirect(url_for("admin.dashboard"))

        flash("Invalid email or password, or your account is inactive.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.login"))
