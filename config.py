
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configure PyMySQL SSL correctly.
    ca_path = os.getenv("MYSQL_SSL_CA")

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "connect_args": {
            "ssl": {"ca": ca_path} if ca_path else {}
        },
    }

    SITE_NAME = os.getenv("SITE_NAME", "VSTV6 Digital Media")
    SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:5000").rstrip("/")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    WTF_CSRF_TIME_LIMIT = 3600

    RSS_FEEDS = [
        x.strip()
        for x in os.getenv("RSS_FEEDS", "").split(",")
        if x.strip()
    ]
