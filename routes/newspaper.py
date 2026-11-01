
from datetime import date, datetime
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from extensions import db
from models import Article
from services.newspaper_pdf import (
    create_newspaper_pdf,
    get_article_body,
    prepare_articles,
)


newspaper_bp = Blueprint(
    "newspaper",
    __name__,
    url_prefix="/admin/newspaper",
)


def _require_admin():
    """Allow only authenticated administrators."""
    if (
        not current_user.is_authenticated
        or getattr(current_user, "role", None) != "admin"
    ):
        abort(403)


def _get_published_articles():
    """Return published Telugu articles with body text, newest first."""
    articles = (
        Article.query
        .filter_by(status="published")
        .order_by(Article.id.desc())
        .all()
    )
    return prepare_articles(articles)


def _get_selected_articles(raw_ids):
    """Validate IDs and return only published Telugu articles."""
    selected_ids = []

    for raw_id in raw_ids:
        try:
            article_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        if article_id > 0 and article_id not in selected_ids:
            selected_ids.append(article_id)

    if not selected_ids:
        return []

    queried_articles = (
        Article.query
        .filter(
            Article.id.in_(selected_ids),
            Article.status == "published",
        )
        .all()
    )
    articles = prepare_articles(queried_articles)

    # Keep the order chosen by the user.
    article_by_id = {article.id: article for article in articles}

    return [
        article_by_id[article_id]
        for article_id in selected_ids
        if article_id in article_by_id
    ]


@newspaper_bp.route("/", methods=["GET", "POST"])
@login_required
def generator():
    """Display the newspaper generator and preview selected stories."""
    _require_admin()

    articles = _get_published_articles()
    selected_articles = []
    selected_ids = []

    if request.method == "POST":
        selected_articles = _get_selected_articles(
            request.form.getlist("article_ids")
        )
        selected_ids = [article.id for article in selected_articles]

    return render_template(
        "admin/newspaper/generator.html",
        articles=articles,
        selected_articles=selected_articles,
        selected_ids=selected_ids,
        edition_date=date.today().isoformat(),
    )


@newspaper_bp.route("/preview", methods=["GET", "POST"])
@login_required
def preview():
    """Display the newspaper preview for selected published articles."""
    _require_admin()

    if request.method == "POST":
        raw_ids = request.form.getlist("article_ids")
    else:
        raw_ids = request.args.getlist("article_ids")

    selected_articles = _get_selected_articles(raw_ids)

    if not selected_articles:
        return render_template(
            "admin/newspaper/preview.html",
            selected_articles=[],
            article_bodies={},
            edition_date=date.today().isoformat(),
        )

    return render_template(
        "admin/newspaper/preview.html",
        selected_articles=selected_articles,
        article_bodies={
            article.id: get_article_body(article)
            for article in selected_articles
        },
        edition_date=date.today().isoformat(),
    )


@newspaper_bp.route("/download-pdf", methods=["POST"])
@login_required
def download_pdf():
    """Generate and download an A3 PDF containing selected published news."""
    _require_admin()

    selected_articles = _get_selected_articles(
        request.form.getlist("article_ids")
    )

    if not selected_articles:
        abort(400, description="Select at least one published article.")

    edition_date = date.today().isoformat()

    try:
        pdf_file = create_newspaper_pdf(
            selected_articles,
            edition_date=edition_date,
        )

        if pdf_file is None:
            current_app.logger.error(
                "The newspaper PDF service returned no file."
            )
            abort(500, description="Unable to generate the newspaper PDF.")

        filename = (
            f"vstv6-newspaper-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        )

        return send_file(
            pdf_file,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )

    except Exception:
        current_app.logger.exception("Newspaper PDF generation failed.")
        abort(500, description="Newspaper PDF generation failed. Check the server log.")


@newspaper_bp.route("/health", methods=["GET"])
@login_required
def newspaper_health():
    """Simple administrator-only diagnostic endpoint."""
    _require_admin()

    return {
        "status": "ok",
        "service": "VSTV6 Newspaper Generator",
        "published_articles": Article.query.filter_by(
            status="published"
        ).count(),
        "date": date.today().isoformat(),
    }
