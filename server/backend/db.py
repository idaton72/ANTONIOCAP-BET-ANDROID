import sqlite3,json
from pathlib import Path
from datetime import datetime
DB=Path.home()/"betprofessional_v4.sqlite"
def init_db():
    c=sqlite3.connect(DB);c.execute("CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,captured_at TEXT,payload TEXT)");c.commit();c.close()
def save(rows):
    c=sqlite3.connect(DB);now=datetime.now().isoformat(timespec="seconds")
    for r in rows:c.execute("INSERT INTO snapshots(captured_at,payload) VALUES(?,?)",(now,json.dumps(r,ensure_ascii=False)))
    c.commit();c.close()
