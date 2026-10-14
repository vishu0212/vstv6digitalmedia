from flask import Blueprint, render_template
from models import Article
articles_bp = Blueprint("articles", __name__)

@articles_bp.get("/news/<slug>")
def detail(slug):
    article = Article.query.filter_by(slug=slug, status="published").first_or_404()
    return render_template("article.html", article=article)
