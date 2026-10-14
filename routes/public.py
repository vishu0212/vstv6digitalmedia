from flask import Blueprint, render_template, request
from sqlalchemy import or_
from models import Article, Category
public_bp = Blueprint("public", __name__)

@public_bp.get("/")
def home():
    articles = Article.query.filter_by(status="published").order_by(Article.published_at.desc()).limit(18).all()
    return render_template("index.html", articles=articles)

@public_bp.get("/search")
def search():
    q = request.args.get("q", "").strip()[:100]
    results = []
    if q:
        like = f"%{q}%"
        results = Article.query.filter(Article.status == "published", or_(
            Article.title_en.ilike(like), Article.title_te.ilike(like),
            Article.summary_en.ilike(like), Article.summary_te.ilike(like)
        )).order_by(Article.published_at.desc()).limit(50).all()
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
    articles = Article.query.filter_by(category_id=category.id, status="published").order_by(Article.published_at.desc()).limit(50).all()
    return render_template("category.html", category=category, articles=articles)
