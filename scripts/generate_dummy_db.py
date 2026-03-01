"""Generate a dummy e-commerce SQLite database for testing KnowSQL."""

import sqlite3
import random
from datetime import datetime, timedelta

SEED = 42
DB_PATH = "dummy_ecommerce.db"

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank",
    "Ivy", "Jack", "Karen", "Leo", "Mona", "Nick", "Olivia", "Paul",
    "Quinn", "Rosa", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xavier",
    "Yara", "Zane", "Amy", "Ben", "Cora", "Dan", "Ella", "Finn",
    "Gina", "Hugh", "Iris", "Joel", "Kate", "Luke", "Mia", "Noah",
    "Opal", "Pete", "Rita", "Sean", "Tara", "Ugo", "Vera", "Will",
    "Xena", "Yuri",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Jackson", "White", "Harris", "Martin", "Thompson", "Moore", "Allen",
    "Young", "King", "Wright", "Scott", "Hill", "Green", "Adams", "Baker",
    "Nelson", "Carter", "Mitchell", "Perez", "Roberts", "Turner", "Phillips",
    "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Sanchez",
    "Morris", "Rogers", "Reed", "Cook", "Morgan", "Bell", "Murphy", "Bailey",
]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
    "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
    "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
    "Seattle", "Denver", "Boston", "Portland", "Miami",
]

STATES = [
    "NY", "CA", "IL", "TX", "AZ", "PA", "TX", "CA", "TX", "CA",
    "TX", "FL", "TX", "OH", "NC", "WA", "CO", "MA", "OR", "FL",
]

REGIONS = ["Northeast", "West", "Midwest", "South", "Southwest"]

STREETS = [
    "Main St", "Oak Ave", "Pine Rd", "Maple Dr", "Cedar Ln",
    "Elm St", "Park Ave", "Lake Rd", "Hill Dr", "River Ln",
]

PRODUCT_NAMES = [
    "Wireless Mouse", "Mechanical Keyboard", "USB-C Hub", "Monitor Stand",
    "Webcam HD", "Noise Cancelling Headphones", "Laptop Stand", "Desk Lamp",
    "External SSD 1TB", "Bluetooth Speaker", "Ergonomic Chair", "Standing Desk",
    "Cable Management Kit", "Power Strip", "Screen Protector", "Mouse Pad XL",
    "Phone Charger", "HDMI Cable 6ft", "Ethernet Cable 10ft", "USB Flash Drive 64GB",
    "Tablet Stylus", "Drawing Tablet", "Portable Charger", "Smart Plug",
    "LED Strip Lights", "Ring Light", "Microphone USB", "Headphone Stand",
    "Keyboard Wrist Rest", "Monitor Light Bar", "Wireless Earbuds", "Smart Watch",
    "Fitness Tracker", "Running Shoes", "Yoga Mat", "Water Bottle",
    "Backpack", "Messenger Bag", "Sunglasses", "Umbrella",
    "Coffee Maker", "Tea Kettle", "Blender", "Toaster",
    "Cutting Board", "Chef Knife", "Mixing Bowl Set", "Measuring Cups",
    "Frying Pan", "Saucepan",
]

CATEGORIES = [
    ("Electronics", None),
    ("Computer Accessories", "Electronics"),
    ("Audio", "Electronics"),
    ("Office Furniture", None),
    ("Cables & Adapters", "Electronics"),
    ("Wearables", "Electronics"),
    ("Sports & Fitness", None),
    ("Kitchen", None),
    ("Bags & Accessories", None),
    ("Home & Living", None),
]

