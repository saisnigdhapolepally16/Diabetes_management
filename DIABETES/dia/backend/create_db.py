"""
╔══════════════════════════════════════════════════════╗
║         DIABETRIX — create_db.py                     ║
║         Run this ONCE to set up the database         ║
║         with 3 test users and sample data            ║
║                                                      ║
║  Run:  python create_db.py                           ║
║  Place this file inside the  backend/  folder        ║
╚══════════════════════════════════════════════════════╝
"""

import sqlite3
import hashlib
import uuid
import os
from datetime import datetime, timedelta
import random

# ── Config ─────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'diabetrix.db')

# ── Helpers ────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def new_id():
    return str(uuid.uuid4())

def days_ago(n, hour=8, minute=0):
    """Return ISO timestamp for N days ago at a given hour."""
    dt = datetime.utcnow() - timedelta(days=n)
    return dt.replace(hour=hour, minute=minute, second=0).isoformat()

def classify(v):
    if v < 70:   return 'Hypoglycemia'
    if v < 100:  return 'Normal'
    if v < 126:  return 'Pre-diabetic'
    if v < 300:  return 'Diabetic'
    return 'Critical'


# ══════════════════════════════════════════════════════
#  SCHEMA — same as app.py
# ══════════════════════════════════════════════════════
def create_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS profiles (
            user_id        TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            age            INTEGER,
            gender         TEXT,
            weight_kg      REAL,
            height_cm      REAL,
            lifestyle      TEXT DEFAULT 'sedentary',
            dtype          TEXT DEFAULT 'type2',
            diagnosed_year INTEGER,
            target_low     INTEGER DEFAULT 80,
            target_high    INTEGER DEFAULT 140,
            doctor_name    TEXT,
            allergies      TEXT,
            meds_text      TEXT,
            step_goal      INTEGER DEFAULT 8000,
            steps_today    INTEGER DEFAULT 0,
            updated_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS glucose_readings (
            id             TEXT PRIMARY KEY,
            user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            value          INTEGER NOT NULL,
            meal_context   TEXT DEFAULT 'fasting',
            note           TEXT DEFAULT '',
            classification TEXT,
            recorded_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS medications (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            dose        TEXT NOT NULL,
            time_of_day TEXT DEFAULT '08:00',
            frequency   TEXT DEFAULT 'Once daily',
            is_done     INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            phone        TEXT NOT NULL,
            relationship TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS safety_log (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            log_type   TEXT NOT NULL,
            message    TEXT NOT NULL,
            logged_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    print("✅  Tables created.")


# ══════════════════════════════════════════════════════
#  TEST USERS
#  Login with:  email + password shown below
# ══════════════════════════════════════════════════════
USERS = [
    {
        "name":     "Arjun Sharma",
        "email":    "arjun@test.com",
        "password": "test123",        # ← login password
        "profile": {
            "age": 45, "gender": "male", "weight_kg": 82.0, "height_cm": 172.0,
            "lifestyle": "sedentary", "dtype": "type2", "diagnosed_year": 2019,
            "target_low": 80, "target_high": 140,
            "doctor_name": "Dr. Ramesh Kumar",
            "allergies": "None", "meds_text": "Metformin 500mg",
            "step_goal": 8000, "steps_today": 4200,
        },
        "medications": [
            {"name": "Metformin",  "dose": "500mg", "time_of_day": "08:00", "frequency": "Twice daily"},
            {"name": "Glipizide", "dose": "5mg",   "time_of_day": "07:30", "frequency": "Once daily"},
        ],
        "contacts": [
            {"name": "Priya Sharma",  "phone": "+91 98765 43210", "relationship": "Spouse"},
            {"name": "Dr. Ramesh Kumar", "phone": "+91 99887 76655", "relationship": "Doctor"},
        ],
        # Glucose readings: last 14 days, Type 2 range (slightly high)
        "glucose_values": [148, 162, 135, 158, 170, 145, 152, 138, 165, 142, 155, 168, 140, 158],
        "meals":          ["fasting","after_meal","fasting","after_meal","before_meal",
                           "fasting","after_meal","fasting","after_meal","bedtime",
                           "fasting","after_meal","fasting","before_meal"],
    },
    {
        "name":     "Meena Patel",
        "email":    "meena@test.com",
        "password": "test123",
        "profile": {
            "age": 32, "gender": "female", "weight_kg": 65.0, "height_cm": 158.0,
            "lifestyle": "moderate", "dtype": "type1", "diagnosed_year": 2015,
            "target_low": 70, "target_high": 130,
            "doctor_name": "Dr. Anjali Mehta",
            "allergies": "Penicillin", "meds_text": "Insulin (Lantus)",
            "step_goal": 9000, "steps_today": 7800,
        },
        "medications": [
            {"name": "Insulin Lantus",  "dose": "20 units", "time_of_day": "22:00", "frequency": "Once daily"},
            {"name": "Insulin NovoRapid","dose": "8 units", "time_of_day": "08:00", "frequency": "With meals"},
        ],
        "contacts": [
            {"name": "Raj Patel",       "phone": "+91 97654 32109", "relationship": "Husband"},
            {"name": "Dr. Anjali Mehta","phone": "+91 98001 23456", "relationship": "Doctor"},
        ],
        # Well-controlled Type 1
        "glucose_values": [98, 112, 88, 125, 105, 95, 118, 102, 110, 92, 108, 115, 96, 122],
        "meals":          ["fasting","after_meal","bedtime","after_meal","before_meal",
                           "fasting","after_meal","fasting","after_meal","bedtime",
                           "fasting","after_meal","fasting","before_meal"],
    },
    {
        "name":     "Suresh Nair",
        "email":    "suresh@test.com",
        "password": "test123",
        "profile": {
            "age": 58, "gender": "male", "weight_kg": 91.0, "height_cm": 168.0,
            "lifestyle": "sedentary", "dtype": "prediabetes", "diagnosed_year": 2022,
            "target_low": 80, "target_high": 140,
            "doctor_name": "Dr. Srinivas Rao",
            "allergies": "Sulfa drugs", "meds_text": "None",
            "step_goal": 6000, "steps_today": 2100,
        },
        "medications": [
            {"name": "Vitamin D3",  "dose": "60000 IU", "time_of_day": "09:00", "frequency": "Once weekly"},
            {"name": "Omega-3",     "dose": "1000mg",   "time_of_day": "13:00", "frequency": "Once daily"},
        ],
        "contacts": [
            {"name": "Lakshmi Nair",    "phone": "+91 94455 66778", "relationship": "Wife"},
            {"name": "Dr. Srinivas Rao","phone": "+91 98123 45678", "relationship": "Doctor"},
        ],
        # Pre-diabetic range — borderline high
        "glucose_values": [118, 132, 108, 142, 125, 115, 138, 122, 145, 112, 128, 136, 119, 141],
        "meals":          ["fasting","after_meal","fasting","after_meal","before_meal",
                           "fasting","after_meal","fasting","after_meal","bedtime",
                           "fasting","after_meal","fasting","before_meal"],
    },
]


# ══════════════════════════════════════════════════════
#  SEED FUNCTION
# ══════════════════════════════════════════════════════
def seed(db):
    print("\n🌱  Seeding test users...\n")

    for u in USERS:
        uid = new_id()

        # ── User row ───────────────────────────────────
        try:
            db.execute(
                "INSERT INTO users (id, name, email, password) VALUES (?, ?, ?, ?)",
                (uid, u["name"], u["email"], hash_pw(u["password"]))
            )
        except sqlite3.IntegrityError:
            print(f"  ⚠  {u['email']} already exists — skipping.")
            continue

        # ── Profile row ────────────────────────────────
        p = u["profile"]
        db.execute("""
            INSERT INTO profiles
                (user_id, age, gender, weight_kg, height_cm, lifestyle, dtype,
                 diagnosed_year, target_low, target_high, doctor_name, allergies,
                 meds_text, step_goal, steps_today)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            uid, p["age"], p["gender"], p["weight_kg"], p["height_cm"],
            p["lifestyle"], p["dtype"], p["diagnosed_year"],
            p["target_low"], p["target_high"],
            p["doctor_name"], p["allergies"], p["meds_text"],
            p["step_goal"], p["steps_today"],
        ))

        # ── Glucose readings (spread over last 14 days) ─
        meals = u["meals"]
        for i, val in enumerate(u["glucose_values"]):
            days_back = len(u["glucose_values"]) - i
            hour = random.choice([7, 8, 12, 18, 21])
            db.execute(
                """INSERT INTO glucose_readings
                   (id, user_id, value, meal_context, note, classification, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (new_id(), uid, val, meals[i], '', classify(val), days_ago(days_back, hour))
            )

        # ── Medications ────────────────────────────────
        for m in u["medications"]:
            db.execute(
                """INSERT INTO medications (id, user_id, name, dose, time_of_day, frequency)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (new_id(), uid, m["name"], m["dose"], m["time_of_day"], m["frequency"])
            )

        # ── Emergency contacts ─────────────────────────
        for c in u["contacts"]:
            db.execute(
                """INSERT INTO emergency_contacts (id, user_id, name, phone, relationship)
                   VALUES (?, ?, ?, ?, ?)""",
                (new_id(), uid, c["name"], c["phone"], c["relationship"])
            )

        # ── Safety log: one initial entry ─────────────
        db.execute(
            """INSERT INTO safety_log (id, user_id, log_type, message)
               VALUES (?, ?, ?, ?)""",
            (new_id(), uid, 'ok', 'Account created and profile set up successfully')
        )

        db.commit()
        print(f"  ✅  Created: {u['name']} ({u['email']})  |  password: {u['password']}")

    print()


# ══════════════════════════════════════════════════════
#  SUMMARY PRINT
# ══════════════════════════════════════════════════════
def print_summary(db):
    print("─" * 52)
    print("📋  DATABASE SUMMARY")
    print("─" * 52)
    users = db.execute("SELECT id, name, email FROM users").fetchall()
    for row in users:
        readings = db.execute(
            "SELECT COUNT(*) FROM glucose_readings WHERE user_id=?", (row[0],)
        ).fetchone()[0]
        meds = db.execute(
            "SELECT COUNT(*) FROM medications WHERE user_id=?", (row[0],)
        ).fetchone()[0]
        contacts = db.execute(
            "SELECT COUNT(*) FROM emergency_contacts WHERE user_id=?", (row[0],)
        ).fetchone()[0]
        print(f"  👤  {row[1]} — {row[2]}")
        print(f"       Readings: {readings}  |  Meds: {meds}  |  Contacts: {contacts}")
    print("─" * 52)
    print(f"  Database file: {DB_PATH}")
    print("─" * 52)
    print()
    print("🔑  LOGIN CREDENTIALS (for testing):")
    print()
    for u in USERS:
        print(f"  Email:    {u['email']}")
        print(f"  Password: {u['password']}")
        print()
    print("🚀  Now run:  python app.py")
    print()


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════
if __name__ == '__main__':
    if os.path.exists(DB_PATH):
        ans = input(f"⚠  Database already exists at:\n   {DB_PATH}\n\n   Overwrite? (yes/no): ").strip().lower()
        if ans == 'yes':
            os.remove(DB_PATH)
            print("   Old database removed.\n")
        else:
            print("   Keeping existing database. Adding users only if not already present.\n")

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    create_tables(db)
    seed(db)
    print_summary(db)
    db.close()