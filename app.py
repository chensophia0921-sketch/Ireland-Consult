from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, session
from werkzeug.utils import secure_filename
from pathlib import Path
import sqlite3, uuid, os
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "consult.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

TOPICS = [
    "留学申请与生活",
    "找工作与简历",
    "PPSN申请流程",
    "Revenue / VAT 税务流程",
    "公司注册流程",
    "移民与居留经验",
    "租房与本地生活",
    "其他爱尔兰生活问题",
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS consultations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        topic TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        payment_image TEXT,
        started_at TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consultation_id TEXT NOT NULL,
        sender TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (consultation_id) REFERENCES consultations(id)
    );
    """)
    conn.close()

init_db()

@app.route("/")
def home():
    return render_template("index.html", topics=TOPICS)

@app.route("/start", methods=["POST"])
def start():
    name = request.form.get("name", "").strip()
    topic = request.form.get("topic", "").strip()
    if not name or topic not in TOPICS:
        return redirect(url_for("home"))
    cid = uuid.uuid4().hex[:10].upper()
    conn = db()
    conn.execute(
        "INSERT INTO consultations(id,name,topic,created_at,status) VALUES(?,?,?,?,?)",
        (cid, name, topic, datetime.now().isoformat(timespec="seconds"), "awaiting_payment")
    )
    conn.commit()
    conn.close()
    return redirect(url_for("pay", cid=cid))

@app.route("/pay/<cid>", methods=["GET", "POST"])
def pay(cid):
    conn = db()
    c = conn.execute("SELECT * FROM consultations WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not c:
        return "咨询不存在", 404
    if request.method == "POST":
        file = request.files.get("payment_image")
        filename = None
        if file and file.filename:
            ext = Path(secure_filename(file.filename)).suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                return "仅支持图片格式", 400
            filename = f"{cid}{ext}"
            file.save(UPLOAD_DIR / filename)
        conn = db()
        conn.execute(
            "UPDATE consultations SET status=?, payment_image=? WHERE id=?",
            ("paid_pending_review", filename, cid)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("chat", cid=cid))
    return render_template("pay.html", c=c)

@app.route("/chat/<cid>")
def chat(cid):
    conn = db()
    c = conn.execute("SELECT * FROM consultations WHERE id=?", (cid,)).fetchone()
    msgs = conn.execute(
        "SELECT * FROM messages WHERE consultation_id=? ORDER BY id ASC", (cid,)
    ).fetchall()
    conn.close()
    if not c:
        return "咨询不存在", 404
    return render_template("chat.html", c=c, msgs=msgs)

@app.route("/api/messages/<cid>")
def api_messages(cid):
    after = int(request.args.get("after", 0))
    conn = db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE consultation_id=? AND id>? ORDER BY id ASC",
        (cid, after)
    ).fetchall()
    c = conn.execute("SELECT status,started_at FROM consultations WHERE id=?", (cid,)).fetchone()
    conn.close()
    return jsonify({
        "messages": [dict(r) for r in rows],
        "status": c["status"] if c else "missing",
        "started_at": c["started_at"] if c else None
    })

@app.route("/api/send/<cid>", methods=["POST"])
def api_send(cid):
    body = (request.json or {}).get("body", "").strip()
    sender = (request.json or {}).get("sender", "customer")
    if sender == "admin" and not session.get("admin"):
        return jsonify({"ok": False}), 403
    if not body:
        return jsonify({"ok": False}), 400
    conn = db()
    conn.execute(
        "INSERT INTO messages(consultation_id,sender,body,created_at) VALUES(?,?,?,?)",
        (cid, sender, body, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        return render_template("admin_login.html", error="密码错误")
    if not session.get("admin"):
        return render_template("admin_login.html")
    conn = db()
    rows = conn.execute(
        "SELECT * FROM consultations ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin.html", rows=rows)

@app.route("/admin/chat/<cid>")
def admin_chat(cid):
    if not session.get("admin"):
        return redirect(url_for("admin"))
    conn = db()
    c = conn.execute("SELECT * FROM consultations WHERE id=?", (cid,)).fetchone()
    msgs = conn.execute(
        "SELECT * FROM messages WHERE consultation_id=? ORDER BY id ASC", (cid,)
    ).fetchall()
    conn.close()
    if not c:
        return "咨询不存在", 404
    return render_template("admin_chat.html", c=c, msgs=msgs)

@app.route("/admin/start/<cid>", methods=["POST"])
def admin_start(cid):
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    conn = db()
    conn.execute(
        "UPDATE consultations SET status='active', started_at=COALESCE(started_at, ?) WHERE id=?",
        (datetime.now().isoformat(timespec="seconds"), cid)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/admin/end/<cid>", methods=["POST"])
def admin_end(cid):
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    conn = db()
    conn.execute("UPDATE consultations SET status='ended' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/admin/api/new")
def admin_new():
    if not session.get("admin"):
        return jsonify([]), 403
    after = request.args.get("after", "")
    conn = db()
    if after:
        rows = conn.execute(
            """SELECT m.*, c.name, c.topic FROM messages m
               JOIN consultations c ON c.id=m.consultation_id
               WHERE m.sender='customer' AND m.created_at>? ORDER BY m.id ASC""",
            (after,)
        ).fetchall()
    else:
        rows = []
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
