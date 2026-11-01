
from flask import abort, Blueprint, render_template
from models import Article

articles_bp = Blueprint("articles", __name__)


@articles_bp.get("/news/<slug>")
def detail(slug):
    """Display a published news article by its slug."""

    article = Article.query.filter_by(
        slug=slug,
        status="published",
        language="te",
    ).filter(
        Article.title_te.isnot(None),
        Article.title_te != "",
    ).first_or_404()

    if not article.has_telugu_story:
        abort(404)

    body = article.telugu_body or ""

    return render_template(
        "article.html",
        article=article,
        article_body=body,
    )
