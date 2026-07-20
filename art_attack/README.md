# Art Attack

Art Attack is a Flask + SQLAlchemy art community and marketplace built around two rival teams: Eldians and Marleyans. Artists can publish work and characters, users can launch creative attacks, and same-team attacks trigger a friendly-fire warning in both users' mailboxes. The project also includes moderation, role-aware analytics, sales, carts, orders, and downloadable PDF receipts.

## Main features

- Artwork discovery with search, team/category filters, sorting, likes, artist profiles, and reports
- Eldians vs Marleyans character attack system with team scoring and friendly-fire warnings
- Artist dashboard with total likes, per-artwork share, and the usernames of everyone who liked each piece
- Moderated upload pipeline: pending, approved, and rejected artwork
- Cart, delivery checkout, order status tracking, seller notifications, and PDF receipts
- Admin dashboard for users, suspensions/bans, reports, moderation, sales, and platform totals
- Responsive UI, server-side authorization, password hashing, CSRF protection, upload validation, and safe ORM queries

## Setup

```powershell
cd C:\Users\MTB\Desktop\art_attack
python -m pip install -r requirements.txt
python -m flask --app app init-db
python -m flask --app app run
```

The existing `.env` keys (`DB_USER`, `DB_PASS`, `DB_HOST`, `DB_NAME`, `SECRET_KEY`) are used for MySQL. Ensure the MySQL service and configured database are available before `init-db`.

For a local SQLite demo when MySQL is unavailable:

```powershell
$env:ART_ATTACK_SQLITE="1"
python -m flask --app app init-db
python -m flask --app app seed-demo
python -m flask --app app run
```

Demo credentials after `seed-demo`:

- Admin: `admin` / `Admin123!`
- Eldian artist: `NovaInk` / `Artist123!`
- Marleyan artist: `RookCanvas` / `Artist123!`
- Member: `ArminReader` / `Member123!`

Use demo passwords only for local evaluation. Change them before deployment.

## Optional email delivery

Friendly-fire warnings always arrive in the in-app mailbox. To mirror them to email, add `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASS`, and optionally `SMTP_TLS` to `.env`.

## Tests

```powershell
python -m pytest -q
```
