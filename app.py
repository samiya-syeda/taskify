from flask import send_from_directory
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import hashlib
import secrets
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'taskify.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password, stored):
    try:
        salt, hashed = stored.split(':')
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except:
        return False

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        completed INTEGER DEFAULT 0,
        priority TEXT DEFAULT 'medium',
        due_date TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        color TEXT DEFAULT '#00ff88',
        frequency TEXT DEFAULT 'daily',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS habit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id INTEGER NOT NULL,
        log_date TEXT NOT NULL,
        completed INTEGER DEFAULT 1,
        FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
        UNIQUE(habit_id, log_date)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        event_date TEXT NOT NULL,
        event_time TEXT,
        note TEXT,
        color TEXT DEFAULT '#00d4ff',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT,
        content TEXT NOT NULL,
        mood TEXT,
        tags TEXT,
        entry_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    conn.commit()
    conn.close()


@app.route("/")
def serve_home():
    return send_from_directory('.', 'index.html')

@app.route("/login")
def serve_login():
    return send_from_directory('.', 'login.html')
# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    conn = get_db()
    existing = conn.execute('SELECT id FROM users WHERE email=? OR username=?', (email, username)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Username or email already exists'}), 409

    hashed = hash_password(password)
    c = conn.cursor()
    c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, hashed))
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': user_id, 'username': username, 'email': email}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    identifier = (data.get('identifier') or '').strip()
    password = data.get('password', '')

    if not identifier or not password:
        return jsonify({'error': 'Email/username and password are required'}), 400

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email=? OR username=?', (identifier, identifier)).fetchone()
    conn.close()

    if not user or not verify_password(password, user['password']):
        return jsonify({'error': 'Invalid credentials'}), 401

    return jsonify({'id': user['id'], 'username': user['username'], 'email': user['email']})

# ─── TASKS ───────────────────────────────────────────────────────────────────

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    tasks = conn.execute('SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC', (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(t) for t in tasks])

@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO tasks (user_id, title, description, priority, due_date) VALUES (?, ?, ?, ?, ?)',
              (data['user_id'], data['title'], data.get('description', ''), data.get('priority', 'medium'), data.get('due_date', '')))
    task_id = c.lastrowid
    conn.commit()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    conn.close()
    return jsonify(dict(task)), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.json
    conn = get_db()
    fields, values = [], []
    for field in ['title', 'description', 'completed', 'priority', 'due_date']:
        if field in data:
            fields.append(f'{field} = ?')
            values.append(data[field])
    values.append(task_id)
    conn.execute(f'UPDATE tasks SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    conn.close()
    return jsonify(dict(task))

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = get_db()
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': task_id})

# ─── HABITS ──────────────────────────────────────────────────────────────────

@app.route('/api/habits', methods=['GET'])
def get_habits():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    habits = conn.execute('SELECT * FROM habits WHERE user_id=? ORDER BY created_at DESC', (user_id,)).fetchall()
    result = []
    for h in habits:
        h_dict = dict(h)
        logs = conn.execute('SELECT log_date FROM habit_logs WHERE habit_id = ?', (h['id'],)).fetchall()
        h_dict['logs'] = [l['log_date'] for l in logs]
        result.append(h_dict)
    conn.close()
    return jsonify(result)

@app.route('/api/habits', methods=['POST'])
def create_habit():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO habits (user_id, name, color, frequency) VALUES (?, ?, ?, ?)',
              (data['user_id'], data['name'], data.get('color', '#00ff88'), data.get('frequency', 'daily')))
    habit_id = c.lastrowid
    conn.commit()
    habit = conn.execute('SELECT * FROM habits WHERE id = ?', (habit_id,)).fetchone()
    conn.close()
    h_dict = dict(habit)
    h_dict['logs'] = []
    return jsonify(h_dict), 201

