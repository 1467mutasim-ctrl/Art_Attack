from __future__ import annotations

import io
import os
import secrets
import smtplib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from PIL import Image, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ORDER_STATUSES = ("placed", "confirmed", "in_progress", "shipped", "delivered", "cancelled")
REPORT_REASONS = ("Spam", "Harassment", "Inappropriate content", "Copyright violation", "Fraud", "Other")
ART_CATEGORIES = ("Digital", "Traditional", "Painting", "Illustration", "Photography", "Sculpture", "Mixed media", "Other")


def database_uri() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit.replace("mysql://", "mysql+pymysql://", 1)
    if os.getenv("ART_ATTACK_SQLITE", "0") == "1":
        return f"sqlite:///{(BASE_DIR / 'art_attack.db').as_posix()}"
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    host = os.getenv("DB_HOST", "localhost")
    name = os.getenv("DB_NAME")
    if user and name:
        return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password or '')}@{host}/{quote_plus(name)}?charset=utf8mb4"
    return f"sqlite:///{(BASE_DIR / 'art_attack.db').as_posix()}"


def utcnow() -> datetime:
    return datetime.utcnow()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    team = db.Column(db.String(20), nullable=False)
    bio = db.Column(db.Text, default="")
    profile_image = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="active")
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    artworks = db.relationship("Artwork", back_populates="owner", cascade="all, delete-orphan", lazy="selectin")
    characters = db.relationship("Character", back_populates="owner", cascade="all, delete-orphan", lazy="selectin")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def role_name(self) -> str:
        return "Admin" if self.is_admin else self.role.title()

    @property
    def profile_image_url(self) -> str:
        filename = self.profile_image or "avatar-default.svg"
        return url_for("static", filename=f"uploads/{filename}")

    @property
    def is_banned(self) -> bool:
        return self.status == "banned"


class Artwork(db.Model):
    __tablename__ = "artworks"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    image_path = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Other")
    medium = db.Column(db.String(80), default="")
    tags = db.Column(db.String(255), default="")
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    for_sale = db.Column(db.Boolean, nullable=False, default=False)
    is_sold = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    rejection_reason = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    owner = db.relationship("User", back_populates="artworks")
    likes = db.relationship("ArtworkLike", back_populates="artwork", cascade="all, delete-orphan", lazy="selectin")

    @property
    def like_count(self) -> int:
        return len(self.likes)

    @property
    def tag_list(self) -> list[str]:
        return [tag.strip() for tag in (self.tags or "").split(",") if tag.strip()]


