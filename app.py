import os
import sqlite3
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB = "database.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --------------------------
# DATABASE INIT
# --------------------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course TEXT,
        mean REAL,
        std REAL,
        failure REAL,
        difficulty REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()


# --------------------------
# SAMPLE DATA
# --------------------------
def generate_sample_data():
    data = {"Course": [], "Score": []}
    courses = ["Math", "Physics", "Chemistry"]

    for course in courses:
        scores = np.random.normal(60, 15, 80)
        scores = np.clip(scores, 0, 100)
        data["Course"] += [course]*80
        data["Score"] += list(scores)

    return pd.DataFrame(data)


# --------------------------
# REGISTER
# --------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed = generate_password_hash(password)

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users(username, password) VALUES (?, ?)", (username, hashed))
            conn.commit()
            flash("Registration successful. Please login.")
            return redirect("/")
        except:
            flash("Username already exists.")
        finally:
            conn.close()

    return render_template("register.html")


# --------------------------
# LOGIN
# --------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user"] = username
            return redirect("/dashboard")
        else:
            flash("Invalid credentials")

    return render_template("login.html")


# --------------------------
# LOGOUT
# --------------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully.")
    return redirect("/")


# --------------------------
# DASHBOARD
# --------------------------
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user" not in session:
        return redirect("/")

    df = generate_sample_data()

    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename != "":
            filename = file.filename.lower()

            if filename.endswith(".csv"):
                df = pd.read_csv(file)
            elif filename.endswith(".xlsx"):
                df = pd.read_excel(file)
            else:
                flash("Only CSV or Excel files allowed.")
                return redirect("/dashboard")

            if not {"Course", "Score"}.issubset(df.columns):
                flash("File must contain Course and Score columns.")
                return redirect("/dashboard")

            if not pd.api.types.is_numeric_dtype(df["Score"]):
                flash("Score column must be numeric.")
                return redirect("/dashboard")

    results = []

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM analysis")

    for course, group in df.groupby("Course"):
        mean = group["Score"].mean()
        std = group["Score"].std()
        failure = (group["Score"] < 40).mean()*100
        difficulty = 0.4*std + 0.3*failure + 0.3*(100-mean)

        c.execute("""
        INSERT INTO analysis(course, mean, std, failure, difficulty)
        VALUES (?, ?, ?, ?, ?)
        """, (course, mean, std, failure, difficulty))

        results.append({
            "course": course,
            "mean": round(mean,2),
            "std": round(std,2),
            "failure": round(failure,2),
            "difficulty": round(difficulty,2)
        })

    conn.commit()
    conn.close()

    return render_template("dashboard.html", results=results)


# --------------------------
# PDF REPORT
# --------------------------
@app.route("/download_report")
def download_report():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT * FROM analysis", conn)
    conn.close()

    file_path = "analysis_report.pdf"
    doc = SimpleDocTemplate(file_path, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Course Difficulty Analysis Report", styles["Heading1"]))
    elements.append(Spacer(1, 20))

    for _, row in df.iterrows():
        text = f"""
        Course: {row['course']} <br/>
        Mean: {round(row['mean'],2)} <br/>
        Std Dev: {round(row['std'],2)} <br/>
        Failure %: {round(row['failure'],2)} <br/>
        Difficulty Index: {round(row['difficulty'],2)} <br/><br/>
        """
        elements.append(Paragraph(text, styles["Normal"]))
        elements.append(Spacer(1, 15))

    doc.build(elements)
    return send_file(file_path, as_attachment=True)


# --------------------------
# SYSTEM REPORT PAGE
# --------------------------
@app.route("/system_report")
def system_report():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT * FROM analysis", conn)
    conn.close()

    hardest = df.sort_values("difficulty", ascending=False).iloc[0]
    easiest = df.sort_values("difficulty").iloc[0]

    return render_template("system_report.html",
                           hardest=hardest,
                           easiest=easiest)


if __name__ == "__main__":
    app.run(debug=True)