@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
def delete_habit(habit_id):
    conn = get_db()
    conn.execute('DELETE FROM habits WHERE id = ?', (habit_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': habit_id})

@app.route('/api/habits/<int:habit_id>/log', methods=['POST'])
def toggle_habit_log(habit_id):
    data = request.json
    log_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db()
    existing = conn.execute('SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?', (habit_id, log_date)).fetchone()
    if existing:
        conn.execute('DELETE FROM habit_logs WHERE habit_id = ? AND log_date = ?', (habit_id, log_date))
        action = 'removed'
    else:
        conn.execute('INSERT INTO habit_logs (habit_id, log_date) VALUES (?, ?)', (habit_id, log_date))
        action = 'added'
    conn.commit()
    conn.close()
    return jsonify({'action': action, 'date': log_date})

# ─── EVENTS ──────────────────────────────────────────────────────────────────

@app.route('/api/events', methods=['GET'])
def get_events():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    events = conn.execute('SELECT * FROM events WHERE user_id=? ORDER BY event_date', (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(e) for e in events])

@app.route('/api/events', methods=['POST'])
def create_event():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO events (user_id, title, event_date, event_time, note, color) VALUES (?, ?, ?, ?, ?, ?)',
              (data['user_id'], data['title'], data['event_date'], data.get('event_time', ''), data.get('note', ''), data.get('color', '#00d4ff')))
    event_id = c.lastrowid
    conn.commit()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()
    return jsonify(dict(event)), 201

@app.route('/api/events/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    data = request.json
    conn = get_db()
    fields, values = [], []
    for field in ['title', 'event_date', 'event_time', 'note', 'color']:
        if field in data:
            fields.append(f'{field} = ?')
            values.append(data[field])
    values.append(event_id)
    conn.execute(f'UPDATE events SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()
    return jsonify(dict(event))

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    conn = get_db()
    conn.execute('DELETE FROM events WHERE id = ?', (event_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': event_id})

# ─── JOURNAL ─────────────────────────────────────────────────────────────────

@app.route('/api/journal', methods=['GET'])
def get_journal():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    entries = conn.execute('SELECT * FROM journal_entries WHERE user_id=? ORDER BY entry_date DESC', (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(e) for e in entries])

@app.route('/api/journal', methods=['POST'])
def create_journal():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    entry_date = data.get('entry_date', datetime.now().strftime('%Y-%m-%d'))
    c.execute('INSERT INTO journal_entries (user_id, title, content, mood, tags, entry_date) VALUES (?, ?, ?, ?, ?, ?)',
              (data['user_id'], data.get('title', ''), data['content'], data.get('mood', ''), data.get('tags', ''), entry_date))
    entry_id = c.lastrowid
    conn.commit()
    entry = conn.execute('SELECT * FROM journal_entries WHERE id = ?', (entry_id,)).fetchone()
    conn.close()
    return jsonify(dict(entry)), 201

@app.route('/api/journal/<int:entry_id>', methods=['PUT'])
def update_journal(entry_id):
    data = request.json
    conn = get_db()
    fields, values = [], []
    for field in ['title', 'content', 'mood', 'tags', 'entry_date']:
        if field in data:
            fields.append(f'{field} = ?')
            values.append(data[field])
    fields.append('updated_at = CURRENT_TIMESTAMP')
    values.append(entry_id)
    conn.execute(f'UPDATE journal_entries SET {", ".join(fields)} WHERE id = ?', values)
    conn.commit()
    entry = conn.execute('SELECT * FROM journal_entries WHERE id = ?', (entry_id,)).fetchone()
    conn.close()
    return jsonify(dict(entry))

@app.route('/api/journal/<int:entry_id>', methods=['DELETE'])
def delete_journal(entry_id):
    conn = get_db()
    conn.execute('DELETE FROM journal_entries WHERE id = ?', (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': entry_id})

if __name__ == '__main__':
    init_db()
    print()
    print("┌─────────────────────────────────────────┐")
    print("│         Taskify API is running!         │")
    print("│                                         │")
    print("│   API  →  http://localhost:5000         │")
    print("│   Open index.html in your browser       │")
    print("│                                         │")
    print("│   Press Ctrl+C to stop                  │")
    print("└─────────────────────────────────────────┘")
    print()
    app.run(debug=True, port=5000)
