
import re
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
)
from flask_login import login_required, current_user

from extensions import db
from models import Article, Category
from models.contact_message import ContactMessage

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
logger = logging.getLogger(__name__)


def _require_admin():
    """Allow only authenticated administrators to manage sensitive actions."""
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)


def _make_slug(value):
    """Create a URL-friendly slug from the English title."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:220].strip("-") or "news"


def _unique_slug(value, article_id=None):
    """Return a unique slug without overwriting another article's slug."""
    base = _make_slug(value)
    candidate = base
    number = 2

    while True:
        query = Article.query.filter_by(slug=candidate)

        if article_id is not None:
            query = query.filter(Article.id != article_id)

        if query.first() is None:
            return candidate

        suffix = f"-{number}"
        candidate = f"{base[:240 - len(suffix)]}{suffix}"
        number += 1


def _valid_url(value, https_only=False):
    """Allow empty optional URLs; validate supplied URLs."""
    if not value:
        return True

    try:
        parsed = urlparse(value)
        allowed_schemes = ("https",) if https_only else ("http", "https")

        return (
            parsed.scheme in allowed_schemes
            and bool(parsed.hostname)
            and not any(char.isspace() for char in value)
        )
    except ValueError:
        return False


def _article_form(article=None):
    categories = Category.query.order_by(Category.name_en.asc()).all()

    return render_template(
        "admin/article_form.html",
        article=article,
        categories=categories,
    )


def _save_article(article):
    """Validate and save the article form. New articles remain drafts."""
    title_en = request.form.get("title_en", "").strip()
    title_te = request.form.get("title_te", "").strip()
    summary_en = request.form.get("summary_en", "").strip()
    summary_te = request.form.get("summary_te", "").strip()
    body_en = request.form.get("body_en", "").strip()
    body_te = request.form.get("body_te", "").strip()
    language = request.form.get("language", "both").strip()
    slug_input = request.form.get("slug", "").strip()
    source_name = request.form.get("source_name", "").strip()
    source_url = request.form.get("source_url", "").strip()
    image_url = request.form.get("image_url", "").strip()
    category_value = request.form.get("category_id", "").strip()

    if not title_en or not summary_en or not body_en:
        flash("English title, summary, and body are required.", "danger")
        return False

    if len(title_en) > 220 or len(title_te) > 220:
        flash("Titles must not exceed 220 characters.", "danger")
        return False

    if len(summary_en) > 500 or len(summary_te) > 500:
        flash("Summaries must not exceed 500 characters.", "danger")
        return False

    if language not in {"en", "te", "both"}:
        flash("Select a valid article language.", "danger")
        return False

    if not _valid_url(source_url):
        flash("Source URL must be a valid HTTP or HTTPS URL.", "danger")
        return False

    if not _valid_url(image_url, https_only=True):
        flash("Image URL must be a valid HTTPS URL.", "danger")
        return False

    try:
        category_id = int(category_value)
    except (TypeError, ValueError):
        flash("Please select a valid category.", "danger")
        return False

    category = db.session.get(Category, category_id)
    if category is None:
        flash("The selected category does not exist.", "danger")
        return False

    article.title_en = title_en
    article.title_te = title_te or None
    article.summary_en = summary_en
    article.summary_te = summary_te or None
    article.body_en = body_en
    article.body_te = body_te or None
    article.language = language
    article.category_id = category.id
    article.source_name = source_name or None
    article.source_url = source_url or None
    article.image_url = image_url or None

    requested_slug = slug_input or title_en
    article.slug = _unique_slug(requested_slug, article_id=article.id)

    if article.id is None:
        article.author_id = current_user.id
        article.status = "draft"

    db.session.add(article)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Could not save article.")
        flash("Could not save the article. Check the server log.", "danger")
        return False

    return True


# -------------------- ADMIN DASHBOARD --------------------

