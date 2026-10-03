<p align="center">
  <img src="static/img/logo.svg" width="72" alt="Art Attack logo">
</p>

<h1 align="center">Art Attack</h1>

<p align="center">
  An art community and marketplace where two rival teams, the <b>Eldians</b> and the <b>Marleyans</b>, battle through art.<br>
  Flask · SQLAlchemy · MySQL / SQLite · DBMS course project
</p>

---

Artists publish work and original characters. Other users "attack" a character by drawing their own take on it, which earns points for their team. Attacking a character from your own team is **friendly fire**: no points, and both users get a warning in their mailbox. The platform also handles moderation, likes, reports, a cart and checkout, order tracking and PDF receipts.

## Features

- **Discover artwork**: search, filter by team or category, sort by newest, popularity or price, and like, report or contact artists.
- **Team battles**: character pages, art attacks, a live team scoreboard, and friendly-fire detection.
- **Artist dashboard**: total likes, likes per artwork with the names of everyone who liked it, sales and revenue.
- **Moderated uploads**: new artwork is *pending* until an admin approves or rejects it, with a reason.
- **Marketplace**: cart, checkout with delivery details, order status tracking, seller notifications, and downloadable PDF receipts.
- **Admin panel**: platform totals, moderation queue, reports, and suspending, banning or deleting users.
- **Security**: hashed passwords, CSRF protection on every form, server-side permission checks, uploads verified as real images, and ORM queries only (no raw SQL).

## Architecture

```mermaid
flowchart LR
    B[Browser] -- "HTML forms + CSRF token" --> F

    subgraph F["Flask app (app.py)"]
        R[Routes and views] --> L[Flask-Login<br/>sessions and roles]
        R --> M[SQLAlchemy models]
        R --> P[Pillow<br/>upload validation]
        R --> Q[ReportLab<br/>PDF receipts]
        R --> T[Jinja2 templates]
    end

    M --> DB[(MySQL via PyMySQL)]
    M -. "ART_ATTACK_SQLITE=1" .-> SL[(SQLite)]
    P --> U[/static/uploads/]
    R -. "optional" .-> S[SMTP email]
```

### Friendly-fire flow

```mermaid
flowchart TD
    A[User submits an attack on a character] --> B{Same team as the<br/>character's owner?}
    B -- No --> C[Save attack, +10 team points]
    C --> D[Notify owner: Incoming art attack]
    B -- Yes --> E[Save attack, 0 points, friendly_fire = true]
    E --> F[Warning in both users' mailboxes]
    F --> G[Email the owner too, if SMTP is set]
```

## Database

Ten tables, with foreign keys and delete rules set per relationship. Sales records use `RESTRICT` so purchase history can't be deleted by accident. Everything else cascades with its owner.

```mermaid
erDiagram
    USERS ||--o{ ARTWORKS : owns
    USERS ||--o{ CHARACTERS : creates
    USERS ||--o{ ARTWORK_LIKES : gives
    ARTWORKS ||--o{ ARTWORK_LIKES : receives
    USERS ||--o{ ATTACKS : launches
    CHARACTERS ||--o{ ATTACKS : "is target of"
    USERS ||--o{ REPORTS : files
    ARTWORKS |o--o{ REPORTS : "is reported in"
    USERS ||--o{ CART_ITEMS : "adds to cart"
    ARTWORKS ||--o{ CART_ITEMS : "sits in"
    USERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    ARTWORKS ||--o{ ORDER_ITEMS : "sold as"
    USERS ||--o{ NOTIFICATIONS : receives
```

See **[docs/database.md](docs/database.md)** for every column, unique key, index, delete rule and the main queries. The full project report is in [docs/report](docs/report/DBMS-Final-Report.pdf).

## Getting started

Requires **Python 3.11+**. MySQL is optional, because the app can run on SQLite for a local demo.

```powershell
git clone https://github.com/<your-username>/art_attack.git
cd art_attack
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Then fill in `.env` and pick a database.

### Option A: quick demo on SQLite

```powershell
$env:ART_ATTACK_SQLITE="1"      # macOS/Linux: export ART_ATTACK_SQLITE=1
flask --app app init-db
flask --app app seed-demo
flask --app app run
```

Open http://127.0.0.1:5000. `seed-demo` creates these accounts:

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin123!` |
| Eldian artist | `NovaInk` | `Artist123!` |
| Marleyan artist | `RookCanvas` | `Artist123!` |
| Member | `ArminReader` | `Member123!` |

These are demo passwords for local use only.

### Option B: MySQL

Create the database and a user:

```sql
CREATE DATABASE art_attack CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'art_attack_user'@'localhost' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON art_attack.* TO 'art_attack_user'@'localhost';
```

Set `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_NAME` and `SECRET_KEY` in `.env`, then run:

```powershell
flask --app app init-db
flask --app app run
```

A full `DATABASE_URL` (for example `mysql://user:pass@host/db`) also works and overrides the separate `DB_*` values.

### Optional: email

Friendly-fire warnings always appear in the in-app mailbox. To also send them by email, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASS` and optionally `SMTP_TLS` in `.env`.

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use an in-memory SQLite database, so they never touch your real data.

## Project structure

```
art_attack/
├── app.py                 # models, routes, CLI commands (init-db, seed-demo)
├── templates/             # Jinja2 pages (public, user, admin, errors)
├── static/
│   ├── css/app.css
│   ├── js/app.js          # CSRF token injection, menu, modals, confirms
│   ├── img/               # logo and illustrations
│   └── uploads/           # user uploads (git-ignored) + default/demo SVGs
├── tests/test_app.py
├── docs/
│   ├── database.md        # schema reference and ER diagram
│   └── report/            # DBMS project report (PDF + draft)
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```
