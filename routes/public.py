from flask import Blueprint, render_template, request
from sqlalchemy import or_
from models import Article, Category
public_bp = Blueprint("public", __name__)


def _telugu_stories(query, limit):
    """Return up to limit stories with Telugu-only headlines and bodies."""
    stories = []
    for article in query.yield_per(100):
        if article.has_telugu_story:
            stories.append(article)
            if len(stories) >= limit:
                break
    return stories


@public_bp.get("/")
def home():
    articles = _telugu_stories(
        Article.query
        .filter(
            Article.status == "published",
            Article.language == "te",
            Article.title_te.isnot(None),
            Article.title_te != "",
        )
        .order_by(Article.published_at.desc()),
        18,
    )
    return render_template("index.html", articles=articles)

@public_bp.get("/search")
def search():
    q = request.args.get("q", "").strip()[:100]
    results = []
    if q:
        like = f"%{q}%"
        results = _telugu_stories(
            Article.query
            .filter(
                Article.status == "published",
                Article.language == "te",
                Article.title_te.isnot(None),
                Article.title_te != "",
                or_(
                    Article.title_te.ilike(like),
                    Article.summary_te.ilike(like),
                    Article.body_te.ilike(like),
                    Article.title_en.ilike(like),
                    Article.summary_en.ilike(like),
                    Article.body_en.ilike(like),
                ),
            )
            .order_by(Article.published_at.desc()),
            50,
        )
    return render_template("search.html", articles=results, query=q)

@public_bp.get("/about")
def about():
    return render_template("about.html")

@public_bp.get("/contact")
def contact():
    return render_template("contact.html")

@public_bp.get("/category/<slug>")
def category(slug):
    category = Category.query.filter_by(slug=slug).first_or_404()
    articles = _telugu_stories(
        Article.query
        .filter_by(
            category_id=category.id,
            status="published",
            language="te",
        )
        .filter(
            Article.title_te.isnot(None),
            Article.title_te != "",
        )
        .order_by(Article.published_at.desc()),
        50,
    )
    return render_template("category.html", category=category, articles=articles)
