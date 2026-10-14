import os
import pytest

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-only")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "test.db"))
    from app import create_app
    from extensions import db
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_home(app):
    assert app.test_client().get("/").status_code == 200

def test_sitemap(app):
    response = app.test_client().get("/sitemap.xml")
    assert response.status_code == 200
    assert b"urlset" in response.data

def test_login(app):
    assert app.test_client().get("/auth/login").status_code == 200