@admin_bp.route("/")
@login_required
def dashboard():
    counts = {
        "all": Article.query.count(),
        "draft": Article.query.filter_by(status="draft").count(),
        "published": Article.query.filter_by(status="published").count(),
    }

    articles = Article.query.order_by(Article.id.desc()).limit(8).all()
    category_count = Category.query.count()
    unread_messages = ContactMessage.query.filter_by(is_read=False).count()

    return render_template(
        "admin/dashboard.html",
        counts=counts,
        articles=articles,
        category_count=category_count,
        unread_messages=unread_messages,
    )


# -------------------- CONTACT MESSAGES --------------------

@admin_bp.route("/messages")
@login_required
def contact_messages():
    _require_admin()

    messages = ContactMessage.query.order_by(
        ContactMessage.created_at.desc()
    ).all()

    unread_count = ContactMessage.query.filter_by(is_read=False).count()

    return render_template(
        "admin/contact_messages.html",
        messages=messages,
        unread_count=unread_count,
    )


@admin_bp.route("/messages/<int:message_id>/read", methods=["POST"])
@login_required
def mark_message_read(message_id):
    _require_admin()

    message = db.session.get(ContactMessage, message_id)
    if message is None:
        abort(404)

    message.is_read = True

    try:
        db.session.commit()
        flash("Message marked as read.", "success")
    except Exception:
        db.session.rollback()
        logger.exception("Could not mark contact message as read.")
        flash("Could not update the message.", "danger")

    return redirect(url_for("admin.contact_messages"))


# -------------------- ARTICLE MANAGEMENT --------------------

@admin_bp.route("/articles")
@login_required
def articles():
    status = request.args.get("status", "").strip()
    query = Article.query

    if status in {"draft", "published"}:
        query = query.filter_by(status=status)

    article_list = query.order_by(Article.id.desc()).all()

    return render_template(
        "admin/articles.html",
        articles=article_list,
        selected_status=status,
    )


@admin_bp.route("/articles/new", methods=["GET", "POST"])
@login_required
def new_article():
    if request.method == "POST":
        article = Article()

        if _save_article(article):
            flash("Article saved as a draft.", "success")
            return redirect(url_for("admin.articles", status="draft"))

        return _article_form(article=article)

    return _article_form()


@admin_bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
@login_required
def edit_article(article_id):
    article = db.get_or_404(Article, article_id)

    if request.method == "POST" and _save_article(article):
        flash("Article updated successfully.", "success")
        return redirect(url_for("admin.articles"))

    return _article_form(article=article)


@admin_bp.route("/articles/<int:article_id>/publish", methods=["POST"])
@login_required
def publish_article(article_id):
    _require_admin()

    article = db.get_or_404(Article, article_id)

    if article.status != "published":
        article.status = "published"
        article.published_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
            flash("Article published successfully.", "success")
        except Exception:
            db.session.rollback()
            logger.exception("Could not publish article.")
            flash("Could not publish the article.", "danger")

    return redirect(url_for("admin.articles"))


@admin_bp.route("/articles/<int:article_id>/unpublish", methods=["POST"])
@login_required
def unpublish_article(article_id):
    _require_admin()

    article = db.get_or_404(Article, article_id)
    article.status = "draft"
    article.published_at = None

    try:
        db.session.commit()
        flash("Article moved back to drafts.", "success")
    except Exception:
        db.session.rollback()
        logger.exception("Could not unpublish article.")
        flash("Could not unpublish the article.", "danger")

    return redirect(url_for("admin.articles"))


@admin_bp.route("/articles/<int:article_id>/delete", methods=["POST"])
@login_required
def delete_article(article_id):
    _require_admin()

    article = db.get_or_404(Article, article_id)

    try:
        db.session.delete(article)
        db.session.commit()
        flash("Article deleted successfully.", "success")
    except Exception:
        db.session.rollback()
        logger.exception("Could not delete article.")
        flash("Could not delete the article.", "danger")

    return redirect(url_for("admin.articles"))
