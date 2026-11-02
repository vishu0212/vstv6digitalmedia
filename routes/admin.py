
import re
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
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
    """Create a URL-friendly slug from an article headline."""
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


def _image_extension(upload):
    """Return a safe image extension only when the file has a known signature."""
    header = upload.stream.read(12)
    upload.stream.seek(0)

    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    return None


def _delete_uploaded_image(image_url):
    """Delete an image only when it is one of this app's uploaded files."""
    prefix = "/uploads/"
    if not image_url or not image_url.startswith(prefix):
        return

    filename = image_url[len(prefix):]
    if not filename or os.path.basename(filename) != filename:
        return

    image_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if os.path.isfile(image_path):
        try:
            os.remove(image_path)
        except OSError:
            logger.exception("Could not remove replaced article image %s.", image_path)


def _save_article(article):
    """Validate and save the article form. New articles remain drafts."""
    title_te = request.form.get("title_te", "").strip()
    summary_te = request.form.get("summary_te", "").strip()
    body_te = request.form.get("body_te", "").strip()
    slug_input = request.form.get("slug", "").strip()
    source_name = request.form.get("source_name", "").strip()
    source_url = request.form.get("source_url", "").strip()
    image_url = request.form.get("image_url", "").strip()
    image_upload = request.files.get("image_file")
    if image_upload and not image_upload.filename:
        image_upload = None
    category_value = request.form.get("category_id", "").strip()

    if not title_te or not summary_te or not body_te:
        flash("Telugu headline, summary, and article body are required.", "danger")
        return False

    if len(title_te) > 220:
        flash("The headline must not exceed 220 characters.", "danger")
        return False

    if len(summary_te) > 500:
        flash("The summary must not exceed 500 characters.", "danger")
        return False

    if not _valid_url(source_url):
        flash("Source URL must be a valid HTTP or HTTPS URL.", "danger")
        return False

    if image_url and not _valid_url(image_url, https_only=True):
        flash("Image URL must be a valid HTTPS URL.", "danger")
        return False

    if image_upload and image_url:
        flash("Choose an image upload or an HTTPS image URL, not both.", "danger")
        return False

    image_extension = _image_extension(image_upload) if image_upload else None
    if image_upload and image_extension is None:
        flash("Upload a valid JPG, PNG, GIF, or WEBP image.", "danger")
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

    previous_image_url = article.image_url
    uploaded_image_path = None
    if image_upload:
        filename = f"{uuid.uuid4().hex}{image_extension}"
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        uploaded_image_path = os.path.join(upload_dir, filename)
        try:
            os.makedirs(upload_dir, exist_ok=True)
            image_upload.save(uploaded_image_path)
        except OSError:
            logger.exception("Could not store uploaded article image.")
            if os.path.isfile(uploaded_image_path):
                try:
                    os.remove(uploaded_image_path)
                except OSError:
                    logger.exception(
                        "Could not remove incomplete article image %s.",
                        uploaded_image_path,
                    )
            flash("Could not save the uploaded image.", "danger")
            return False
        image_url = url_for("uploaded_image", filename=filename)

    article.title_en = None
    article.title_te = title_te or None
    article.summary_en = None
    article.summary_te = summary_te or None
    article.body_en = None
    article.body_te = body_te or None
    article.language = "te"
    article.category_id = category.id
    article.source_name = source_name or None
    article.source_url = source_url or None
    article.image_url = image_url or previous_image_url

    requested_slug = slug_input or title_te
    article.slug = _unique_slug(requested_slug, article_id=article.id)

    if article.id is None:
        article.author_id = current_user.id
        article.status = "draft"

    db.session.add(article)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if uploaded_image_path and os.path.isfile(uploaded_image_path):
            try:
                os.remove(uploaded_image_path)
            except OSError:
                logger.exception(
                    "Could not remove unsaved article image %s.",
                    uploaded_image_path,
                )
        logger.exception("Could not save article.")
        flash("Could not save the article. Check the server log.", "danger")
        return False

    if previous_image_url != article.image_url:
        _delete_uploaded_image(previous_image_url)

    return True


# -------------------- ADMIN DASHBOARD --------------------

@admin_bp.route("/")
@login_required
def dashboard():
    counts = {
        "all": Article.query.filter_by(language="te").count(),
        "draft": Article.query.filter_by(
            status="draft",
            language="te",
        ).count(),
        "published": Article.query.filter_by(
            status="published",
            language="te",
        ).count(),
    }

    articles = (
        Article.query
        .filter(
            Article.language == "te",
            Article.title_te.isnot(None),
            Article.title_te != "",
        )
        .order_by(Article.id.desc())
        .limit(8)
        .all()
    )
    category_count = Category.query.count()
    unread_messages = ContactMessage.query.filter_by(is_read=False).count()

    return render_template(
        "admin/dashboard.html",
        counts=counts,
        articles=articles,
        category_count=category_count,
        unread_messages=unread_messages,
    )



@admin_bp.route("/rss-automation")
@login_required
def rss_automation():
    _require_admin()

    from models.rss_run import RssRun
    from services.news_collector import configured_feeds

    latest = RssRun.query.order_by(RssRun.started_at.desc()).first()
    runs = RssRun.query.order_by(RssRun.started_at.desc()).limit(30).all()

    return render_template(
        "admin/rss_automation.html",
        feeds=list(configured_feeds),
        latest=latest,
        runs=runs,
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

    query = Article.query.filter(
        Article.language == "te",
        Article.title_te.isnot(None),
        Article.title_te != "",
    )

    # Filter by publication status.
    if status in {"draft", "published"}:
        query = query.filter_by(status=status)

    article_list = query.order_by(Article.id.desc()).all()

    return render_template(
        "admin/articles.html",
        articles=article_list,
        selected_status=status,
        selected_language="te",
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
        logger.exception("Could not unpublish the article.")
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
        logger.exception("Could not delete the article.")
        flash("Could not delete the article.", "danger")

    return redirect(url_for("admin.articles"))
from flask import send_file
from io import BytesIO

from services.newspaper_pdf import generate_newspaper_pdf


@admin_bp.get("/newspaper/download")
@login_required
def download_newspaper():
    try:
        pdf_bytes = generate_newspaper_pdf()

        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="vstv6-telugu-newspaper.pdf",
        )

    except (ValueError, RuntimeError) as exc:
        return str(exc), 400