PRODUCT_CATEGORY_MAP = {
    "Wireless Mouse": "Computer Accessories",
    "Mechanical Keyboard": "Computer Accessories",
    "USB-C Hub": "Computer Accessories",
    "Monitor Stand": "Office Furniture",
    "Webcam HD": "Computer Accessories",
    "Noise Cancelling Headphones": "Audio",
    "Laptop Stand": "Office Furniture",
    "Desk Lamp": "Office Furniture",
    "External SSD 1TB": "Electronics",
    "Bluetooth Speaker": "Audio",
    "Ergonomic Chair": "Office Furniture",
    "Standing Desk": "Office Furniture",
    "Cable Management Kit": "Cables & Adapters",
    "Power Strip": "Electronics",
    "Screen Protector": "Computer Accessories",
    "Mouse Pad XL": "Computer Accessories",
    "Phone Charger": "Cables & Adapters",
    "HDMI Cable 6ft": "Cables & Adapters",
    "Ethernet Cable 10ft": "Cables & Adapters",
    "USB Flash Drive 64GB": "Electronics",
    "Tablet Stylus": "Computer Accessories",
    "Drawing Tablet": "Electronics",
    "Portable Charger": "Electronics",
    "Smart Plug": "Home & Living",
    "LED Strip Lights": "Home & Living",
    "Ring Light": "Electronics",
    "Microphone USB": "Audio",
    "Headphone Stand": "Audio",
    "Keyboard Wrist Rest": "Computer Accessories",
    "Monitor Light Bar": "Office Furniture",
    "Wireless Earbuds": "Audio",
    "Smart Watch": "Wearables",
    "Fitness Tracker": "Wearables",
    "Running Shoes": "Sports & Fitness",
    "Yoga Mat": "Sports & Fitness",
    "Water Bottle": "Sports & Fitness",
    "Backpack": "Bags & Accessories",
    "Messenger Bag": "Bags & Accessories",
    "Sunglasses": "Bags & Accessories",
    "Umbrella": "Bags & Accessories",
    "Coffee Maker": "Kitchen",
    "Tea Kettle": "Kitchen",
    "Blender": "Kitchen",
    "Toaster": "Kitchen",
    "Cutting Board": "Kitchen",
    "Chef Knife": "Kitchen",
    "Mixing Bowl Set": "Kitchen",
    "Measuring Cups": "Kitchen",
    "Frying Pan": "Kitchen",
    "Saucepan": "Kitchen",
}

DEPARTMENTS = [
    ("Sales", "Revenue generation and customer relations"),
    ("Engineering", "Product development and technical operations"),
    ("Marketing", "Brand awareness and customer acquisition"),
    ("Support", "Customer service and issue resolution"),
    ("Operations", "Logistics and supply chain management"),
]

REVIEW_TEXTS = [
    "Great product, exactly what I needed!",
    "Good quality for the price.",
    "Arrived on time and works perfectly.",
    "Decent but could be better.",
    "Not what I expected, returning it.",
    "Excellent build quality.",
    "Works as described.",
    "Would recommend to others.",
    "Average product, nothing special.",
    "Love it! Best purchase this year.",
    "Solid construction and fast shipping.",
    "A bit overpriced for what it is.",
    "Perfect for my home office setup.",
    "Stopped working after a week.",
    "Exceeded my expectations!",
]

PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "bank_transfer", "apple_pay"]
ORDER_STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]
SHIPPING_STATUSES = ["label_created", "picked_up", "in_transit", "out_for_delivery", "delivered", "delayed"]
RETURN_STATUSES = ["requested", "approved", "received", "refunded", "rejected"]
COUPON_STATUSES = ["active", "expired", "used", "disabled"]
CARRIERS = ["UPS", "FedEx", "USPS", "DHL"]
SEGMENT_NAMES = ["VIP", "Regular", "New", "At-Risk", "Churned"]
TAG_NAMES = [
    "bestseller", "new-arrival", "sale", "eco-friendly", "premium",
    "budget", "trending", "limited-edition", "gift-idea", "clearance",
]


