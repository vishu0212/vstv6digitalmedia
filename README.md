# VSTV6 Digital Media

Bilingual (Telugu + English) Flask news portal with MySQL, login, article CRUD, mandatory admin approval, RSS-to-draft collection, sitemap, robots.txt, RSS output and NewsArticle structured data.

## Windows / VS Code
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
If activation is blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again.

## MySQL
Run in MySQL Workbench:
```sql
CREATE DATABASE vstv6_news CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'vstv6_user'@'localhost' IDENTIFIED BY 'USE_A_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON vstv6_news.* TO 'vstv6_user'@'localhost';
FLUSH PRIVILEGES;
```
Put the matching connection string in `.env`. URL-encode special characters in the DB password. Generate `SECRET_KEY`:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Do not commit `.env`.

## First database migration and admin
```powershell
$env:FLASK_APP = "app.py"
flask db upgrade
flask seed-categories
flask create-admin
python app.py
```
The initial Alembic migration is included in `migrations/`. For later schema changes, run `flask db migrate -m "describe change"` then `flask db upgrade`.

Open http://127.0.0.1:5000. Admin login: `/auth/login`; dashboard: `/admin`.

## RSS intake
Set comma-separated HTTPS **Telugu news** RSS URLs in `RSS_FEEDS`, create an active admin and seed categories first, then run:
```powershell
flask collect-rss
```
The Render blueprint includes a cron service that runs this command at the start of every hour (UTC). Configure the cron service's `DATABASE_URL`, `RSS_FEEDS`, and optional `MYSQL_SSL_CA` environment variables in Render; use the same database as the web service. Set `RSS_FEEDS` to Telugu feeds, not English-only feeds. The cron service needs its own `SECRET_KEY` and can use the generated value.

RSS stories are saved as drafts only; articles without Telugu script in the headline or full body are skipped. Public news pages and newspaper editions likewise require Telugu script in the headline and full body, while mixed-language stories containing Telugu words are allowed. English-only summaries are omitted. No automatic translation is performed. An admin must review, write original copy, and publish manually. Do not republish full copyrighted articles. For local hourly collection, configure Windows Task Scheduler to run `flask collect-rss` hourly from the project folder using the virtual environment Python.

GitHub Actions also schedules collection at 17 minutes past every hour (UTC). Add repository Actions secrets named `DATABASE_URL`, `RSS_FEEDS`, and `SECRET_KEY`; add `MYSQL_SSL_CA` if the database requires a custom CA certificate. Use the same database and Telugu feed URLs as the web app. GitHub scheduled runs can be delayed, especially during periods of high Actions load. Enable only one hosted scheduler (Render or GitHub Actions) to avoid polling the same feeds twice each hour.

## Routes
`/`, `/news/<slug>`, `/category/<slug>`, `/search?q=...`, `/auth/login`, `/admin`, `/sitemap.xml`, `/robots.txt`, `/feed.xml`.

## Security
Use HTTPS in production and set `COOKIE_SECURE=1`. Never use Flask debug mode publicly. Use a unique secret, least-privilege DB user, backups, updated dependencies, and restricted admin access. CSRF protection is enabled. User article content is rendered as escaped plain text. Article editors can upload JPG, PNG, GIF, or WEBP images up to 8 MB; configure `UPLOAD_FOLDER` to a persistent disk path in production because app-local files may be removed during redeploys. This starter does not include rate limiting, MFA, or audit logs; add them before a high-traffic launch.

## Free hosting
Free providers can sleep, restrict databases, or remove ephemeral files. Do not store MySQL data on an app server's temporary filesystem. Verify current database/network limits with the provider before deployment.
