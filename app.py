from flask import Flask, render_template, request, redirect, session
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret"

# -----------------------
# DB
# -----------------------
def get_db():
    conn = sqlite3.connect("healthcare.db")
    conn.row_factory = sqlite3.Row
    return conn

# -----------------------
# Init DB
# -----------------------
def init_db():
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    conn.execute("""
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    email TEXT
)
""")

    conn.execute("""
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT,
    date TEXT,
    time TEXT
)
""")

    conn.commit()
    conn.close()

# -----------------------
# Default Users
# -----------------------
def create_users():
    conn = get_db()

    if not conn.execute("SELECT * FROM users WHERE username='admin'").fetchone():
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     ("admin", generate_password_hash("admin123"), "admin"))

    if not conn.execute("SELECT * FROM users WHERE username='staff'").fetchone():
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     ("staff", generate_password_hash("staff123"), "staff"))

    conn.commit()
    conn.close()

# -----------------------
# Role Decorator
# -----------------------
def role_required(roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect("/")
            if session.get("role") not in roles:
                return "Access Denied", 403
            return fn(*args, **kwargs)
        return decorated
    return wrapper

# -----------------------
# Login
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/dashboard")

        return "Invalid login"

    return render_template("login.html")

# -----------------------
# Dashboard
# -----------------------
@app.route("/dashboard")
@role_required(["admin", "staff"])
def dashboard():
    conn = get_db()

    patients = conn.execute("SELECT * FROM patients").fetchall()
    appointments = conn.execute("SELECT * FROM appointments").fetchall()

    return render_template("dashboard.html",
                           patients=patients,
                           appointments=appointments,
                           role=session.get("role"))

# -----------------------
# Patients Page
# -----------------------
@app.route("/patients")
@role_required(["admin", "staff"])
def patients():
    conn = get_db()
    patients = conn.execute("SELECT * FROM patients").fetchall()
    return render_template("patients.html", patients=patients, role=session.get("role"))

@app.route("/add_patient_page")
@role_required(["admin", "staff"])
def add_patient_page():
    return render_template("add_patient.html")

# -----------------------
# Appointments Page
# -----------------------
@app.route("/appointments")
@role_required(["admin", "staff"])
def appointments():
    conn = get_db()

    appointments = conn.execute("""
    SELECT appointments.id, appointments.date, appointments.time,
           patients.first_name, patients.last_name, patients.patient_id
    FROM appointments
    JOIN patients ON appointments.patient_id = patients.patient_id
""").fetchall()
    
    patients = conn.execute("SELECT * FROM patients").fetchall()

    return render_template(
        "appointments.html",
        appointments=appointments,
        patients=patients,
        role=session.get("role")
    )

@app.route("/add_appointment_page")
@role_required(["admin", "staff"])
def add_appointment_page():
    conn = get_db()
    patients = conn.execute("SELECT * FROM patients").fetchall()

    return render_template("add_appointment.html", patients=patients)

# -----------------------
# Analytics Page
# -----------------------
@app.route("/analytics")
@role_required(["admin", "staff"])
def analytics():
    conn = get_db()

    # totals
    patient_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    appointment_count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]

    # bar chart data
    rows = conn.execute("""
        SELECT date, COUNT(*) as count
        FROM appointments
        GROUP BY date
        ORDER BY date
    """).fetchall()

    dates = [row["date"] for row in rows]
    counts = [row["count"] for row in rows]

    # calendar data
    event_rows = conn.execute("""
        SELECT appointments.date, appointments.time,
               patients.first_name, patients.last_name
        FROM appointments
        JOIN patients ON appointments.patient_id = patients.patient_id
    """).fetchall()

    events = []
    for r in event_rows:
        events.append({
            "title": f"{r['first_name']} {r['last_name']}",
            "start": f"{r['date']}T{r['time']}"
        })

    return render_template(
        "analytics.html",
        patient_count=patient_count,
        appointment_count=appointment_count,
        dates=dates,
        counts=counts,
        events=events
    )

# -----------------------
# Patients CRUD
# -----------------------
@app.route("/add_patient", methods=["POST"])
@role_required(["admin", "staff"])
def add_patient():
    conn = get_db()

    # Get next ID
    last = conn.execute("SELECT id FROM patients ORDER BY id DESC LIMIT 1").fetchone()
    
    next_id = 1 if not last else last["id"] + 1
    patient_id = f"{next_id:02d}"

    conn.execute("""
        INSERT INTO patients (patient_id, first_name, last_name, phone, email)
        VALUES (?, ?, ?, ?, ?)
    """, (
        patient_id,
        request.form["first_name"],
        request.form["last_name"],
        request.form["phone"],
        request.form["email"]
    ))

    conn.commit()
    return redirect("/patients")

@app.route("/edit_patient/<int:id>", methods=["GET", "POST"])
@role_required(["admin"])
def edit_patient(id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
UPDATE patients 
SET patient_id=?, first_name=?, last_name=?, phone=?, email=?
WHERE id=?
""", (
    request.form["patient_id"],
    request.form["first_name"],
    request.form["last_name"],
    request.form["phone"],
    request.form["email"],
    id
))
        conn.commit()
        return redirect("/patients")

    patient = conn.execute("SELECT * FROM patients WHERE id=?", (id,)).fetchone()
    return render_template("edit_patient.html", patient=patient)

@app.route("/delete_patient/<int:id>")
@role_required(["admin"])
def delete_patient(id):
    conn = get_db()
    conn.execute("DELETE FROM patients WHERE id=?", (id,))
    conn.commit()
    return redirect("/patients")

# -----------------------
# Appointments CRUD
# -----------------------
@app.route("/add_appointment", methods=["POST"])
@role_required(["admin", "staff"])
def add_appointment():
    conn = get_db()

    conn.execute("""
        INSERT INTO appointments (patient_id, date, time)
        VALUES (?, ?, ?)
    """, (
        request.form["patient_id"],
        request.form["date"],
        request.form["time"]
    ))

    conn.commit()
    return redirect("/appointments")

@app.route("/edit_appointment/<int:id>", methods=["GET", "POST"])
@role_required(["admin"])
def edit_appointment(id):
    conn = get_db()

    if request.method == "POST":
        conn.execute("UPDATE appointments SET patient_name=?, date=?, time=? WHERE id=?",
                     (request.form["patient_name"], request.form["date"], request.form["time"], id))
        conn.commit()
        return redirect("/appointments")

    appt = conn.execute("SELECT * FROM appointments WHERE id=?", (id,)).fetchone()
    return render_template("edit_appointment.html", appt=appt)

@app.route("/delete_appointment/<int:id>")
@role_required(["admin"])
def delete_appointment(id):
    conn = get_db()
    conn.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit()
    return redirect("/appointments")

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    init_db()
    create_users()
    app.run(debug=True)