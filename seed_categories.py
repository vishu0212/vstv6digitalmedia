from extensions import db
from models import Category

def seed():
    categories = [
        ("Telangana", "తెలంగాణ", "telangana"),
        ("National", "జాతీయం", "national"),
        ("World", "ప్రపంచం", "world"),
        ("Technology", "సాంకేతికం", "technology"),
        ("Business", "వ్యాపారం", "business"),
        ("Sports", "క్రీడలు", "sports"),
        ("Entertainment", "వినోదం", "entertainment"),
    ]
    count = 0
    for en, te, slug in categories:
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(name_en=en, name_te=te, slug=slug))
            count += 1
    db.session.commit()
    print(f"Categories ready. Added {count}.")
