# Database design

Art Attack uses ten tables, all defined as SQLAlchemy models in [`app.py`](../app.py). The same schema runs on MySQL (production) and SQLite (local demo); `flask init-db` creates it with `db.create_all()`.

## ER diagram

```mermaid
erDiagram
    USERS ||--o{ ARTWORKS : owns
    USERS ||--o{ CHARACTERS : creates
    USERS ||--o{ ARTWORK_LIKES : gives
    ARTWORKS ||--o{ ARTWORK_LIKES : receives
    USERS ||--o{ ATTACKS : launches
    CHARACTERS ||--o{ ATTACKS : "is target of"
    USERS ||--o{ REPORTS : files
    USERS |o--o{ REPORTS : "is reported in"
    ARTWORKS |o--o{ REPORTS : "is reported in"
    USERS ||--o{ CART_ITEMS : "adds to cart"
    ARTWORKS ||--o{ CART_ITEMS : "sits in"
    USERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    ARTWORKS ||--o{ ORDER_ITEMS : "sold as"
    USERS ||--o{ ORDER_ITEMS : sells
    USERS ||--o{ NOTIFICATIONS : receives

    USERS {
        int id PK
        varchar username UK
        varchar email UK
        varchar password_hash
        varchar role "member | artist"
        varchar team "Eldians | Marleyans"
        text bio
        varchar profile_image
        varchar status "active | suspended | banned"
        bool is_admin
        datetime created_at
    }
    ARTWORKS {
        int id PK
        int owner_id FK
        varchar title
        text description
        varchar image_path
        varchar category
        varchar medium
        varchar tags
        decimal price
        bool for_sale
        bool is_sold
        varchar status "pending | approved | rejected"
        varchar rejection_reason
        datetime created_at
    }
    ARTWORK_LIKES {
        int id PK
        int user_id FK
        int artwork_id FK
        datetime created_at
    }
    CHARACTERS {
        int id PK
        int owner_id FK
        varchar name
        varchar pronouns
        text description
        varchar image_path
        datetime created_at
    }
    ATTACKS {
        int id PK
        int attacker_id FK
        int character_id FK
        varchar image_path
        text description
        int points "10, or 0 on friendly fire"
        bool friendly_fire
        datetime created_at
    }
    REPORTS {
        int id PK
        int reporter_id FK
        int artwork_id FK "nullable"
        int user_id FK "nullable"
        varchar reason
        text description
        varchar status "pending | reviewed | dismissed"
        datetime created_at
    }
    CART_ITEMS {
        int id PK
        int user_id FK
        int artwork_id FK
        datetime created_at
    }
    ORDERS {
        int id PK
        int buyer_id FK
        varchar reference UK
        varchar status
        decimal subtotal
        decimal delivery_fee
        decimal total
        varchar full_name
        varchar email
        varchar phone
        text address
        datetime created_at
    }
    ORDER_ITEMS {
        int id PK
        int order_id FK
        int artwork_id FK
        int seller_id FK
        varchar title
        decimal price
    }
    NOTIFICATIONS {
        int id PK
        int user_id FK
        varchar title
        text message
        varchar kind
        varchar link
        bool is_read
        datetime created_at
    }
```

## Constraints

### Unique keys

| Table | Columns | Purpose |
|---|---|---|
| `users` | `username` | One account per name |
| `users` | `email` | One account per email |
| `artwork_likes` | `(user_id, artwork_id)` | A user can like an artwork only once |
| `cart_items` | `(user_id, artwork_id)` | No duplicate cart entries |
| `orders` | `reference` | Human-readable order ID, e.g. `AA-260928-3F9A1C` |

### Foreign keys and delete rules

| Foreign key | References | On delete |
|---|---|---|
| `artworks.owner_id` | `users.id` | CASCADE |
| `characters.owner_id` | `users.id` | CASCADE |
| `artwork_likes.user_id` / `artwork_id` | `users.id` / `artworks.id` | CASCADE |
| `attacks.attacker_id` | `users.id` | CASCADE |
| `attacks.character_id` | `characters.id` | CASCADE |
| `reports.reporter_id` / `user_id` | `users.id` | CASCADE |
| `reports.artwork_id` | `artworks.id` | CASCADE |
| `cart_items.user_id` / `artwork_id` | `users.id` / `artworks.id` | CASCADE |
| `notifications.user_id` | `users.id` | CASCADE |
| `orders.buyer_id` | `users.id` | **RESTRICT** |
| `order_items.order_id` | `orders.id` | CASCADE |
| `order_items.artwork_id` | `artworks.id` | **RESTRICT** |
| `order_items.seller_id` | `users.id` | **RESTRICT** |

Sales records use RESTRICT, so a user or artwork that appears in an order can't be deleted and the purchase history stays intact. Everything else cascades with its owner.

`order_items` also copies the artwork's `title` and `price` at checkout, so the receipt still shows what was paid even if the artwork is edited later.

### Indexes

Besides primary keys and unique columns, these columns are indexed: `artworks.owner_id`, `artworks.status`, `artworks.created_at`, `characters.owner_id`, `attacks.attacker_id`, `attacks.character_id`, `reports.status`, `orders.buyer_id` and `notifications.user_id`. They back the most frequent queries: browsing approved artwork newest-first, loading a user's dashboard, and the moderation queues.

## Notable queries

| Feature | Query shape |
|---|---|
| Team scoreboard (home page) | `users` LEFT JOIN `attacks` on the attacker, `SUM(points)` grouped by `team` |
| Sort by popularity (browse) | Subquery counting `artwork_likes` per artwork, LEFT JOINed to `artworks` and ordered by the count |
| Seller revenue (dashboard) | `SUM(order_items.price)` JOIN `orders` where the seller matches and the order isn't cancelled |
| Platform revenue (admin) | `SUM(orders.total)` for non-cancelled orders |
| Attacks received (dashboard) | `attacks` JOIN `characters` where the character's owner is the current user |
