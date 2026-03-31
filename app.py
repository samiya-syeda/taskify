#!/usr/bin/env python3
"""
Taskify - All-in-one productivity app
Flask backend + SQLite + embedded HTML frontend
Run: python3 app.py
Open: http://localhost:5000
"""

import sqlite3
import os
from datetime import datetime, date
from flask import Flask, request, jsonify, g

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taskify.db")

# ─── Database ────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                title     TEXT NOT NULL,
                note      TEXT DEFAULT '',
                priority  TEXT DEFAULT 'medium',
                category  TEXT DEFAULT 'general',
                done      INTEGER DEFAULT 0,
                created   TEXT NOT NULL,
                updated   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                color       TEXT DEFAULT '#00d4aa',
                frequency   TEXT DEFAULT 'daily',
                created     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS habit_logs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                log_date TEXT NOT NULL,
                UNIQUE(habit_id, log_date)
            );

            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_time TEXT DEFAULT '',
                note       TEXT DEFAULT '',
                color      TEXT DEFAULT '#4f8aff',
                created    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journal (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT NOT NULL,
                body    TEXT NOT NULL,
                mood    TEXT DEFAULT 'neutral',
                tags    TEXT DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
        """)
        db.commit()

def now_iso():
    return datetime.utcnow().isoformat()

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

def err(msg, code=400):
    return jsonify({"error": msg}), code

# ─── Tasks ────────────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    db = get_db()
    rows = db.execute("SELECT * FROM tasks ORDER BY done ASC, created DESC").fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/tasks", methods=["POST"])
def create_task():
    d = request.json or {}
    if not d.get("title", "").strip():
        return err("title required")
    db = get_db()
    t = now_iso()
    cur = db.execute(
        "INSERT INTO tasks (title,note,priority,category,done,created,updated) VALUES (?,?,?,?,0,?,?)",
        (d["title"].strip(), d.get("note",""), d.get("priority","medium"),
         d.get("category","general"), t, t)
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone())), 201

@app.route("/api/tasks/<int:tid>", methods=["PUT"])
def update_task(tid):
    d = request.json or {}
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not row:
        return err("not found", 404)
    db.execute(
        "UPDATE tasks SET title=?,note=?,priority=?,category=?,done=?,updated=? WHERE id=?",
        (d.get("title", row["title"]), d.get("note", row["note"]),
         d.get("priority", row["priority"]), d.get("category", row["category"]),
         int(d["done"]) if "done" in d else row["done"], now_iso(), tid)
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()))

@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def delete_task(tid):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id=?", (tid,))
    db.commit()
    return jsonify({"deleted": tid})

# ─── Habits ──────────────────────────────────────────────────────────────────

@app.route("/api/habits", methods=["GET"])
def get_habits():
    db = get_db()
    habits = rows_to_list(db.execute("SELECT * FROM habits ORDER BY created DESC").fetchall())
    today = date.today().isoformat()
    for h in habits:
        logs = db.execute(
            "SELECT log_date FROM habit_logs WHERE habit_id=? ORDER BY log_date DESC LIMIT 60",
            (h["id"],)
        ).fetchall()
        h["logs"] = [r["log_date"] for r in logs]
        h["done_today"] = today in h["logs"]
        streak = 0
        check = date.today()
        log_set = set(h["logs"])
        while check.isoformat() in log_set:
            streak += 1
            from datetime import timedelta
            check = check - timedelta(days=1)
        h["streak"] = streak
    return jsonify(habits)

@app.route("/api/habits", methods=["POST"])
def create_habit():
    d = request.json or {}
    if not d.get("name","").strip():
        return err("name required")
    db = get_db()
    cur = db.execute(
        "INSERT INTO habits (name,description,color,frequency,created) VALUES (?,?,?,?,?)",
        (d["name"].strip(), d.get("description",""), d.get("color","#00d4aa"),
         d.get("frequency","daily"), now_iso())
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM habits WHERE id=?", (cur.lastrowid,)).fetchone())), 201

@app.route("/api/habits/<int:hid>", methods=["DELETE"])
def delete_habit(hid):
    db = get_db()
    db.execute("DELETE FROM habits WHERE id=?", (hid,))
    db.commit()
    return jsonify({"deleted": hid})

@app.route("/api/habits/<int:hid>/toggle", methods=["POST"])
def toggle_habit(hid):
    db = get_db()
    log_date = (request.json or {}).get("date", date.today().isoformat())
    existing = db.execute(
        "SELECT id FROM habit_logs WHERE habit_id=? AND log_date=?", (hid, log_date)
    ).fetchone()
    if existing:
        db.execute("DELETE FROM habit_logs WHERE habit_id=? AND log_date=?", (hid, log_date))
        done = False
    else:
        db.execute("INSERT INTO habit_logs (habit_id,log_date) VALUES (?,?)", (hid, log_date))
        done = True
    db.commit()
    return jsonify({"done": done, "date": log_date})

# ─── Events ──────────────────────────────────────────────────────────────────

@app.route("/api/events", methods=["GET"])
def get_events():
    db = get_db()
    month = request.args.get("month")
    if month:
        rows = db.execute(
            "SELECT * FROM events WHERE event_date LIKE ? ORDER BY event_date, event_time",
            (month + "%",)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM events ORDER BY event_date DESC, event_time").fetchall()
    return jsonify(rows_to_list(rows))

@app.route("/api/events", methods=["POST"])
def create_event():
    d = request.json or {}
    if not d.get("title","").strip():
        return err("title required")
    if not d.get("event_date","").strip():
        return err("event_date required")
    db = get_db()
    cur = db.execute(
        "INSERT INTO events (title,event_date,event_time,note,color,created) VALUES (?,?,?,?,?,?)",
        (d["title"].strip(), d["event_date"], d.get("event_time",""),
         d.get("note",""), d.get("color","#4f8aff"), now_iso())
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM events WHERE id=?", (cur.lastrowid,)).fetchone())), 201

@app.route("/api/events/<int:eid>", methods=["PUT"])
def update_event(eid):
    d = request.json or {}
    db = get_db()
    row = db.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    if not row:
        return err("not found", 404)
    db.execute(
        "UPDATE events SET title=?,event_date=?,event_time=?,note=?,color=? WHERE id=?",
        (d.get("title", row["title"]), d.get("event_date", row["event_date"]),
         d.get("event_time", row["event_time"]), d.get("note", row["note"]),
         d.get("color", row["color"]), eid)
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()))

@app.route("/api/events/<int:eid>", methods=["DELETE"])
def delete_event(eid):
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (eid,))
    db.commit()
    return jsonify({"deleted": eid})

# ─── Journal ─────────────────────────────────────────────────────────────────

@app.route("/api/journal", methods=["GET"])
def get_journal():
    db = get_db()
    return jsonify(rows_to_list(db.execute("SELECT * FROM journal ORDER BY created DESC").fetchall()))

@app.route("/api/journal", methods=["POST"])
def create_entry():
    d = request.json or {}
    if not d.get("title","").strip():
        return err("title required")
    if not d.get("body","").strip():
        return err("body required")
    db = get_db()
    t = now_iso()
    cur = db.execute(
        "INSERT INTO journal (title,body,mood,tags,created,updated) VALUES (?,?,?,?,?,?)",
        (d["title"].strip(), d["body"].strip(), d.get("mood","neutral"), d.get("tags",""), t, t)
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM journal WHERE id=?", (cur.lastrowid,)).fetchone())), 201

@app.route("/api/journal/<int:jid>", methods=["PUT"])
def update_entry(jid):
    d = request.json or {}
    db = get_db()
    row = db.execute("SELECT * FROM journal WHERE id=?", (jid,)).fetchone()
    if not row:
        return err("not found", 404)
    db.execute(
        "UPDATE journal SET title=?,body=?,mood=?,tags=?,updated=? WHERE id=?",
        (d.get("title", row["title"]), d.get("body", row["body"]),
         d.get("mood", row["mood"]), d.get("tags", row["tags"]), now_iso(), jid)
    )
    db.commit()
    return jsonify(row_to_dict(db.execute("SELECT * FROM journal WHERE id=?", (jid,)).fetchone()))

@app.route("/api/journal/<int:jid>", methods=["DELETE"])
def delete_entry(jid):
    db = get_db()
    db.execute("DELETE FROM journal WHERE id=?", (jid,))
    db.commit()
    return jsonify({"deleted": jid})

# ─── Frontend (embedded) ──────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Taskify</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0d0f14;--bg2:#13161e;--bg3:#1a1e28;
  --border:#252a38;--border2:#2e3548;
  --text:#e8eaf0;--text2:#8b91a8;--text3:#555d75;
  --accent:#00d4aa;--accent2:#4f8aff;--accent3:#f59e0b;--accent4:#ef4444;
  --purple:#a78bfa;--pink:#f472b6;
  --r:12px;--tr:all .2s ease;
}
html{font-size:15px}body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh;display:flex;overflow-x:hidden}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

/* Sidebar */
#sidebar{width:220px;min-width:220px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:0 0 24px;position:fixed;top:0;left:0;height:100vh;z-index:100}
.brand{padding:28px 20px 24px;border-bottom:1px solid var(--border)}
.brand h1{font-family:'Space Mono',monospace;font-size:1.3rem;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.5px}
.brand .tagline{font-size:0.68rem;color:var(--text3);letter-spacing:2px;text-transform:uppercase;display:block;margin-top:3px}
nav{flex:1;padding:16px 12px;display:flex;flex-direction:column;gap:2px}
.nav-section{font-size:0.62rem;letter-spacing:2px;text-transform:uppercase;color:var(--text3);padding:14px 12px 4px;font-weight:600}
.nav-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;cursor:pointer;transition:var(--tr);color:var(--text2);font-size:0.875rem;font-weight:500}
.nav-item svg{width:17px;height:17px;flex-shrink:0}
.nav-item:hover{background:var(--bg3);color:var(--text)}
.nav-item.active{background:rgba(0,212,170,.1);color:var(--accent)}
.sidebar-footer{padding:14px 20px;border-top:1px solid var(--border);font-family:'Space Mono',monospace;font-size:0.62rem;color:var(--text3)}

/* Main */
#main{margin-left:220px;flex:1;min-height:100vh;overflow-y:auto}
.page{display:none;padding:36px 40px;animation:fadeIn .3s ease}
.page.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* Headers */
.page-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:32px;gap:16px;flex-wrap:wrap}
.page-title{font-family:'Space Mono',monospace;font-size:1.7rem;font-weight:700}
.page-sub{font-size:0.78rem;color:var(--text3);margin-top:5px;letter-spacing:.3px}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:8px;padding:9px 18px;border-radius:8px;border:none;cursor:pointer;font-family:'DM Sans',sans-serif;font-size:0.875rem;font-weight:500;transition:var(--tr);white-space:nowrap}
.btn-primary{background:var(--accent);color:#061a14}
.btn-primary:hover{background:#00bfa0;transform:translateY(-1px);box-shadow:0 6px 20px rgba(0,212,170,.25)}
.btn-secondary{background:var(--bg3);color:var(--text);border:1px solid var(--border2)}
.btn-secondary:hover{border-color:var(--accent);color:var(--accent)}
.btn-danger{background:rgba(239,68,68,.12);color:var(--accent4);border:1px solid rgba(239,68,68,.2)}
.btn-danger:hover{background:rgba(239,68,68,.22)}
.btn-sm{padding:6px 12px;font-size:0.78rem}
.btn-icon{padding:7px;border-radius:7px}

/* Cards */
.card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);padding:22px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}

/* Stat cards */
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);padding:22px;display:flex;flex-direction:column;gap:6px}
.stat-card .s-label{font-size:0.68rem;letter-spacing:1.5px;text-transform:uppercase;color:var(--text3);font-weight:600}
.stat-card .s-value{font-family:'Space Mono',monospace;font-size:2.2rem;font-weight:700;line-height:1}
.stat-card .s-sub{font-size:0.74rem;color:var(--text2);margin-top:2px}
.stat-accent{border-left:3px solid var(--accent)}
.stat-blue{border-left:3px solid var(--accent2)}
.stat-amber{border-left:3px solid var(--accent3)}
.stat-purple{border-left:3px solid var(--purple)}

/* Task list */
.task-filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.filter-btn{padding:6px 16px;border-radius:20px;font-size:0.78rem;background:transparent;border:1px solid var(--border2);color:var(--text2);cursor:pointer;transition:var(--tr);font-family:'DM Sans',sans-serif}
.filter-btn.active,.filter-btn:hover{border-color:var(--accent);color:var(--accent);background:rgba(0,212,170,.06)}
.task-list{display:flex;flex-direction:column;gap:8px}
.task-item{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;display:flex;align-items:flex-start;gap:12px;transition:var(--tr)}
.task-item:hover{border-color:var(--border2);background:var(--bg3)}
.task-item.done{opacity:.45}
.task-item.done .task-title{text-decoration:line-through;color:var(--text3)}
.chk{width:20px;height:20px;border-radius:6px;border:2px solid var(--border2);cursor:pointer;flex-shrink:0;transition:var(--tr);display:flex;align-items:center;justify-content:center;margin-top:1px}
.chk.on{background:var(--accent);border-color:var(--accent)}
.chk.on::after{content:'✓';font-size:11px;color:#061a14;font-weight:800}
.task-body{flex:1;min-width:0}
.task-title{font-size:0.9rem;font-weight:500;line-height:1.4}
.task-note{font-size:0.75rem;color:var(--text3);margin-top:4px;line-height:1.4}
.task-meta{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}
.badge{font-size:0.63rem;letter-spacing:.5px;padding:3px 8px;border-radius:4px;font-weight:700;text-transform:uppercase}
.badge-high{background:rgba(239,68,68,.15);color:#fca5a5}
.badge-medium{background:rgba(245,158,11,.15);color:#fcd34d}
.badge-low{background:rgba(0,212,170,.12);color:var(--accent)}
.badge-cat{background:rgba(79,138,255,.12);color:#93b4ff}
.task-actions{display:flex;gap:6px;opacity:0;transition:var(--tr);flex-shrink:0}
.task-item:hover .task-actions{opacity:1}

/* Habits */
.habit-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.habit-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);padding:20px;display:flex;flex-direction:column;gap:14px;transition:var(--tr)}
.habit-card:hover{border-color:var(--border2)}
.habit-hdr{display:flex;align-items:center;justify-content:space-between}
.habit-name{display:flex;align-items:center;gap:10px;font-weight:600;font-size:0.95rem}
.h-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.habit-streak{font-family:'Space Mono',monospace;font-size:0.78rem;color:var(--accent3);display:flex;align-items:center;gap:4px}
.heatmap{display:flex;gap:3px;flex-wrap:wrap}
.hcell{width:14px;height:14px;border-radius:3px;background:var(--bg3);border:1px solid var(--border);flex-shrink:0}
.habit-today{display:flex;align-items:center;justify-content:space-between;padding-top:10px;border-top:1px solid var(--border)}
.tog{width:46px;height:26px;border-radius:13px;background:var(--bg3);border:1px solid var(--border2);cursor:pointer;transition:var(--tr);position:relative;flex-shrink:0}
.tog.on{background:var(--accent);border-color:var(--accent)}
.tog::after{content:'';position:absolute;top:4px;left:4px;width:16px;height:16px;border-radius:50%;background:#fff;transition:var(--tr)}
.tog.on::after{transform:translateX(20px)}

/* Calendar */
.cal-layout{display:grid;grid-template-columns:1fr 300px;gap:20px;align-items:start}
.cal-nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.cal-month-lbl{font-family:'Space Mono',monospace;font-size:1rem;font-weight:700}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.cal-dname{text-align:center;font-size:0.63rem;letter-spacing:1px;text-transform:uppercase;color:var(--text3);padding:8px 0;font-weight:600}
.cal-day{aspect-ratio:1;border-radius:8px;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;transition:var(--tr);position:relative;font-size:0.84rem;border:1px solid transparent;gap:3px}
.cal-day:hover{background:var(--bg3);border-color:var(--border)}
.cal-day.today{background:rgba(0,212,170,.12);border-color:var(--accent);color:var(--accent);font-weight:700}
.cal-day.sel{background:var(--accent);color:#061a14;font-weight:700;border-color:var(--accent)}
.cal-day.sel:hover{background:var(--accent)}
.cal-day.other{color:var(--text3)}
.cal-day .ev-dot{width:5px;height:5px;border-radius:50%;background:var(--accent2)}
.ev-panel .card{margin-bottom:12px}
.ev-item{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)}
.ev-item:last-child{border-bottom:none;padding-bottom:0}
.ev-stripe{width:3px;border-radius:2px;flex-shrink:0;align-self:stretch;min-height:24px}
.ev-info .ev-title{font-size:0.875rem;font-weight:500}
.ev-info .ev-time{font-size:0.72rem;color:var(--text3);margin-top:2px}
.ev-info .ev-note{font-size:0.72rem;color:var(--text2);margin-top:4px;line-height:1.4}

/* Journal */
.j-layout{display:grid;grid-template-columns:270px 1fr;gap:20px;align-items:start}
.j-list{display:flex;flex-direction:column;gap:8px;max-height:72vh;overflow-y:auto;padding-right:4px}
.j-item{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px;cursor:pointer;transition:var(--tr)}
.j-item:hover,.j-item.active{border-color:var(--accent);background:rgba(0,212,170,.04)}
.j-item .jt{font-size:0.875rem;font-weight:600;margin-bottom:4px}
.j-item .jp{font-size:0.74rem;color:var(--text3);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.j-item .jm{display:flex;justify-content:space-between;margin-top:6px;font-size:0.7rem;color:var(--text3)}
.j-editor{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);padding:28px}

/* Modals */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(6px);z-index:200;display:none;align-items:center;justify-content:center;padding:20px}
.overlay.open{display:flex}
.modal{background:var(--bg2);border:1px solid var(--border2);border-radius:16px;padding:28px;width:100%;max-width:480px;animation:mIn .22s ease}
@keyframes mIn{from{opacity:0;transform:scale(.96)}to{opacity:1;transform:scale(1)}}
.modal-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
.modal-title{font-family:'Space Mono',monospace;font-size:0.95rem;font-weight:700}
.close-x{width:30px;height:30px;border-radius:7px;background:var(--bg3);border:1px solid var(--border);cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--text2);font-size:16px;transition:var(--tr)}
.close-x:hover{border-color:var(--accent4);color:var(--accent4)}
.fg{margin-bottom:16px}
.fr{display:grid;grid-template-columns:1fr 1fr;gap:12px}
label{display:block;font-size:0.72rem;letter-spacing:.4px;color:var(--text2);margin-bottom:6px;font-weight:500}
input,textarea,select{width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px 12px;color:var(--text);font-family:'DM Sans',sans-serif;font-size:0.875rem;transition:var(--tr);outline:none;resize:vertical}
input:focus,textarea:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,212,170,.1)}
select option{background:var(--bg2)}
textarea{min-height:90px;line-height:1.5}
.form-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:20px}
.cp{display:flex;gap:8px;flex-wrap:wrap}
.co{width:28px;height:28px;border-radius:50%;cursor:pointer;border:3px solid transparent;transition:var(--tr)}
.co.sel,.co:hover{border-color:#fff;transform:scale(1.12)}

/* Dashboard extras */
.dash-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:24px}
.prog-bar{height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;margin-top:6px}
.prog-fill{height:100%;border-radius:3px;transition:width .6s ease}
.empty-state{text-align:center;padding:40px 20px;color:var(--text3);display:flex;flex-direction:column;align-items:center;gap:10px}
.empty-state svg{width:44px;height:44px;opacity:.25}
.empty-state p{font-size:0.84rem}

@media(max-width:860px){
  #sidebar{width:56px;min-width:56px}
  .nav-item span,.brand h1,.brand .tagline,.nav-section,.sidebar-footer{display:none}
  .brand{padding:14px 8px}.nav-item{justify-content:center;padding:12px}
  #main{margin-left:56px}.cal-layout,.j-layout{grid-template-columns:1fr}
  .dash-grid,.grid-2,.grid-4{grid-template-columns:1fr}.page{padding:20px 16px}
}
</style>
</head>
<body>

<aside id="sidebar">
  <div class="brand">
    <h1>Taskify</h1>
    <span class="tagline">Productivity Suite</span>
  </div>
  <nav>
    <div class="nav-section">Overview</div>
    <div class="nav-item active" data-page="dashboard">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
      <span>Dashboard</span>
    </div>
    <div class="nav-section">Manage</div>
    <div class="nav-item" data-page="tasks">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      <span>Tasks</span>
    </div>
    <div class="nav-item" data-page="habits">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
      <span>Habits</span>
    </div>
    <div class="nav-item" data-page="calendar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      <span>Calendar</span>
    </div>
    <div class="nav-item" data-page="journal">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>
      <span>Journal</span>
    </div>
  </nav>
  <div class="sidebar-footer">Taskify v1.0 · SQLite</div>
</aside>

<main id="main">

  <!-- Dashboard -->
  <section class="page active" id="page-dashboard">
    <div class="page-header">
      <div>
        <div class="page-title">Good <span id="greet">morning</span> <span id="greet-emoji">☀️</span></div>
        <div class="page-sub" id="today-str"></div>
      </div>
    </div>
    <div class="grid-4" id="dash-stats"></div>
    <div class="dash-grid">
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <b style="font-family:'Space Mono',monospace;font-size:.82rem;letter-spacing:.5px">RECENT TASKS</b>
          <span class="btn btn-secondary btn-sm" style="cursor:pointer" onclick="navTo('tasks')">View all →</span>
        </div>
        <div id="dash-tasks"></div>
      </div>
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <b style="font-family:'Space Mono',monospace;font-size:.82rem;letter-spacing:.5px">TODAY'S HABITS</b>
          <span class="btn btn-secondary btn-sm" style="cursor:pointer" onclick="navTo('habits')">Manage →</span>
        </div>
        <div id="dash-habits"></div>
      </div>
    </div>
  </section>

  <!-- Tasks -->
  <section class="page" id="page-tasks">
    <div class="page-header">
      <div><div class="page-title">Tasks</div><div class="page-sub">Manage your to-do list</div></div>
      <button class="btn btn-primary" onclick="openModal('task')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Add Task
      </button>
    </div>
    <div class="task-filters">
      <button class="filter-btn active" data-f="all">All</button>
      <button class="filter-btn" data-f="active">Active</button>
      <button class="filter-btn" data-f="done">Completed</button>
      <button class="filter-btn" data-f="high">High Priority</button>
    </div>
    <div class="task-list" id="task-list"></div>
  </section>

  <!-- Habits -->
  <section class="page" id="page-habits">
    <div class="page-header">
      <div><div class="page-title">Habit Tracker</div><div class="page-sub">Build streaks · track consistency</div></div>
      <button class="btn btn-primary" onclick="openModal('habit')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        New Habit
      </button>
    </div>
    <div class="habit-grid" id="habit-grid"></div>
  </section>

  <!-- Calendar -->
  <section class="page" id="page-calendar">
    <div class="page-header">
      <div><div class="page-title">Calendar</div><div class="page-sub">Schedule & manage events</div></div>
      <button class="btn btn-primary" onclick="openModal('event')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Add Event
      </button>
    </div>
    <div class="cal-layout">
      <div class="card">
        <div class="cal-nav">
          <button class="btn btn-secondary btn-sm" onclick="calMove(-1)">← Prev</button>
          <div class="cal-month-lbl" id="cal-lbl"></div>
          <button class="btn btn-secondary btn-sm" onclick="calMove(1)">Next →</button>
        </div>
        <div class="cal-grid" id="cal-grid"></div>
      </div>
      <div class="ev-panel">
        <div class="card">
          <div style="font-family:'Space Mono',monospace;font-size:.78rem;color:var(--text2);margin-bottom:12px" id="ev-day-lbl">Select a day</div>
          <div id="ev-day-list"><div class="empty-state" style="padding:16px">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <p>No events</p>
          </div></div>
        </div>
      </div>
    </div>
  </section>

  <!-- Journal -->
  <section class="page" id="page-journal">
    <div class="page-header">
      <div><div class="page-title">Journal</div><div class="page-sub">Your personal diary</div></div>
      <button class="btn btn-primary" onclick="newJ()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        New Entry
      </button>
    </div>
    <div class="j-layout">
      <div class="j-list" id="j-list"></div>
      <div class="j-editor" id="j-editor">
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>
          <p>Select an entry or create a new one</p>
        </div>
      </div>
    </div>
  </section>

</main>

<!-- Overlay / Modals -->
<div class="overlay" id="overlay" onclick="closeOuter(event)">

  <!-- Task modal -->
  <div class="modal" id="m-task">
    <div class="modal-hdr">
      <div class="modal-title" id="task-m-title">New Task</div>
      <button class="close-x" onclick="closeModal()">✕</button>
    </div>
    <div class="fg"><label>Title *</label><input id="t-title" placeholder="What needs to be done?"/></div>
    <div class="fg"><label>Note</label><textarea id="t-note" rows="3" placeholder="Additional details..."></textarea></div>
    <div class="fr">
      <div class="fg"><label>Priority</label>
        <select id="t-priority"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select>
      </div>
      <div class="fg"><label>Category</label><input id="t-cat" placeholder="Work, Personal…" value="general"/></div>
    </div>
    <div class="form-actions">
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveTask()">Save Task</button>
    </div>
  </div>

  <!-- Habit modal -->
  <div class="modal" id="m-habit" style="display:none">
    <div class="modal-hdr">
      <div class="modal-title">New Habit</div>
      <button class="close-x" onclick="closeModal()">✕</button>
    </div>
    <div class="fg"><label>Habit Name *</label><input id="h-name" placeholder="e.g. Morning Run"/></div>
    <div class="fg"><label>Description</label><input id="h-desc" placeholder="Optional description"/></div>
    <div class="fg"><label>Color</label>
      <div class="cp" id="h-cp">
        <div class="co sel" data-c="#00d4aa" style="background:#00d4aa"></div>
        <div class="co" data-c="#4f8aff" style="background:#4f8aff"></div>
        <div class="co" data-c="#f59e0b" style="background:#f59e0b"></div>
        <div class="co" data-c="#a78bfa" style="background:#a78bfa"></div>
        <div class="co" data-c="#f472b6" style="background:#f472b6"></div>
        <div class="co" data-c="#ef4444" style="background:#ef4444"></div>
      </div>
    </div>
    <div class="form-actions">
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveHabit()">Save Habit</button>
    </div>
  </div>

  <!-- Event modal -->
  <div class="modal" id="m-event" style="display:none">
    <div class="modal-hdr">
      <div class="modal-title" id="ev-m-title">New Event</div>
      <button class="close-x" onclick="closeModal()">✕</button>
    </div>
    <div class="fg"><label>Event Title *</label><input id="e-title" placeholder="Event name"/></div>
    <div class="fr">
      <div class="fg"><label>Date *</label><input id="e-date" type="date"/></div>
      <div class="fg"><label>Time</label><input id="e-time" type="time"/></div>
    </div>
    <div class="fg"><label>Note</label><textarea id="e-note" rows="3" placeholder="Event details..."></textarea></div>
    <div class="fg"><label>Color</label>
      <div class="cp" id="e-cp">
        <div class="co" data-c="#00d4aa" style="background:#00d4aa"></div>
        <div class="co sel" data-c="#4f8aff" style="background:#4f8aff"></div>
        <div class="co" data-c="#f59e0b" style="background:#f59e0b"></div>
        <div class="co" data-c="#a78bfa" style="background:#a78bfa"></div>
        <div class="co" data-c="#f472b6" style="background:#f472b6"></div>
        <div class="co" data-c="#ef4444" style="background:#ef4444"></div>
      </div>
    </div>
    <div class="form-actions">
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveEvent()">Save Event</button>
    </div>
  </div>

</div>

<script>
// ── State ───────────────────────────────────────────────────────────────────
let tasks=[], habits=[], events=[], journal=[];
let tFilter='all', tEditId=null, evEditId=null, jEditId=null;
let calY, calM, calSel=null;
let hColor='#00d4aa', eColor='#4f8aff';

// ── Boot ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const n=new Date(); calY=n.getFullYear(); calM=n.getMonth();
  calSel=n.toISOString().split('T')[0];
  const h=n.getHours();
  document.getElementById('greet').textContent=h<12?'morning':h<17?'afternoon':'evening';
  document.getElementById('greet-emoji').textContent=h<12?'☀️':h<17?'🌤️':'🌙';
  document.getElementById('today-str').textContent=
    n.toLocaleDateString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'});

  document.querySelectorAll('.nav-item').forEach(el=>el.addEventListener('click',()=>navTo(el.dataset.page)));
  document.querySelectorAll('.filter-btn').forEach(btn=>btn.addEventListener('click',()=>{
    tFilter=btn.dataset.f;
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active'); renderTasks();
  }));
  setupCP('h-cp', c=>{hColor=c;});
  setupCP('e-cp', c=>{eColor=c;});
  await Promise.all([loadTasks(),loadHabits(),loadEvents(),loadJournal()]);
  renderDash(); renderCal();
});

function setupCP(id,cb){
  document.querySelectorAll(`#${id} .co`).forEach(el=>el.addEventListener('click',()=>{
    document.querySelectorAll(`#${id} .co`).forEach(e=>e.classList.remove('sel'));
    el.classList.add('sel'); cb(el.dataset.c);
  }));
}

function navTo(p){
  document.querySelectorAll('.nav-item').forEach(e=>e.classList.toggle('active',e.dataset.page===p));
  document.querySelectorAll('.page').forEach(e=>e.classList.toggle('active',e.id==='page-'+p));
  if(p==='dashboard') renderDash();
  if(p==='calendar') renderCal();
}

// ── API ─────────────────────────────────────────────────────────────────────
async function api(m,p,b){
  const r=await fetch(p,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});
  if(!r.ok){const e=await r.json();throw new Error(e.error||'Error');}
  return r.json();
}

// ── Tasks ───────────────────────────────────────────────────────────────────
async function loadTasks(){tasks=await api('GET','/api/tasks');renderTasks();}
function renderTasks(){
  let f=tasks;
  if(tFilter==='active') f=tasks.filter(t=>!t.done);
  else if(tFilter==='done') f=tasks.filter(t=>t.done);
  else if(tFilter==='high') f=tasks.filter(t=>t.priority==='high');
  const el=document.getElementById('task-list');
  if(!f.length){el.innerHTML=`<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg><p>No tasks here yet</p></div>`;return;}
  el.innerHTML=f.map(t=>`
    <div class="task-item ${t.done?'done':''}">
      <div class="chk ${t.done?'on':''}" onclick="togTask(${t.id})"></div>
      <div class="task-body">
        <div class="task-title">${X(t.title)}</div>
        ${t.note?`<div class="task-note">${X(t.note)}</div>`:''}
        <div class="task-meta">
          <span class="badge badge-${t.priority}">${t.priority}</span>
          <span class="badge badge-cat">${X(t.category)}</span>
          <span style="font-size:.68rem;color:var(--text3)">${fd(t.created)}</span>
        </div>
      </div>
      <div class="task-actions">
        <button class="btn btn-secondary btn-sm btn-icon" onclick="editTask(${t.id})" title="Edit"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
        <button class="btn btn-danger btn-sm btn-icon" onclick="delTask(${t.id})" title="Delete"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M9 6V4h6v2"/></svg></button>
      </div>
    </div>`).join('');
}
async function togTask(id){const t=tasks.find(x=>x.id===id);await api('PUT',`/api/tasks/${id}`,{done:t.done?0:1});await loadTasks();renderDash();}
async function delTask(id){if(!confirm('Delete task?'))return;await api('DELETE',`/api/tasks/${id}`);await loadTasks();renderDash();}
function editTask(id){
  tEditId=id; const t=tasks.find(x=>x.id===id);
  document.getElementById('task-m-title').textContent='Edit Task';
  document.getElementById('t-title').value=t.title;
  document.getElementById('t-note').value=t.note;
  document.getElementById('t-priority').value=t.priority;
  document.getElementById('t-cat').value=t.category;
  openModal('task');
}
async function saveTask(){
  const title=document.getElementById('t-title').value.trim();
  if(!title){alert('Title required');return;}
  const b={title,note:document.getElementById('t-note').value,priority:document.getElementById('t-priority').value,category:document.getElementById('t-cat').value||'general'};
  tEditId?await api('PUT',`/api/tasks/${tEditId}`,b):await api('POST','/api/tasks',b);
  closeModal(); await loadTasks(); renderDash();
}

// ── Habits ──────────────────────────────────────────────────────────────────
async function loadHabits(){habits=await api('GET','/api/habits');renderHabits();}
function renderHabits(){
  const el=document.getElementById('habit-grid');
  if(!habits.length){el.innerHTML=`<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg><p>Add your first habit!</p></div>`;return;}
  const days=[]; const td=new Date();
  for(let i=29;i>=0;i--){const d=new Date(td);d.setDate(d.getDate()-i);days.push(d.toISOString().split('T')[0]);}
  el.innerHTML=habits.map(h=>`
    <div class="habit-card">
      <div class="habit-hdr">
        <div class="habit-name"><div class="h-dot" style="background:${h.color}"></div>${X(h.name)}${h.description?`<span style="font-size:.7rem;color:var(--text3)">${X(h.description)}</span>`:''}</div>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="habit-streak">🔥 ${h.streak}</div>
          <button class="btn btn-danger btn-sm btn-icon" onclick="delHabit(${h.id})"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M9 6V4h6v2"/></svg></button>
        </div>
      </div>
      <div class="heatmap">${days.map(d=>`<div class="hcell" style="${h.logs.includes(d)?`background:${h.color};opacity:.75;border-color:${h.color}`:''}" title="${d}"></div>`).join('')}</div>
      <div class="habit-today">
        <span style="font-size:.8rem;color:var(--text2)">Today</span>
        <div class="tog ${h.done_today?'on':''}" onclick="togHabit(${h.id})"></div>
      </div>
    </div>`).join('');
}
async function togHabit(id){const today=new Date().toISOString().split('T')[0];await api('POST',`/api/habits/${id}/toggle`,{date:today});await loadHabits();renderDash();}
async function delHabit(id){if(!confirm('Delete habit?'))return;await api('DELETE',`/api/habits/${id}`);await loadHabits();}
async function saveHabit(){
  const name=document.getElementById('h-name').value.trim();
  if(!name){alert('Name required');return;}
  await api('POST','/api/habits',{name,description:document.getElementById('h-desc').value,color:hColor,frequency:'daily'});
  closeModal(); await loadHabits(); renderDash();
}

// ── Events ──────────────────────────────────────────────────────────────────
async function loadEvents(){events=await api('GET','/api/events');renderCal();}
function renderCal(){
  const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
  document.getElementById('cal-lbl').textContent=`${MONTHS[calM]} ${calY}`;
  const first=new Date(calY,calM,1), last=new Date(calY,calM+1,0);
  const sd=first.getDay(), td2=last.getDate();
  const today=new Date().toISOString().split('T')[0];
  const evMap={};
  events.forEach(e=>{(evMap[e.event_date]=evMap[e.event_date]||[]).push(e);});
  const DN=['Su','Mo','Tu','We','Th','Fr','Sa'];
  let h=DN.map(d=>`<div class="cal-dname">${d}</div>`).join('');
  const pL=new Date(calY,calM,0).getDate();
  for(let i=sd-1;i>=0;i--) h+=`<div class="cal-day other">${pL-i}</div>`;
  for(let d=1;d<=td2;d++){
    const iso=`${calY}-${String(calM+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const hev=evMap[iso]&&evMap[iso].length;
    const cls=['cal-day'];
    if(iso===today) cls.push('today');
    if(iso===calSel) cls.push('sel');
    if(hev) cls.push('has-ev');
    h+=`<div class="${cls.join(' ')}" onclick="selDay('${iso}')">${d}${hev?'<div class="ev-dot"></div>':''}</div>`;
  }
  const rem=(7-(sd+td2)%7)%7;
  for(let i=1;i<=rem;i++) h+=`<div class="cal-day other">${i}</div>`;
  document.getElementById('cal-grid').innerHTML=h;
  if(calSel) renderDayEv(calSel);
}
function calMove(d){calM+=d;if(calM<0){calM=11;calY--;}if(calM>11){calM=0;calY++;}renderCal();}
function selDay(iso){calSel=iso;renderCal();}
function renderDayEv(date){
  const evs=events.filter(e=>e.event_date===date);
  document.getElementById('ev-day-lbl').textContent=fdFull(date);
  const el=document.getElementById('ev-day-list');
  if(!evs.length){el.innerHTML=`<div class="empty-state" style="padding:16px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/></svg><p>No events</p></div>`;return;}
  el.innerHTML=evs.map(e=>`
    <div class="ev-item">
      <div class="ev-stripe" style="background:${e.color}"></div>
      <div class="ev-info" style="flex:1">
        <div class="ev-title">${X(e.title)}</div>
        ${e.event_time?`<div class="ev-time">⏰ ${e.event_time}</div>`:''}
        ${e.note?`<div class="ev-note">${X(e.note)}</div>`:''}
      </div>
      <button class="btn btn-danger btn-sm btn-icon" onclick="delEv(${e.id})"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M9 6V4h6v2"/></svg></button>
    </div>`).join('');
}
async function saveEvent(){
  const title=document.getElementById('e-title').value.trim(), date=document.getElementById('e-date').value;
  if(!title){alert('Title required');return;}if(!date){alert('Date required');return;}
  const b={title,event_date:date,event_time:document.getElementById('e-time').value,note:document.getElementById('e-note').value,color:eColor};
  evEditId?await api('PUT',`/api/events/${evEditId}`,b):await api('POST','/api/events',b);
  closeModal(); await loadEvents();
}
async function delEv(id){if(!confirm('Delete event?'))return;await api('DELETE',`/api/events/${id}`);await loadEvents();}

// ── Journal ─────────────────────────────────────────────────────────────────
const ME={happy:'😊',neutral:'😐',sad:'😔',excited:'🤩',anxious:'😰'};
async function loadJournal(){journal=await api('GET','/api/journal');renderJList();}
function renderJList(){
  const el=document.getElementById('j-list');
  if(!journal.length){el.innerHTML=`<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg><p>No entries yet</p></div>`;return;}
  el.innerHTML=journal.map(j=>`
    <div class="j-item ${jEditId===j.id?'active':''}" onclick="openJ(${j.id})">
      <div class="jt">${X(j.title)}</div>
      <div class="jp">${X(j.body)}</div>
      <div class="jm"><span>${fd(j.created)}</span><span>${ME[j.mood]||'😐'} ${j.mood}</span></div>
    </div>`).join('');
}
function newJ(){jEditId=null;document.querySelectorAll('.j-item').forEach(e=>e.classList.remove('active'));renderJForm(null);}
function openJ(id){jEditId=id;renderJList();renderJForm(journal.find(x=>x.id===id));}
function renderJForm(j){
  const isNew=!j;
  document.getElementById('j-editor').innerHTML=`
    <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px">
      <div>
        <div style="font-family:'Space Mono',monospace;font-size:.9rem;font-weight:700">${isNew?'New Entry':X(j.title)}</div>
        <div style="font-size:.7rem;color:var(--text3);margin-top:3px">${isNew?new Date().toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'}):fdFull(j.created)}</div>
      </div>
      ${!isNew?`<button class="btn btn-danger btn-sm" onclick="delJ(${j.id})">Delete</button>`:''}
    </div>
    <div class="fg"><label>Title</label><input id="j-title" value="${isNew?'':X(j.title)}" placeholder="Entry title…"/></div>
    <div class="fg"><label>Mood</label>
      <select id="j-mood">${['happy','neutral','sad','excited','anxious'].map(m=>`<option value="${m}" ${!isNew&&j.mood===m?'selected':''}>${ME[m]} ${m}</option>`).join('')}</select>
    </div>
    <div class="fg"><label>Tags (comma separated)</label><input id="j-tags" value="${isNew?'':(j.tags||'')}" placeholder="work, personal, ideas…"/></div>
    <div class="fg"><label>Your thoughts</label><textarea id="j-body" rows="10" placeholder="What's on your mind today?">${isNew?'':(j.body||'')}</textarea></div>
    <div class="form-actions"><button class="btn btn-primary" onclick="saveJ()">${isNew?'Save Entry':'Update Entry'}</button></div>
  `;
  if(!isNew && document.getElementById('j-mood')) document.getElementById('j-mood').value=j.mood||'neutral';
}
async function saveJ(){
  const title=document.getElementById('j-title').value.trim(), body=document.getElementById('j-body').value.trim();
  if(!title){alert('Title required');return;}if(!body){alert('Body required');return;}
  const p={title,body,mood:document.getElementById('j-mood').value,tags:document.getElementById('j-tags').value};
  const saved=jEditId?await api('PUT',`/api/journal/${jEditId}`,p):await api('POST','/api/journal',p);
  jEditId=saved.id; await loadJournal(); openJ(saved.id);
}
async function delJ(id){if(!confirm('Delete entry?'))return;await api('DELETE',`/api/journal/${id}`);jEditId=null;await loadJournal();document.getElementById('j-editor').innerHTML=`<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg><p>Select an entry or create a new one</p></div>`;}

// ── Dashboard ────────────────────────────────────────────────────────────────
function renderDash(){
  const done=tasks.filter(t=>t.done).length, active=tasks.length-done;
  const hToday=habits.filter(h=>h.done_today).length;
  const upcoming=events.filter(e=>e.event_date>=new Date().toISOString().split('T')[0]).length;
  const pct=tasks.length?Math.round(done/tasks.length*100):0;
  document.getElementById('dash-stats').innerHTML=`
    <div class="stat-card stat-accent"><div class="s-label">Active Tasks</div><div class="s-value" style="color:var(--accent)">${active}</div><div class="s-sub">${done} completed</div></div>
    <div class="stat-card stat-blue"><div class="s-label">Habits Today</div><div class="s-value" style="color:var(--accent2)">${hToday}/${habits.length}</div><div class="s-sub">Daily progress</div></div>
    <div class="stat-card stat-amber"><div class="s-label">Upcoming</div><div class="s-value" style="color:var(--accent3)">${upcoming}</div><div class="s-sub">Events ahead</div></div>
    <div class="stat-card stat-purple"><div class="s-label">Journal</div><div class="s-value" style="color:var(--purple)">${journal.length}</div><div class="s-sub">Total entries</div></div>
  `;
  const dt=document.getElementById('dash-tasks');
  if(!tasks.length){dt.innerHTML=`<div style="text-align:center;color:var(--text3);font-size:.8rem;padding:16px">No tasks yet</div>`;return;}
  dt.innerHTML=`
    <div style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:.74rem;color:var(--text2)">Completion rate</span>
        <span style="font-size:.74rem;color:var(--accent);font-family:'Space Mono',monospace">${pct}%</span>
      </div>
      <div class="prog-bar"><div class="prog-fill" style="width:${pct}%;background:var(--accent)"></div></div>
    </div>
    ${tasks.slice(0,6).map(t=>`
      <div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border)">
        <div class="chk ${t.done?'on':''}" style="width:16px;height:16px;border-radius:4px" onclick="togTask(${t.id})"></div>
        <span style="font-size:.82rem;flex:1;color:${t.done?'var(--text3)':'var(--text)'};${t.done?'text-decoration:line-through':''}">${X(t.title)}</span>
        <span class="badge badge-${t.priority}">${t.priority}</span>
      </div>`).join('')}
  `;
  const dh=document.getElementById('dash-habits');
  if(!habits.length){dh.innerHTML=`<div style="text-align:center;color:var(--text3);font-size:.8rem;padding:16px">No habits yet</div>`;return;}
  dh.innerHTML=habits.map(h=>`
    <div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border)">
      <div style="width:8px;height:8px;border-radius:50%;background:${h.color};flex-shrink:0"></div>
      <span style="font-size:.82rem;flex:1">${X(h.name)}</span>
      <span style="font-size:.72rem;color:var(--accent3);font-family:'Space Mono',monospace">🔥${h.streak}</span>
      <div class="tog ${h.done_today?'on':''}" style="width:38px;height:22px" onclick="togHabit(${h.id})"></div>
    </div>`).join('');
}

// ── Modal ────────────────────────────────────────────────────────────────────
function openModal(t){
  document.getElementById('overlay').classList.add('open');
  document.getElementById('m-task').style.display=t==='task'?'':'none';
  document.getElementById('m-habit').style.display=t==='habit'?'':'none';
  document.getElementById('m-event').style.display=t==='event'?'':'none';
  if(t==='task'&&!tEditId){document.getElementById('task-m-title').textContent='New Task';['t-title','t-note'].forEach(id=>document.getElementById(id).value='');document.getElementById('t-priority').value='medium';document.getElementById('t-cat').value='general';}
  if(t==='event'&&!evEditId){document.getElementById('ev-m-title').textContent='New Event';['e-title','e-note','e-time'].forEach(id=>document.getElementById(id).value='');document.getElementById('e-date').value=calSel||new Date().toISOString().split('T')[0];}
  if(t==='habit'){['h-name','h-desc'].forEach(id=>document.getElementById(id).value='');}
}
function closeModal(){document.getElementById('overlay').classList.remove('open');tEditId=null;evEditId=null;}
function closeOuter(e){if(e.target===document.getElementById('overlay'))closeModal();}

// ── Utils ────────────────────────────────────────────────────────────────────
function X(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function fd(iso){if(!iso)return'';return new Date(iso).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});}
function fdFull(iso){if(!iso)return'';try{return new Date(iso+'T00:00:00').toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});}catch{return iso;}}
</script>
</body>
</html>"""

@app.route("/")
def index():
    return HTML

if __name__ == "__main__":
    init_db()
    print()
    print("┌───────────────────────────────────────────┐")
    print("│         Taskify is running!               │")
    print("│                                           │")
    print("│   Open → http://localhost:5000            │")
    print("│                                           │")
    print("│   Press Ctrl+C to stop                    │")
    print("└───────────────────────────────────────────┘")
    print()
    app.run(debug=True, port=5000, use_reloader=False)
