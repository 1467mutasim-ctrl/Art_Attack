import io
from decimal import Decimal

from PIL import Image

from app import Artwork, Character, Notification, User, create_app, db


def image_file(name="test.png"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "#f15b47").save(stream, format="PNG")
    stream.seek(0)
    return stream, name


def make_app():
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret",
    })
    with app.app_context():
        db.create_all()
        admin = User(username="admin", email="admin@test.local", role="artist", team="Eldians", is_admin=True)
        admin.set_password("Password1!")
        artist = User(username="artist", email="artist@test.local", role="artist", team="Eldians")
        artist.set_password("Password1!")
        rival = User(username="rival", email="rival@test.local", role="artist", team="Marleyans")
        rival.set_password("Password1!")
        buyer = User(username="buyer", email="buyer@test.local", role="member", team="Eldians")
        buyer.set_password("Password1!")
        db.session.add_all([admin, artist, rival, buyer])
        db.session.flush()
        art = Artwork(owner_id=artist.id, title="Test Art", image_path="demo-saffron.svg", category="Digital", price=Decimal("1000"), for_sale=True, status="approved")
        character = Character(owner_id=artist.id, name="Friendly Target", image_path="character-mira.svg")
        db.session.add_all([art, character])
        db.session.commit()
    return app


def login(client, identity, password="Password1!"):
    return client.post("/login", data={"identity": identity, "password": password}, follow_redirects=True)


def test_guest_pages_render():
    app = make_app()
    client = app.test_client()
    for path in ["/", "/browse", "/browse?q=Nova&team=Eldians&sort=popular", "/characters", "/login", "/register", "/artwork/1", "/characters/1"]:
        response = client.get(path)
        assert response.status_code == 200, path


def test_artist_dashboard_like_and_friendly_fire_mailbox():
    app = make_app()
    client = app.test_client()
    login(client, "buyer")
    assert client.post("/artwork/1/like", follow_redirects=True).status_code == 200
    payload = {"description": "A friendly challenge", "image": image_file()}
    response = client.post("/characters/1/attack", data=payload, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    assert b"Friendly fire" in response.data
    with app.app_context():
        assert Notification.query.filter_by(title="Friendly fire warning").count() == 2


def test_cart_checkout_and_pdf_receipt():
    app = make_app()
    client = app.test_client()
    login(client, "buyer")
    assert client.post("/cart/add/1", follow_redirects=True).status_code == 200
    response = client.post("/checkout", data={"full_name": "Buyer One", "email": "buyer@test.local", "phone": "01700000000", "address": "Dhaka, Bangladesh"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"AA-" in response.data
    receipt = client.get("/orders/1/receipt.pdf")
    assert receipt.status_code == 200
    assert receipt.mimetype == "application/pdf"
    assert receipt.data.startswith(b"%PDF")


def test_admin_can_approve_pending_artwork_and_suspend_user():
    app = make_app()
    with app.app_context():
        artist = User.query.filter_by(username="rival").first()
        db.session.add(Artwork(owner_id=artist.id, title="Pending", image_path="demo-signal.svg", category="Illustration", status="pending"))
        db.session.commit()
    client = app.test_client()
    login(client, "admin")
    for path in ["/admin", "/admin/artworks", "/admin/reports", "/admin/users", "/notifications"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/dashboard").status_code == 302
    response = client.post("/admin/artworks/2/moderate", data={"action": "approve"}, follow_redirects=True)
    assert response.status_code == 200
    response = client.post("/admin/users/4/status", data={"status": "suspended"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Artwork, 2).status == "approved"
        assert db.session.get(User, 4).status == "suspended"


def test_all_templates_compile():
    app = make_app()
    with app.app_context():
        for template_name in app.jinja_env.list_templates():
            app.jinja_env.get_template(template_name)
