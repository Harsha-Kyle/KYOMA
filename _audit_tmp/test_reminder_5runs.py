import sys
import os
import time
import sqlite3
sys.path.insert(0, 'Kyoma')
from reminder_utils import add_reminder, get_db_path, reset_demo_reminders

print("=== 5-RUN REMINDER CREATION & DB VERIFICATION ===")
reset_demo_reminders()

for i in range(1, 6):
    title = f"drink water run {i}"
    res = add_reminder(title, f"Drink water reminder test {i}", "in 1 minute")
    print(f"Run {i}: Created -> {res['title']} at {res['time']}")

conn = sqlite3.connect(get_db_path())
c = conn.cursor()
c.execute("SELECT id, title, time, status FROM reminders WHERE status = 'pending'")
rows = c.fetchall()
conn.close()
print(f"Database pending count: {len(rows)}/5 verified stored in {os.path.basename(get_db_path())}")
for r in rows:
    print(f"  ID {r[0]}: {r[1]} @ {r[2]} [status: {r[3]}]")
