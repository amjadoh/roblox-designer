"""أداة سطر أوامر يستخدمها الوكيل (Claude Code) لتطبيق التصاميم على مشاريع التطبيق.

الاستخدام (من مجلد المشروع):
    python -m app.design_cli new [--name NAME]
    python -m app.design_cli list
    python -m app.design_cli show PID
    python -m app.design_cli set PID '<JSON جزئي>' --note "وش تغيّر"
    python -m app.design_cli undo PID
    python -m app.design_cli check PID
    python -m app.design_cli package PID [--out FILE.zip]
    python -m app.design_cli requests [--all]           # طلبات الموقع اللي تنتظر رد
    python -m app.design_cli reply RID "الرد" [--reject] # رد على طلب (ويربطه بالإصدار الحالي)

`set` يقبل فقط مفاتيح موجودة في DEFAULT_SPEC وبقيم صالحة؛ أي شي ثاني يُرفض قبل الرسم.
"""
import argparse, copy, json, os, re, sys

from fastapi.testclient import TestClient

from . import main
from .generate import DEFAULT_SPEC

PATTERNS = ("none", "diamond", "hex", "chevron")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
RANGES = {"pattern_opacity": (0.0, 0.6), "pocket_scale": (0.4, 1.8), "emblem_scale": (0.4, 1.8),
          "cargo_pocket_scale": (0.4, 1.8)}


class SpecError(ValueError):
    pass


def validate_patch(patch, ref=DEFAULT_SPEC, path=""):
    if not isinstance(patch, dict): raise SpecError(f"{path or 'الجذر'}: لازم يكون كائن JSON")
    for k, v in patch.items():
        p = f"{path}.{k}" if path else k
        if k not in ref: raise SpecError(f"مفتاح غير معروف: {p}")
        r = ref[k]
        if k == "locked":
            if not (isinstance(v, list) and all(x in ("shirt", "pants") for x in v)):
                raise SpecError("locked: قائمة فيها shirt أو pants فقط")
        elif k == "colors":
            if not isinstance(v, dict): raise SpecError(f"{p}: لازم كائن")
            for ck, cv in v.items():
                if ck not in ("base", "accent"): raise SpecError(f"لون غير معروف: {p}.{ck}")
                if not (isinstance(cv, str) and HEX.match(cv)): raise SpecError(f"{p}.{ck}: لازم #RRGGBB")
        elif k == "pattern":
            if v not in PATTERNS: raise SpecError(f"{p}: المسموح {PATTERNS}")
        elif isinstance(r, dict):
            validate_patch(v, r, p)
        elif isinstance(r, bool):
            if not isinstance(v, bool): raise SpecError(f"{p}: لازم true/false")
        elif isinstance(r, (int, float)):
            if isinstance(v, bool) or not isinstance(v, (int, float)): raise SpecError(f"{p}: لازم رقم")
            lo, hi = RANGES.get(k, (0, 10))
            if not lo <= v <= hi: raise SpecError(f"{p}: لازم بين {lo} و {hi}")
        elif isinstance(r, str):
            if not isinstance(v, str) or len(v) > 60: raise SpecError(f"{p}: نص قصير")


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def files_of(pid, n):
    d = main.rdir(pid, n)
    return {g: os.path.join(d, f"{g}.png") for g in ("shirt", "pants")}


def out(obj): print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_new(a):
    st = TestClient(main.app).post("/api/projects").json()
    if a.name:
        c = main.db(); c.execute("UPDATE projects SET name=? WHERE id=?", (a.name[:60], st["id"])); c.commit()
    out({"id": st["id"], "rev": st["current"]["n"], "png": files_of(st["id"], st["current"]["n"])})


def cmd_list(a): out([dict(r) for r in main.db().execute("SELECT id,name,current_rev FROM projects")])


def cmd_show(a):
    st = main.project_state(a.pid); cur = st["current"]
    out({"id": a.pid, "name": st["name"], "rev": cur["n"], "spec": cur["spec"], "png": files_of(a.pid, cur["n"]),
         "history": [{"n": r["n"], "message": r["message"]} for r in st["revisions"][-5:]]})