def create_tables(conn: sqlite3.Connection):
    """Create all 18 tables and 2 views."""
    c = conn.cursor()

    c.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            region TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            street TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip_code TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            address_type TEXT DEFAULT 'shipping'
        )
    """)

    c.execute("""
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            parent_category_id INTEGER REFERENCES categories(id),
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT UNIQUE NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            price REAL NOT NULL,
            cost REAL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            department_id INTEGER REFERENCES departments(id),
            hire_date DATE NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending',
            total_amount REAL NOT NULL,
            discount_amount REAL DEFAULT 0,
            notes TEXT
        )
    """)

    c.execute("""
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            invoice_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            due_date TIMESTAMP,
            total_amount REAL NOT NULL,
            tax_amount REAL DEFAULT 0,
            net_total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            paid_at TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id),
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'completed',
            transaction_ref TEXT
        )
    """)

    c.execute("""
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE wishlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_percent REAL,
            discount_fixed REAL,
            min_order_amount REAL DEFAULT 0,
            max_uses INTEGER,
            times_used INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            valid_from TIMESTAMP,
            valid_until TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE shipping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            carrier TEXT NOT NULL,
            tracking_number TEXT,
            status TEXT NOT NULL DEFAULT 'label_created',
            shipped_at TIMESTAMP,
            estimated_delivery TIMESTAMP,
            delivered_at TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity_on_hand INTEGER NOT NULL DEFAULT 0,
            reorder_level INTEGER DEFAULT 10,
            warehouse_location TEXT,
            last_restocked TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            order_item_id INTEGER NOT NULL REFERENCES order_items(id),
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'requested',
            refund_amount REAL,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)

    # Tables WITHOUT FK constraints (test implicit relationship detection)
    c.execute("""
        CREATE TABLE customer_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            segment_name TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            score REAL
        )
    """)

    c.execute("""
        CREATE TABLE product_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            tag_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Views
    c.execute("""
        CREATE VIEW revenue_summary AS
        SELECT
            strftime('%Y-%m', o.order_date) AS month,
            COUNT(DISTINCT o.id) AS order_count,
            SUM(o.total_amount) AS gross_revenue,
            SUM(o.discount_amount) AS total_discounts,
            SUM(o.total_amount - o.discount_amount) AS net_revenue,
            COUNT(DISTINCT o.customer_id) AS unique_customers
        FROM orders o
        WHERE o.status != 'cancelled'
        GROUP BY strftime('%Y-%m', o.order_date)
    """)

    c.execute("""
        CREATE VIEW customer_lifetime_value AS
        SELECT
            c.id AS customer_id,
            c.first_name || ' ' || c.last_name AS customer_name,
            c.email,
            c.region,
            COUNT(DISTINCT o.id) AS total_orders,
            COALESCE(SUM(o.total_amount), 0) AS total_spent,
            COALESCE(AVG(o.total_amount), 0) AS avg_order_value,
            MIN(o.order_date) AS first_order_date,
            MAX(o.order_date) AS last_order_date
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id AND o.status != 'cancelled'
        GROUP BY c.id
    """)

    conn.commit()


def populate_data(conn: sqlite3.Connection):
    """Populate tables with realistic test data."""
    rng = random.Random(SEED)
    c = conn.cursor()

    # Customers (~100)
    customers = []
    for i in range(100):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        phone = f"555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"
        region = rng.choice(REGIONS)
        created = datetime(2023, 1, 1) + timedelta(days=rng.randint(0, 700))
        is_active = 1 if rng.random() > 0.1 else 0
        customers.append((fn, ln, email, phone, region, created.isoformat(), is_active))

    c.executemany(
        "INSERT INTO customers (first_name, last_name, email, phone, region, created_at, is_active) VALUES (?,?,?,?,?,?,?)",
        customers,
    )

    # Addresses (1-2 per customer)
    addresses = []
    for cid in range(1, 101):
        num_addr = rng.choice([1, 1, 1, 2])
        for j in range(num_addr):
            idx = rng.randint(0, len(CITIES) - 1)
            street = f"{rng.randint(100, 9999)} {rng.choice(STREETS)}"
            zipcode = f"{rng.randint(10000, 99999)}"
            atype = "shipping" if j == 0 else rng.choice(["shipping", "billing"])
            addresses.append((cid, street, CITIES[idx], STATES[idx], zipcode, 1 if j == 0 else 0, atype))
    c.executemany(
        "INSERT INTO addresses (customer_id, street, city, state, zip_code, is_default, address_type) VALUES (?,?,?,?,?,?,?)",
        addresses,
    )

    # Categories
    cat_ids = {}
    for name, parent in CATEGORIES:
        parent_id = cat_ids.get(parent)
        desc = f"Products in the {name} category"
        c.execute("INSERT INTO categories (name, parent_category_id, description) VALUES (?,?,?)", (name, parent_id, desc))
        cat_ids[name] = c.lastrowid

    # Products (50)
    products = []
    for i, pname in enumerate(PRODUCT_NAMES):
        sku = f"SKU-{i+1:04d}"
        cat_name = PRODUCT_CATEGORY_MAP.get(pname, "Electronics")
        cat_id = cat_ids.get(cat_name, 1)
        price = round(rng.uniform(9.99, 499.99), 2)
        cost = round(price * rng.uniform(0.3, 0.7), 2)
        desc = f"High quality {pname.lower()} for everyday use"
        products.append((pname, sku, cat_id, price, cost, desc, 1))
    c.executemany(
        "INSERT INTO products (name, sku, category_id, price, cost, description, is_active, created_at) VALUES (?,?,?,?,?,?,?, CURRENT_TIMESTAMP)",
        products,
    )

    # Departments and Staff
    dept_ids = {}
    for dname, ddesc in DEPARTMENTS:
        c.execute("INSERT INTO departments (name, description) VALUES (?,?)", (dname, ddesc))
        dept_ids[dname] = c.lastrowid

    staff = []
    for i in range(20):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        email = f"{fn.lower()}.{ln.lower()}.staff{i}@knowsql.com"
        dept_id = dept_ids[rng.choice(list(dept_ids.keys()))]
        hire_date = (datetime(2020, 1, 1) + timedelta(days=rng.randint(0, 1500))).strftime("%Y-%m-%d")
        staff.append((fn, ln, email, dept_id, hire_date, 1))
    c.executemany(
        "INSERT INTO staff (first_name, last_name, email, department_id, hire_date, is_active) VALUES (?,?,?,?,?,?)",
        staff,
    )

    # Coupons
    coupon_codes = []
    for i in range(15):
        code = f"SAVE{rng.randint(5,50)}-{chr(65+i)}"
        disc_pct = rng.choice([None, 10, 15, 20, 25, 30])
        disc_fix = round(rng.uniform(5, 50), 2) if disc_pct is None else None
        min_order = round(rng.uniform(0, 100), 2)
        max_uses = rng.choice([None, 50, 100, 200])
        times_used = rng.randint(0, max_uses or 100)
        status = rng.choice(COUPON_STATUSES)
        vfrom = (datetime(2024, 1, 1) + timedelta(days=rng.randint(0, 200))).isoformat()
        vuntil = (datetime(2025, 1, 1) + timedelta(days=rng.randint(0, 365))).isoformat()
        coupon_codes.append((code, disc_pct, disc_fix, min_order, max_uses, times_used, status, vfrom, vuntil))
    c.executemany(
        "INSERT INTO coupons (code, discount_percent, discount_fixed, min_order_amount, max_uses, times_used, status, valid_from, valid_until) VALUES (?,?,?,?,?,?,?,?,?)",
        coupon_codes,
    )

    # Orders (~500)
    base_date = datetime(2024, 1, 1)
    order_data = []
    for i in range(500):
        cid = rng.randint(1, 100)
        order_date = base_date + timedelta(days=rng.randint(0, 400), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        status = rng.choice(ORDER_STATUSES)
        total = 0.0  # will update after items
        discount = round(rng.uniform(0, 20), 2) if rng.random() > 0.7 else 0
        notes = rng.choice([None, None, None, "Rush order", "Gift wrapping requested", "Leave at door"])
        order_data.append((cid, order_date.isoformat(), status, total, discount, notes))

    c.executemany(
        "INSERT INTO orders (customer_id, order_date, status, total_amount, discount_amount, notes) VALUES (?,?,?,?,?,?)",
        order_data,
    )

    # Order Items (~1500, 1-5 per order)
    order_items = []
    order_totals = {}
    for oid in range(1, 501):
        num_items = rng.randint(1, 5)
        total = 0.0
        for _ in range(num_items):
            pid = rng.randint(1, 50)
            qty = rng.randint(1, 3)
            # Get product price
            c.execute("SELECT price FROM products WHERE id = ?", (pid,))
            unit_price = c.fetchone()[0]
            subtotal = round(unit_price * qty, 2)
            total += subtotal
            order_items.append((oid, pid, qty, unit_price, subtotal))
        order_totals[oid] = round(total, 2)

    c.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES (?,?,?,?,?)",
        order_items,
    )

    # Update order totals
    for oid, total in order_totals.items():
        c.execute("UPDATE orders SET total_amount = ? WHERE id = ?", (total, oid))

    # Invoices (one per non-cancelled order)
    invoices = []
    c.execute("SELECT id, order_date, total_amount, discount_amount, status FROM orders")
    for oid, odate, total, discount, ostatus in c.fetchall():
        if ostatus == "cancelled":
            continue
        inv_date = odate
        due_date = (datetime.fromisoformat(odate) + timedelta(days=30)).isoformat()
        tax = round(total * 0.08, 2)
        net = round(total + tax - discount, 2)
        inv_status = "paid" if ostatus in ("delivered", "shipped") else "pending"
        paid_at = odate if inv_status == "paid" else None
        invoices.append((oid, inv_date, due_date, total, tax, net, inv_status, paid_at))

    c.executemany(
        "INSERT INTO invoices (order_id, invoice_date, due_date, total_amount, tax_amount, net_total, status, paid_at) VALUES (?,?,?,?,?,?,?,?)",
        invoices,
    )

    # Payments (one per paid invoice)
    payments = []
    c.execute("SELECT id, net_total, invoice_date FROM invoices WHERE status = 'paid'")
    for inv_id, amount, inv_date in c.fetchall():
        method = rng.choice(PAYMENT_METHODS)
        ref = f"TXN-{rng.randint(100000, 999999)}"
        payments.append((inv_id, amount, method, inv_date, "completed", ref))

    c.executemany(
        "INSERT INTO payments (invoice_id, amount, payment_method, payment_date, status, transaction_ref) VALUES (?,?,?,?,?,?)",
        payments,
    )

    # Reviews (~200)
    reviews = []
    reviewed = set()
    for _ in range(200):
        pid = rng.randint(1, 50)
        cid = rng.randint(1, 100)
        key = (pid, cid)
        if key in reviewed:
            continue
        reviewed.add(key)
        rating = rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 20, 35, 30])[0]
        text = rng.choice(REVIEW_TEXTS)
        created = (datetime(2024, 3, 1) + timedelta(days=rng.randint(0, 300))).isoformat()
        reviews.append((pid, cid, rating, text, created))

    c.executemany(
        "INSERT INTO reviews (product_id, customer_id, rating, review_text, created_at) VALUES (?,?,?,?,?)",
        reviews,
    )

    # Wishlists
    wishlists = []
    wishlisted = set()
    for _ in range(150):
        cid = rng.randint(1, 100)
        pid = rng.randint(1, 50)
        key = (cid, pid)
        if key in wishlisted:
            continue
        wishlisted.add(key)
        added = (datetime(2024, 1, 1) + timedelta(days=rng.randint(0, 400))).isoformat()
        wishlists.append((cid, pid, added))
    c.executemany(
        "INSERT INTO wishlists (customer_id, product_id, added_at) VALUES (?,?,?)",
        wishlists,
    )

    # Shipping (one per shipped/delivered order)
    shipments = []
    c.execute("SELECT id, order_date, status FROM orders WHERE status IN ('shipped', 'delivered')")
    for oid, odate, ostatus in c.fetchall():
        carrier = rng.choice(CARRIERS)
        tracking = f"{carrier[0]}{rng.randint(1000000000, 9999999999)}"
        ship_status = "delivered" if ostatus == "delivered" else rng.choice(["in_transit", "out_for_delivery", "delayed"])
        shipped_at = (datetime.fromisoformat(odate) + timedelta(days=rng.randint(1, 3))).isoformat()
        est_delivery = (datetime.fromisoformat(odate) + timedelta(days=rng.randint(3, 10))).isoformat()
        delivered_at = (datetime.fromisoformat(odate) + timedelta(days=rng.randint(3, 10))).isoformat() if ship_status == "delivered" else None
        shipments.append((oid, carrier, tracking, ship_status, shipped_at, est_delivery, delivered_at))

    c.executemany(
        "INSERT INTO shipping (order_id, carrier, tracking_number, status, shipped_at, estimated_delivery, delivered_at) VALUES (?,?,?,?,?,?,?)",
        shipments,
    )

    # Inventory (one per product)
    inventory = []
    for pid in range(1, 51):
        qty = rng.randint(0, 200)
        reorder = rng.choice([5, 10, 15, 20])
        warehouse = rng.choice(["A1", "A2", "B1", "B2", "C1"])
        restocked = (datetime(2024, 10, 1) + timedelta(days=rng.randint(0, 100))).isoformat()
        inventory.append((pid, qty, reorder, warehouse, restocked))
    c.executemany(
        "INSERT INTO inventory (product_id, quantity_on_hand, reorder_level, warehouse_location, last_restocked) VALUES (?,?,?,?,?)",
        inventory,
    )

    # Returns (~50)
    returns = []
    c.execute("SELECT oi.id, oi.order_id, oi.unit_price, oi.quantity FROM order_items oi JOIN orders o ON oi.order_id = o.id WHERE o.status = 'delivered' ORDER BY RANDOM() LIMIT 50")
    for oi_id, oid, unit_price, qty in c.fetchall():
        reason = rng.choice(["Defective", "Wrong item", "Changed mind", "Not as described", "Too late"])
        status = rng.choice(RETURN_STATUSES)
        refund = round(unit_price * qty, 2) if status in ("approved", "refunded") else None
        requested = (datetime(2024, 6, 1) + timedelta(days=rng.randint(0, 200))).isoformat()
        resolved = (datetime.fromisoformat(requested) + timedelta(days=rng.randint(1, 14))).isoformat() if status in ("refunded", "rejected") else None
        returns.append((oid, oi_id, reason, status, refund, requested, resolved))

    c.executemany(
        "INSERT INTO returns (order_id, order_item_id, reason, status, refund_amount, requested_at, resolved_at) VALUES (?,?,?,?,?,?,?)",
        returns,
    )

    # Customer Segments (NO FK -- intentional)
    segments = []
    for cid in range(1, 101):
        seg = rng.choice(SEGMENT_NAMES)
        score = round(rng.uniform(0, 100), 1)
        assigned = (datetime(2024, 6, 1) + timedelta(days=rng.randint(0, 200))).isoformat()
        segments.append((cid, seg, assigned, score))
    c.executemany(
        "INSERT INTO customer_segments (customer_id, segment_name, assigned_at, score) VALUES (?,?,?,?)",
        segments,
    )

    # Product Tags (NO FK -- intentional)
    tags = []
    tagged = set()
    for pid in range(1, 51):
        num_tags = rng.randint(1, 3)
        for _ in range(num_tags):
            tag = rng.choice(TAG_NAMES)
            key = (pid, tag)
            if key in tagged:
                continue
            tagged.add(key)
            created = (datetime(2024, 1, 1) + timedelta(days=rng.randint(0, 300))).isoformat()
            tags.append((pid, tag, created))
    c.executemany(
        "INSERT INTO product_tags (product_id, tag_name, created_at) VALUES (?,?,?)",
        tags,
    )

    conn.commit()


def main():
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    populate_data(conn)

    # Print summary
    cursor = conn.cursor()
    print(f"Database created: {DB_PATH}")
    print()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Tables ({len(tables)}):")
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM [{t}]")
        count = cursor.fetchone()[0]
        print(f"  {t}: {count} rows")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
    views = [r[0] for r in cursor.fetchall()]
    print(f"\nViews ({len(views)}):")
    for v in views:
        cursor.execute(f"SELECT COUNT(*) FROM [{v}]")
        count = cursor.fetchone()[0]
        print(f"  {v}: {count} rows")

    conn.close()


if __name__ == "__main__":
    main()
