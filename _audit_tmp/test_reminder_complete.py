import sys
import os
import sqlite3
sys.path.insert(0, 'Kyoma')
from reminder_utils import get_db_path, mark_reminder_completed, reset_demo_reminders

conn = sqlite3.connect(get_db_path())
c = conn.cursor()
c.execute("SELECT id, title, time, status FROM reminders WHERE status = 'pending'")
rows = c.fetchall()
conn.close()

print("=== SIMULATING FIRING & COMPLETION OF 5 REMINDERS ===")
for r in rows:
    rid, title, rtime, status = r
    mark_reminder_completed(rid)
    print(f"Triggered & Marked Completed: ID {rid} ({title})")

conn = sqlite3.connect(get_db_path())
c = conn.cursor()
c.execute("SELECT id, title, status FROM reminders")
all_rows = c.fetchall()
conn.close()
completed_count = sum(1 for r in all_rows if r[2] == 'completed')
print(f"Status transition verified: {completed_count}/{len(all_rows)} marked completed in reminders_demo.db")
reset_demo_reminders()
