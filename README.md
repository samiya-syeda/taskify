# Taskify — Your Digital Command Center

A full-stack productivity app with Tasks, Habit Tracker, Calendar & Journal.

## Stack
- **Frontend**: HTML + CSS + Vanilla JS (no build step needed)
- **Backend**: Python + Flask REST API
- **Database**: SQLite (auto-created on first run)

## Setup & Run

### 1. Install Python dependencies
```bash
pip install flask flask-cors
```

### 2. Start the API server
```bash
cd taskify
python app.py
```
The API runs at `http://localhost:5000`

### 3. Open the frontend
Open `index.html` in your browser.

> **Tip**: Use a local server like VS Code Live Server or `python -m http.server 8080` then visit `http://localhost:8080`

## API Endpoints

### Tasks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/tasks | List all tasks |
| POST | /api/tasks | Create task |
| PUT | /api/tasks/:id | Update task |
| DELETE | /api/tasks/:id | Delete task |

### Habits
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/habits | List habits with logs |
| POST | /api/habits | Create habit |
| DELETE | /api/habits/:id | Delete habit |
| POST | /api/habits/:id/log | Toggle day completion |

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/events | List events |
| POST | /api/events | Create event |
| PUT | /api/events/:id | Update event |
| DELETE | /api/events/:id | Delete event |

### Journal
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/journal | List entries |
| POST | /api/journal | Create entry |
| PUT | /api/journal/:id | Update entry |
| DELETE | /api/journal/:id | Delete entry |

## Database
SQLite file `taskify.db` is auto-created in the project directory.

Tables: `tasks`, `habits`, `habit_logs`, `events`, `journal_entries`