def cmd_set(a):
    patch = json.loads(a.patch)
    validate_patch(patch)
    cur = main.project_state(a.pid)["current"]
    spec = merge(cur["spec"], patch)
    for g in cur["spec"]["locked"]:  # الجزء المثبّت ما يتغير إلا لو انفك تثبيته في نفس الطلب
        if g in spec["locked"]: spec[g] = cur["spec"][g]
    if spec == cur["spec"]:
        out({"ok": False, "reason": "ما تغيّر شي (يمكن الجزء مثبّت)"}); return
    n = main.make_rev(a.pid, cur["n"], spec, a.note or "تعديل من الوكيل", a.note or "تعديل من الوكيل")
    out({"ok": True, "rev": n, "png": files_of(a.pid, n)})


def cmd_undo(a):
    cur = main.project_state(a.pid)["current"]
    if not cur["parent"]: out({"ok": False, "reason": "ما فيه إصدار قبله"}); return
    old = main.rev_info(a.pid, cur["parent"])["spec"]
    n = main.make_rev(a.pid, cur["n"], old, "تراجع", f"رجعت إلى الإصدار {cur['parent']}")
    out({"ok": True, "rev": n, "png": files_of(a.pid, n)})


def cmd_check(a):
    n = main.project_state(a.pid)["current"]["n"]
    out([{k: c[k] for k in ("id", "status", "rule")} for c in main.technical_validation(a.pid, n)])


def cmd_package(a):
    n = main.project_state(a.pid)["current"]["n"]
    r = TestClient(main.app).get(f"/api/projects/{a.pid}/package/{n}")
    path = a.out or os.path.join(main.DATA, "exports", f"{a.pid}-rev{n}.zip")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, "wb").write(r.content)
    out({"ok": True, "zip": os.path.abspath(path)})


def cmd_requests(a):
    q = "SELECT id, project_id, base_rev, text, status, created FROM requests"
    q += "" if a.all else " WHERE status='pending'"
    out([dict(r) for r in main.db().execute(q + " ORDER BY id")])


def cmd_reply(a):
    c = main.db()
    r = c.execute("SELECT project_id, status FROM requests WHERE id=?", (a.rid,)).fetchone()
    if not r: out({"ok": False, "reason": "طلب غير موجود"}); return
    if r["status"] != "pending": out({"ok": False, "reason": f"الطلب حالته {r['status']}، مو pending"}); return
    rev = main.db().execute("SELECT current_rev FROM projects WHERE id=?", (r["project_id"],)).fetchone()[0]
    c.execute("UPDATE requests SET status=?, reply=?, reply_rev=?, replied_at=? WHERE id=?",
              ("rejected" if a.reject else "done", a.text[:600], rev, main.now(), a.rid))
    c.commit()
    out({"ok": True, "id": a.rid, "status": "rejected" if a.reject else "done", "reply_rev": rev})


def build_parser():
    p = argparse.ArgumentParser(prog="design_cli"); s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("new"); x.add_argument("--name"); x.set_defaults(fn=cmd_new)
    s.add_parser("list").set_defaults(fn=cmd_list)
    for name, fn in (("show", cmd_show), ("undo", cmd_undo), ("check", cmd_check)):
        x = s.add_parser(name); x.add_argument("pid"); x.set_defaults(fn=fn)
    x = s.add_parser("set"); x.add_argument("pid"); x.add_argument("patch"); x.add_argument("--note"); x.set_defaults(fn=cmd_set)
    x = s.add_parser("package"); x.add_argument("pid"); x.add_argument("--out"); x.set_defaults(fn=cmd_package)
    x = s.add_parser("requests"); x.add_argument("--all", action="store_true"); x.set_defaults(fn=cmd_requests)
    x = s.add_parser("reply"); x.add_argument("rid", type=int); x.add_argument("text"); x.add_argument("--reject", action="store_true")
    x.set_defaults(fn=cmd_reply)
    return p


if __name__ == "__main__":
    a = build_parser().parse_args()
    try:
        a.fn(a)
    except (SpecError, json.JSONDecodeError) as e:
        out({"ok": False, "reason": str(e)}); sys.exit(2)