class ArtworkLike(db.Model):
    __tablename__ = "artwork_likes"
    __table_args__ = (db.UniqueConstraint("user_id", "artwork_id", name="uq_user_artwork_like"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", lazy="joined")
    artwork = db.relationship("Artwork", back_populates="likes")


class Character(db.Model):
    __tablename__ = "characters"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    pronouns = db.Column(db.String(50), default="")
    description = db.Column(db.Text, default="")
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    owner = db.relationship("User", back_populates="characters")
    attacks = db.relationship("Attack", back_populates="character", cascade="all, delete-orphan", lazy="selectin")


class Attack(db.Model):
    __tablename__ = "attacks"

    id = db.Column(db.Integer, primary_key=True)
    attacker_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = db.Column(db.Integer, db.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    image_path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default="")
    points = db.Column(db.Integer, nullable=False, default=10)
    friendly_fire = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    attacker = db.relationship("User", lazy="joined")
    character = db.relationship("Character", back_populates="attacks")


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id", ondelete="CASCADE"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    reason = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    reporter = db.relationship("User", foreign_keys=[reporter_id], lazy="joined")
    reported_user = db.relationship("User", foreign_keys=[user_id], lazy="joined")
    artwork = db.relationship("Artwork", lazy="joined")


class CartItem(db.Model):
    __tablename__ = "cart_items"
    __table_args__ = (db.UniqueConstraint("user_id", "artwork_id", name="uq_cart_user_artwork"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    artwork = db.relationship("Artwork", lazy="joined")


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    reference = db.Column(db.String(24), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="placed")
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    buyer = db.relationship("User", lazy="joined")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id", ondelete="RESTRICT"), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    artwork = db.relationship("Artwork", lazy="joined")
    seller = db.relationship("User", lazy="joined")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(40), nullable=False, default="info")
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", lazy="joined")


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def save_image(file_storage, prefix: str) -> str:
    if not file_storage or not file_storage.filename:
        raise ValueError("Please choose an image.")
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Use a PNG, JPG, GIF, or WEBP image.")
    try:
        image = Image.open(file_storage.stream)
        image.verify()
        file_storage.stream.seek(0)
    except (UnidentifiedImageError, OSError):
        raise ValueError("The selected file is not a valid image.")
    filename = f"{prefix}-{secrets.token_hex(12)}.{ext}"
    upload_dir = BASE_DIR / "static" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_storage.save(upload_dir / filename)
    return filename


def parse_price(value: str) -> Decimal:
    try:
        price = Decimal((value or "0").strip()).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError("Enter a valid price.")
    if price < 0:
        raise ValueError("Price cannot be negative.")
    return price


def add_notification(user: User, title: str, message: str, kind: str = "info", link: str | None = None) -> None:
    db.session.add(Notification(user_id=user.id, title=title, message=message, kind=kind, link=link))


def send_optional_email(recipient: User, subject: str, message: str) -> None:
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        return
    email = EmailMessage()
    email["From"] = sender
    email["To"] = recipient.email
    email["Subject"] = subject
    email.set_content(message)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=8) as smtp:
            if os.getenv("SMTP_TLS", "1") == "1":
                smtp.starttls()
            if os.getenv("SMTP_USER"):
                smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS", ""))
            smtp.send_message(email)
    except (OSError, smtplib.SMTPException):
        pass


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=database_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message_category = "warning"

    @app.template_filter("money")
    def money(value):
        return f"৳{Decimal(value or 0):,.2f}"

    @app.template_filter("datetime")
    def format_datetime(value):
        return value.strftime("%d %b %Y · %I:%M %p") if value else ""

    @app.context_processor
    def global_context():
        unread = 0
        cart_count = 0
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
        return {
            "unread_notifications": unread,
            "cart_count": cart_count,
            "report_reasons": REPORT_REASONS,
            "art_categories": ART_CATEGORIES,
            "current_year": datetime.utcnow().year,
        }

    @app.before_request
    def block_inactive_users():
        if current_user.is_authenticated and current_user.status in {"banned", "suspended"}:
            account_status = current_user.status
            logout_user()
            flash(f"Your account is {account_status}. Contact an administrator.", "danger")
            return redirect(url_for("login"))

    @app.route("/")
    def index():
        artworks = Artwork.query.filter_by(status="approved").order_by(Artwork.created_at.desc()).limit(12).all()
        team_scores = dict(
            db.session.query(User.team, func.coalesce(func.sum(Attack.points), 0))
            .join(Attack, Attack.attacker_id == User.id, isouter=True)
            .group_by(User.team)
            .all()
        )
        stats = {
            "artists": User.query.filter_by(role="artist", status="active").count(),
            "artworks": Artwork.query.filter_by(status="approved").count(),
            "attacks": Attack.query.count(),
        }
        return render_template("index.html", artworks=artworks, team_scores=team_scores, stats=stats)

    @app.route("/browse")
    def browse():
        query = Artwork.query.filter_by(status="approved")
        q = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        team = request.args.get("team", "").strip()
        sale = request.args.get("sale", "") == "1"
        sort = request.args.get("sort", "newest")
        if q or team:
            query = query.join(User, Artwork.owner_id == User.id)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(Artwork.title.ilike(like), Artwork.tags.ilike(like), User.username.ilike(like)))
        if category:
            query = query.filter(Artwork.category == category)
        if team:
            query = query.filter(User.team == team)
        if sale:
            query = query.filter(Artwork.for_sale.is_(True), Artwork.is_sold.is_(False))
        if sort == "popular":
            like_counts = (
                db.session.query(ArtworkLike.artwork_id.label("artwork_id"), func.count(ArtworkLike.id).label("like_count"))
                .group_by(ArtworkLike.artwork_id)
                .subquery()
            )
            query = query.outerjoin(like_counts, like_counts.c.artwork_id == Artwork.id).order_by(func.coalesce(like_counts.c.like_count, 0).desc())
        elif sort == "price_low":
            query = query.order_by(Artwork.price.asc())
        elif sort == "price_high":
            query = query.order_by(Artwork.price.desc())
        else:
            query = query.order_by(Artwork.created_at.desc())
        return render_template("browse.html", artworks=query.all())

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            team = request.form.get("team", "")
            role = request.form.get("role", "member")
            if len(username) < 3 or len(password) < 8 or "@" not in email:
                flash("Use a username of 3+ characters, a valid email, and a password of 8+ characters.", "danger")
            elif team not in {"Eldians", "Marleyans"} or role not in {"member", "artist"}:
                flash("Choose a valid team and account type.", "danger")
            elif User.query.filter(or_(User.username == username, User.email == email)).first():
                flash("That username or email is already registered.", "danger")
            else:
                user = User(username=username, email=email, team=team, role=role)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                login_user(user)
                flash(f"Welcome to {team}, {username}!", "success")
                return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            identity = request.form.get("identity", "").strip()
            user = User.query.filter(or_(User.username == identity, User.email == identity.lower())).first()
            if not user or not user.check_password(request.form.get("password", "")):
                flash("Incorrect username/email or password.", "danger")
            elif user.status != "active":
                flash(f"This account is {user.status}.", "danger")
            else:
                login_user(user, remember=request.form.get("remember") == "1")
                return redirect(request.args.get("next") or url_for("dashboard"))
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You are signed out.", "success")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        owned = Artwork.query.filter_by(owner_id=current_user.id).all()
        total_likes = sum(art.like_count for art in owned)
        like_breakdown = [
            {"artwork": art, "count": art.like_count, "likers": [like.user for like in art.likes]}
            for art in sorted(owned, key=lambda item: item.like_count, reverse=True)
        ]
        attacks_sent = Attack.query.filter_by(attacker_id=current_user.id).count()
        attacks_received = Attack.query.join(Character).filter(Character.owner_id == current_user.id).count()
        purchases = Order.query.filter_by(buyer_id=current_user.id).count()
        revenue = (
            db.session.query(func.coalesce(func.sum(OrderItem.price), 0))
            .join(Order)
            .filter(OrderItem.seller_id == current_user.id, Order.status != "cancelled")
            .scalar()
        )
        recent_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
        recent_sales = (
            OrderItem.query.join(Order)
            .filter(OrderItem.seller_id == current_user.id)
            .order_by(Order.created_at.desc())
            .limit(5)
            .all()
        )
        return render_template(
            "dashboard.html",
            artworks=owned,
            total_likes=total_likes,
            like_breakdown=like_breakdown,
            attacks_sent=attacks_sent,
            attacks_received=attacks_received,
            purchases=purchases,
            revenue=revenue,
            recent_notifications=recent_notifications,
            recent_sales=recent_sales,
        )

    @app.route("/profile/<int:user_id>")
    def profile(user_id):
        user = db.get_or_404(User, user_id)
        approved = [art for art in user.artworks if art.status == "approved" or current_user.is_authenticated and current_user.id == user.id]
        total_likes = sum(art.like_count for art in user.artworks)
        sales = OrderItem.query.filter_by(seller_id=user.id).count()
        return render_template("profile.html", user=user, artworks=approved, total_likes=total_likes, sales=sales)

    @app.route("/profile/edit", methods=["GET", "POST"])
    @login_required
    def edit_profile():
        if request.method == "POST":
            username = request.form.get("display_name", "").strip()
            if len(username) < 3:
                flash("Display name must be at least 3 characters.", "danger")
            elif User.query.filter(User.username == username, User.id != current_user.id).first():
                flash("That display name is already taken.", "danger")
            else:
                current_user.username = username
                current_user.bio = request.form.get("bio", "").strip()[:1000]
                if request.files.get("profile_image") and request.files["profile_image"].filename:
                    try:
                        current_user.profile_image = save_image(request.files["profile_image"], "avatar")
                    except ValueError as exc:
                        flash(str(exc), "danger")
                        return render_template("edit_profile.html", user=current_user)
                db.session.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("profile", user_id=current_user.id))
        return render_template("edit_profile.html", user=current_user)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def user_settings():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            if "@" not in email or User.query.filter(User.email == email, User.id != current_user.id).first():
                flash("Use a valid, unique email address.", "danger")
            else:
                current_user.email = email
                password = request.form.get("password", "")
                if password:
                    if len(password) < 8:
                        flash("New password must be at least 8 characters.", "danger")
                        return render_template("user_settings.html", user=current_user)
                    current_user.set_password(password)
                db.session.commit()
                flash("Account settings saved.", "success")
                return redirect(url_for("dashboard"))
        return render_template("user_settings.html", user=current_user)

    @app.route("/artwork/upload", methods=["GET", "POST"])
    @login_required
    def upload_artwork():
        if current_user.role != "artist" and not current_user.is_admin:
            abort(403)
        if request.method == "POST":
            try:
                title = request.form.get("title", "").strip()
                if len(title) < 2:
                    raise ValueError("Add an artwork title.")
                category = request.form.get("category", "Other")
                if category not in ART_CATEGORIES:
                    raise ValueError("Choose a valid category.")
                price = parse_price(request.form.get("price", "0"))
                image_path = save_image(request.files.get("image"), "art")
                artwork = Artwork(
                    owner_id=current_user.id,
                    title=title[:120],
                    description=request.form.get("description", "").strip()[:5000],
                    image_path=image_path,
                    category=category,
                    medium=request.form.get("medium", "").strip()[:80],
                    tags=request.form.get("tags", "").strip()[:255],
                    price=price,
                    for_sale=request.form.get("for_sale") == "1" and price > 0,
                    status="pending",
                )
                db.session.add(artwork)
                db.session.commit()
                flash("Artwork submitted for admin approval.", "success")
                return redirect(url_for("dashboard"))
            except ValueError as exc:
                flash(str(exc), "danger")
        return render_template("upload_artwork.html")

    @app.route("/artwork/<int:painting_id>")
    def artwork_detail(painting_id):
        artwork = db.get_or_404(Artwork, painting_id)
        can_preview = current_user.is_authenticated and (current_user.id == artwork.owner_id or current_user.is_admin)
        if artwork.status != "approved" and not can_preview:
            abort(404)
        liked = current_user.is_authenticated and ArtworkLike.query.filter_by(user_id=current_user.id, artwork_id=artwork.id).first() is not None
        return render_template("artwork_detail.html", artwork=artwork, liked=liked)

    @app.post("/artwork/<int:painting_id>/like")
    @login_required
    def toggle_like(painting_id):
        artwork = db.get_or_404(Artwork, painting_id)
        if artwork.status != "approved":
            abort(404)
        like = ArtworkLike.query.filter_by(user_id=current_user.id, artwork_id=artwork.id).first()
        if like:
            db.session.delete(like)
        else:
            db.session.add(ArtworkLike(user_id=current_user.id, artwork_id=artwork.id))
            if artwork.owner_id != current_user.id:
                add_notification(artwork.owner, "Your artwork got some love", f"{current_user.username} liked “{artwork.title}”.", "like", url_for("artwork_detail", painting_id=artwork.id))
        db.session.commit()
        return redirect(request.referrer or url_for("artwork_detail", painting_id=artwork.id))

    @app.post("/artwork/<int:painting_id>/report")
    @login_required
    def report_artwork(painting_id):
        artwork = db.get_or_404(Artwork, painting_id)
        reason = request.form.get("reason", "")
        if reason not in REPORT_REASONS:
            flash("Choose a report reason.", "danger")
        else:
            db.session.add(Report(reporter_id=current_user.id, artwork_id=artwork.id, reason=reason, description=request.form.get("description", "")[:2000]))
            db.session.commit()
            flash("Report submitted for review.", "success")
        return redirect(url_for("artwork_detail", painting_id=artwork.id))

    @app.post("/user/<int:user_id>/report")
    @login_required
    def report_user(user_id):
        user = db.get_or_404(User, user_id)
        if user.id == current_user.id:
            abort(400)
        reason = request.form.get("reason", "")
        if reason in REPORT_REASONS:
            db.session.add(Report(reporter_id=current_user.id, user_id=user.id, reason=reason, description=request.form.get("description", "")[:2000]))
            db.session.commit()
            flash("User report submitted.", "success")
        else:
            flash("Choose a report reason.", "danger")
        return redirect(url_for("profile", user_id=user.id))

    @app.post("/user/<int:user_id>/contact")
    @login_required
    def contact_artist(user_id):
        user = db.get_or_404(User, user_id)
        message = request.form.get("message", "").strip()
        if not message:
            flash("Write a message first.", "danger")
        else:
            add_notification(user, f"Message from {current_user.username}", message[:2000], "message", url_for("profile", user_id=current_user.id))
            db.session.commit()
            flash("Message delivered to their mailbox.", "success")
        return redirect(url_for("profile", user_id=user.id))

    @app.route("/characters")
    def characters():
        query = Character.query
        owner_id = request.args.get("owner", type=int)
        team = request.args.get("team", "").strip()
        if owner_id:
            query = query.filter(Character.owner_id == owner_id)
        if team in {"Eldians", "Marleyans"}:
            query = query.join(User, Character.owner_id == User.id).filter(User.team == team)
        characters_list = query.order_by(Character.created_at.desc()).all()
        return render_template("characters.html", characters=characters_list)

    @app.route("/characters/create", methods=["GET", "POST"])
    @login_required
    def create_character():
        if request.method == "POST":
            try:
                name = request.form.get("name", "").strip()
                if len(name) < 2:
                    raise ValueError("Add a character name.")
                image = request.files.get("image")
                filename = save_image(image, "character") if image and image.filename else None
                character = Character(owner_id=current_user.id, name=name[:100], pronouns=request.form.get("pronouns", "")[:50], description=request.form.get("description", "")[:5000], image_path=filename)
                db.session.add(character)
                db.session.commit()
                flash("Character published.", "success")
                return redirect(url_for("character_detail", character_id=character.id))
            except ValueError as exc:
                flash(str(exc), "danger")
        return render_template("create_character.html")

    @app.route("/characters/<int:character_id>")
    def character_detail(character_id):
        character = db.get_or_404(Character, character_id)
        attacks = Attack.query.filter_by(character_id=character.id).order_by(Attack.created_at.desc()).all()
        return render_template("character_detail.html", character=character, character_attacks=attacks)

    @app.route("/characters/<int:character_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_character(character_id):
        character = db.get_or_404(Character, character_id)
        if current_user.id != character.owner_id and not current_user.is_admin:
            abort(403)
        if request.method == "POST":
            character.name = request.form.get("name", "").strip()[:100]
            character.pronouns = request.form.get("pronouns", "").strip()[:50]
            character.description = request.form.get("description", "").strip()[:5000]
            if request.files.get("image") and request.files["image"].filename:
                try:
                    character.image_path = save_image(request.files["image"], "character")
                except ValueError as exc:
                    flash(str(exc), "danger")
                    return render_template("edit_character.html", character=character)
            db.session.commit()
            flash("Character updated.", "success")
            return redirect(url_for("character_detail", character_id=character.id))
        return render_template("edit_character.html", character=character)

    @app.route("/characters/<int:character_id>/attack", methods=["GET", "POST"])
    @login_required
    def attack_form(character_id):
        character = db.get_or_404(Character, character_id)
        if character.owner_id == current_user.id:
            flash("You cannot attack your own character.", "danger")
            return redirect(url_for("character_detail", character_id=character.id))
        friendly = current_user.team == character.owner.team
        if request.method == "POST":
            try:
                filename = save_image(request.files.get("image"), "attack")
                attack = Attack(
                    attacker_id=current_user.id,
                    character_id=character.id,
                    image_path=filename,
                    description=request.form.get("description", "")[:3000],
                    friendly_fire=friendly,
                    points=0 if friendly else 10,
                )
                db.session.add(attack)
                link = url_for("character_detail", character_id=character.id)
                if friendly:
                    title = "Friendly fire warning"
                    message = f"{current_user.username} attacked {character.name}, but both artists are on Team {current_user.team}. No team points were awarded."
                    add_notification(current_user, title, message, "warning", link)
                    add_notification(character.owner, title, message, "warning", link)
                    send_optional_email(character.owner, f"Art Attack: {title}", message)
                else:
                    add_notification(character.owner, "Incoming art attack!", f"{current_user.username} attacked {character.name}. Your team can counter for glory.", "attack", link)
                db.session.commit()
                flash("Attack submitted. Friendly-fire notices were sent." if friendly else "Attack landed! Your team earned 10 points.", "warning" if friendly else "success")
                return redirect(link)
            except ValueError as exc:
                flash(str(exc), "danger")
        return render_template("attack_form.html", character=character, friendly=friendly)

    @app.route("/my-attacks")
    @login_required
    def my_attacks():
        attacks = Attack.query.filter_by(attacker_id=current_user.id).order_by(Attack.created_at.desc()).all()
        return render_template("my_attacks.html", attacks=attacks)

    @app.post("/cart/add/<int:painting_id>")
    @login_required
    def add_to_cart(painting_id):
        artwork = db.get_or_404(Artwork, painting_id)
        if not artwork.for_sale or artwork.is_sold or artwork.status != "approved" or artwork.owner_id == current_user.id:
            flash("This artwork cannot be added to your cart.", "danger")
        elif CartItem.query.filter_by(user_id=current_user.id, artwork_id=artwork.id).first():
            flash("That artwork is already in your cart.", "warning")
        else:
            db.session.add(CartItem(user_id=current_user.id, artwork_id=artwork.id))
            db.session.commit()
            flash("Added to cart.", "success")
        return redirect(request.referrer or url_for("cart"))

    @app.route("/cart")
    @login_required
    def cart():
        items = CartItem.query.filter_by(user_id=current_user.id).order_by(CartItem.created_at.desc()).all()
        subtotal = sum((item.artwork.price for item in items), Decimal("0"))
        delivery_fee = Decimal("200.00") if items else Decimal("0")
        return render_template("cart.html", items=items, subtotal=subtotal, delivery_fee=delivery_fee, total=subtotal + delivery_fee)

    @app.post("/cart/remove/<int:item_id>")
    @login_required
    def remove_cart_item(item_id):
        item = db.get_or_404(CartItem, item_id)
        if item.user_id != current_user.id:
            abort(403)
        db.session.delete(item)
        db.session.commit()
        flash("Removed from cart.", "success")
        return redirect(url_for("cart"))

    @app.route("/checkout", methods=["GET", "POST"])
    @login_required
    def checkout():
        items = CartItem.query.filter_by(user_id=current_user.id).all()
        available = [item for item in items if item.artwork.for_sale and not item.artwork.is_sold and item.artwork.status == "approved"]
        if not available:
            flash("Your cart has no available artworks.", "warning")
            return redirect(url_for("cart"))
        subtotal = sum((item.artwork.price for item in available), Decimal("0"))
        delivery_fee = Decimal("200.00")
        if request.method == "POST":
            required = {key: request.form.get(key, "").strip() for key in ("full_name", "email", "phone", "address")}
            if not all(required.values()) or "@" not in required["email"]:
                flash("Complete all delivery details.", "danger")
            else:
                order = Order(
                    buyer_id=current_user.id,
                    reference=f"AA-{datetime.utcnow():%y%m%d}-{secrets.token_hex(3).upper()}",
                    status="placed",
                    subtotal=subtotal,
                    delivery_fee=delivery_fee,
                    total=subtotal + delivery_fee,
                    **required,
                )
                db.session.add(order)
                db.session.flush()
                for item in available:
                    art = item.artwork
                    db.session.add(OrderItem(order_id=order.id, artwork_id=art.id, seller_id=art.owner_id, title=art.title, price=art.price))
                    art.is_sold = True
                    add_notification(art.owner, "Artwork sold", f"“{art.title}” was purchased in order {order.reference}.", "sale", url_for("dashboard"))
                    db.session.delete(item)
                db.session.commit()
                flash("Order placed. Your PDF receipt is ready.", "success")
                return redirect(url_for("order_detail", order_id=order.id))
        return render_template("checkout.html", items=available, subtotal=subtotal, delivery_fee=delivery_fee, total=subtotal + delivery_fee)

    @app.route("/orders")
    @login_required
    def orders():
        orders_list = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).all()
        return render_template("orders.html", orders=orders_list)

    @app.route("/orders/<int:order_id>")
    @login_required
    def order_detail(order_id):
        order = db.get_or_404(Order, order_id)
        if order.buyer_id != current_user.id and not current_user.is_admin and not any(item.seller_id == current_user.id for item in order.items):
            abort(403)
        return render_template("order_detail.html", order=order)

    @app.post("/orders/<int:order_id>/status")
    @login_required
    def update_order_status(order_id):
        order = db.get_or_404(Order, order_id)
        if not current_user.is_admin and not any(item.seller_id == current_user.id for item in order.items):
            abort(403)
        status = request.form.get("status")
        if status not in ORDER_STATUSES:
            abort(400)
        order.status = status
        add_notification(order.buyer, "Order status updated", f"{order.reference} is now {status.replace('_', ' ')}.", "order", url_for("order_detail", order_id=order.id))
        db.session.commit()
        flash("Order status updated.", "success")
        return redirect(url_for("order_detail", order_id=order.id))

    @app.route("/orders/<int:order_id>/receipt.pdf")
    @login_required
    def order_receipt(order_id):
        order = db.get_or_404(Order, order_id)
        if order.buyer_id != current_user.id and not current_user.is_admin:
            abort(403)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleAA", parent=styles["Title"], textColor=colors.HexColor("#E85643"), fontSize=26)
        story = [Paragraph("ART ATTACK", title_style), Paragraph("Official purchase receipt", styles["Heading2"]), Spacer(1, 8 * mm)]
        story.append(Table([["Receipt", order.reference], ["Date", order.created_at.strftime("%d %B %Y, %I:%M %p")], ["Customer", order.full_name], ["Email", order.email], ["Status", order.status.replace("_", " ").title()]], colWidths=[35 * mm, 120 * mm], style=TableStyle([("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])))
        story += [Spacer(1, 8 * mm)]
        rows = [["Artwork", "Artist", "Price"]] + [[item.title, item.seller.username, f"BDT {item.price:,.2f}"] for item in order.items]
        rows += [["", "Subtotal", f"BDT {order.subtotal:,.2f}"], ["", "Delivery", f"BDT {order.delivery_fee:,.2f}"], ["", "Total", f"BDT {order.total:,.2f}"]]
        table = Table(rows, colWidths=[75 * mm, 50 * mm, 35 * mm], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17171C")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -4), .4, colors.HexColor("#D9DEE7")), ("ALIGN", (-1, 1), (-1, -1), "RIGHT"), ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"), ("TEXTCOLOR", (1, -1), (-1, -1), colors.HexColor("#E85643")), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story += [table, Spacer(1, 10 * mm), Paragraph("Thank you for supporting independent artists through Art Attack.", styles["BodyText"]), Paragraph(f"Delivery address: {order.address}", styles["BodyText"])]
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"{order.reference}-receipt.pdf")

    @app.route("/notifications")
    @login_required
    def notifications():
        items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
        db.session.commit()
        return render_template("notifications.html", notifications=items)

    @app.post("/notifications/read-all")
    @login_required
    def notifications_read_all():
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
        db.session.commit()
        return redirect(url_for("notifications"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        stats = {
            "users": User.query.count(),
            "artworks": Artwork.query.count(),
            "pending_artworks": Artwork.query.filter_by(status="pending").count(),
            "sold": Artwork.query.filter_by(is_sold=True).count(),
            "reports": Report.query.filter_by(status="pending").count(),
            "attacks": Attack.query.count(),
            "revenue": db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(Order.status != "cancelled").scalar(),
        }
        pending = Artwork.query.filter_by(status="pending").order_by(Artwork.created_at.asc()).limit(8).all()
        recent_reports = Report.query.filter_by(status="pending").order_by(Report.created_at.desc()).limit(6).all()
        team_counts = dict(db.session.query(User.team, func.count(User.id)).group_by(User.team).all())
        return render_template("admin_dashboard.html", stats=stats, pending=pending, recent_reports=recent_reports, team_counts=team_counts)

    @app.route("/admin/artworks")
    @admin_required
    def admin_artworks():
        status = request.args.get("status", "pending")
        query = Artwork.query
        if status in {"pending", "approved", "rejected"}:
            query = query.filter_by(status=status)
        return render_template("admin_artworks.html", artworks=query.order_by(Artwork.created_at.desc()).all(), active_status=status)

    @app.post("/admin/artworks/<int:artwork_id>/moderate")
    @admin_required
    def moderate_artwork(artwork_id):
        artwork = db.get_or_404(Artwork, artwork_id)
        action = request.form.get("action")
        if action not in {"approve", "reject"}:
            abort(400)
        artwork.status = "approved" if action == "approve" else "rejected"
        artwork.rejection_reason = request.form.get("reason", "").strip()[:255] if action == "reject" else ""
        add_notification(artwork.owner, f"Artwork {artwork.status}", f"“{artwork.title}” was {artwork.status}." + (f" Reason: {artwork.rejection_reason}" if artwork.rejection_reason else ""), "moderation", url_for("dashboard"))
        db.session.commit()
        flash(f"Artwork {artwork.status}.", "success")
        return redirect(request.referrer or url_for("admin_artworks"))

    @app.route("/admin/reports")
    @admin_required
    def admin_reports():
        reports = Report.query.order_by(Report.status.asc(), Report.created_at.desc()).all()
        return render_template("admin_reports.html", reports=reports)

    @app.post("/admin/reports/<int:report_id>/resolve")
    @admin_required
    def admin_resolve_report(report_id):
        report = db.get_or_404(Report, report_id)
        report.status = "reviewed"
        db.session.commit()
        flash("Report marked reviewed.", "success")
        return redirect(url_for("admin_reports"))

    @app.post("/admin/reports/<int:report_id>/dismiss")
    @admin_required
    def admin_dismiss_report(report_id):
        report = db.get_or_404(Report, report_id)
        report.status = "dismissed"
        db.session.commit()
        flash("Report dismissed.", "success")
        return redirect(url_for("admin_reports"))

    @app.route("/admin/users")
    @admin_required
    def admin_users():
        q = request.args.get("q", "").strip()
        query = User.query
        if q:
            query = query.filter(or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
        return render_template("admin_users.html", users=query.order_by(User.created_at.desc()).all())

    @app.post("/admin/users/<int:user_id>/status")
    @admin_required
    def admin_user_status(user_id):
        user = db.get_or_404(User, user_id)
        if user.is_admin or user.id == current_user.id:
            abort(400)
        status = request.form.get("status")
        if status not in {"active", "suspended", "banned"}:
            abort(400)
        user.status = status
        add_notification(user, "Account status changed", f"Your account is now {status}.", "moderation")
        db.session.commit()
        flash(f"{user.username} is now {status}.", "success")
        return redirect(url_for("admin_users"))

    @app.post("/admin/toggle-ban/<int:user_id>")
    @admin_required
    def admin_toggle_ban(user_id):
        user = db.get_or_404(User, user_id)
        user.status = "active" if user.status == "banned" else "banned"
        db.session.commit()
        return redirect(url_for("admin_users"))

    @app.post("/admin/delete-user/<int:user_id>")
    @admin_required
    def admin_delete_user(user_id):
        user = db.get_or_404(User, user_id)
        if user.is_admin:
            abort(400)
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "success")
        return redirect(url_for("admin_users"))

    @app.errorhandler(CSRFError)
    def handle_csrf(error):
        flash("That form expired. Please try again.", "danger")
        return redirect(request.referrer or url_for("index"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.cli.command("init-db")
    def init_db_command():
        db.create_all()
        print("Database tables created.")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        db.create_all()
        if User.query.count():
            print("Seed skipped: users already exist.")
            return
        admin = User(username="admin", email="admin@artattack.local", role="artist", team="Eldians", is_admin=True)
        admin.set_password("Admin123!")
        eldia = User(username="NovaInk", email="nova@artattack.local", role="artist", team="Eldians", bio="Dreamlike worlds, bright pigments, and character stories.")
        eldia.set_password("Artist123!")
        marley = User(username="RookCanvas", email="rook@artattack.local", role="artist", team="Marleyans", bio="Painter of strange creatures and quiet city nights.")
        marley.set_password("Artist123!")
        member = User(username="ArminReader", email="member@artattack.local", role="member", team="Eldians", bio="Collector, critic, and friendly rival.")
        member.set_password("Member123!")
        db.session.add_all([admin, eldia, marley, member])
        db.session.flush()
        arts = [
            Artwork(owner_id=eldia.id, title="Saffron Orbit", description="A bright orbital garden drifting over a sleeping city.", image_path="demo-saffron.svg", category="Illustration", medium="Digital", tags="space, city, vibrant", price=Decimal("6800"), for_sale=True, status="approved"),
            Artwork(owner_id=marley.id, title="Night Market Familiar", description="A curious creature guards the last lantern in the market.", image_path="demo-familiar.svg", category="Digital", medium="Digital painting", tags="creature, night, fantasy", price=Decimal("5200"), for_sale=True, status="approved"),
            Artwork(owner_id=eldia.id, title="Blue Hour Bloom", description="Botanical shapes unfold between dusk and dawn.", image_path="demo-bloom.svg", category="Painting", medium="Gouache", tags="floral, abstract, blue", price=Decimal("4100"), for_sale=True, status="approved"),
            Artwork(owner_id=marley.id, title="Signal Through Rain", description="A distant train sends warm signals through a violet storm.", image_path="demo-signal.svg", category="Illustration", medium="Ink and digital", tags="rain, train, atmospheric", price=Decimal("7500"), for_sale=True, status="approved"),
        ]
        db.session.add_all(arts)
        db.session.flush()
        db.session.add_all([
            Character(owner_id=eldia.id, name="Mira Sol", pronouns="she/they", description="A cartographer who maps impossible skies.", image_path="character-mira.svg"),
            Character(owner_id=marley.id, name="Bramble", pronouns="he/him", description="A forest courier with a talent for finding lost things.", image_path="character-bramble.svg"),
        ])
        db.session.add_all([ArtworkLike(user_id=member.id, artwork_id=art.id) for art in arts[:3]])
        db.session.commit()
        print("Demo seeded. Admin: admin / Admin123!")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1")
