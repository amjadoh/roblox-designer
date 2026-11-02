"""يراقب طلبات الموقع ويطبع سطر لكل طلب جديد (يستخدمه Claude Code كـ Monitor).

يقرأ قاعدة SQLite مباشرة (قراءة فقط) كل 3 ثواني. يطبع الطلبات المعلّقة الموجودة عند التشغيل
مرة وحدة، ثم كل طلب جديد. ما يعدّل أي شي.
"""
import os, sqlite3, sys, time

DB = os.path.join(os.environ.get("RD_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "db.sqlite")
seen = set()
while True:
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        for rid, pid, text in c.execute("SELECT id, project_id, text FROM requests WHERE status='pending' ORDER BY id"):
            if rid not in seen:
                seen.add(rid)
                print(f"طلب جديد #{rid} (مشروع {pid}): {text}", flush=True)
        c.close()
    except sqlite3.Error as e:
        print(f"خطأ في قراءة الطلبات: {e}", flush=True)
        time.sleep(30)
    time.sleep(3)
