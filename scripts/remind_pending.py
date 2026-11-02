"""شبكة أمان: لو فيه طلب ينتظر أكثر من 10 دقايق بدون رد، يرسل لأمجد تلقرام مرة وحدة.

يشتغل من crontab حق amjed كل 5 دقايق. ما يرسل نص الطلب نفسه (خصوصية الولد)، بس العدد.
"""
import datetime, os, sqlite3, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(os.environ.get("RD_DATA_DIR", os.path.join(ROOT, "data")), "db.sqlite")
NOTIFY = "/home/amjed/bin/notify-amjed"
cutoff = (datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(minutes=10)).isoformat() + "Z"
c = sqlite3.connect(DB, timeout=10)
rows = [r[0] for r in c.execute(
    "SELECT id FROM requests WHERE status='pending' AND notified=0 AND created < ?", (cutoff,))]
if rows:
    r = subprocess.run([NOTIFY, f"🎨 roblox-designer: فيه {len(rows)} طلب من الموقع ينتظر كلود أكثر من 10 دقايق. افتح Claude Code وقل «كمّل الطلبات»."],
                       capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        c.executemany("UPDATE requests SET notified=1 WHERE id=?", [(i,) for i in rows]); c.commit()
c.close()
