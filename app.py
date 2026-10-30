
import os
from datetime import datetime, timezone
from getpass import getpass

from flask import Flask, render_template, send_from_directory

from config import Config
from extensions import db, login_manager, csrf, migrate
from routes.contact import contact_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if (
        not app.config["SECRET_KEY"]
        or not app.config["SQLALCHEMY_DATABASE_URI"]
    ):
        raise RuntimeError("Set SECRET_KEY and DATABASE_URL in .env")

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"

    # Import models and blueprints
    from models import User, Article, Category
    from routes.public import public_bp
    from routes.articles import articles_bp
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.seo import seo_bp
    from routes.newspaper import newspaper_bp

    # Register blueprints
    app.register_blueprint(public_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(seo_bp)
    app.register_blueprint(contact_bp)
    app.register_blueprint(newspaper_bp)

    # Google Search Console HTML file verification
    @app.route("/google8e97696e2dc05713.html")
    def google_site_verification():
        return send_from_directory(
            app.root_path,
            "google8e97696e2dc05713.html",
            mimetype="text/html",
        )

    # Global template variables
    @app.context_processor
    def globals_for_templates():
        return {"now": datetime.now(timezone.utc)}

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("500.html"), 500

    # Create a new admin account only if no admin exists
    @app.cli.command("create-admin")
    def create_admin():
        if User.query.filter_by(role="admin").first():
            print("An admin already exists.")
            return

        email = input("Admin email: ").strip().lower()
        password = getpass("Password (12+ characters): ")

        if len(password) < 12 or "@" not in email:
            print(
                "Use a valid email and a password of at least "
                "12 characters."
            )
            return

        user = User(
            email=email,
            display_name="Administrator",
            role="admin",
        )
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
            print("Admin created successfully.")
        except Exception:
            db.session.rollback()
            print("Admin creation failed. Check the application logs.")

    # Reset the password of an existing admin account
    @app.cli.command("reset-admin-password")
    def reset_admin_password():
        email = input("Existing admin email: ").strip().lower()

        admin = User.query.filter_by(
            email=email,
            role="admin",
        ).first()

        if not admin:
            print("No admin account found for that email.")
            return

        password = getpass("New password (minimum 12 characters): ")
        confirm = getpass("Confirm new password: ")

        if len(password) < 12:
            print("Password must contain at least 12 characters.")
            return

        if password != confirm:
            print("Passwords do not match.")
            return

        try:
            admin.set_password(password)
            db.session.commit()
            print("Admin password updated successfully.")
        except Exception:
            db.session.rollback()
            print("Password update failed. Check the application logs.")

    # Seed article categories
    @app.cli.command("seed-categories")
    def seed_categories():
        from seed_categories import seed

        seed()

    # Collect RSS articles as drafts
    @app.cli.command("collect-rss")
    def collect_rss():
        from services.news_collector import collect_feeds

        print(f"New draft articles: {collect_feeds(app)}")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
