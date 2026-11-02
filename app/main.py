import copy, datetime, io, json, os, sqlite3, uuid, zipfile
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from psd_tools import PSDImage

from . import accessory, commands, layout
from .generate import DEFAULT_SPEC, render_revision, sha256

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("RD_DATA_DIR", os.path.join(ROOT, "data"))
os.makedirs(DATA, exist_ok=True)
DB = os.path.join(DATA, "db.sqlite")
app = FastAPI(title="مصمم أصول Roblox")

# كلمة مرور اختيارية (HTTP Basic) للنشر على الإنترنت. محليًا بدون RD_PASSWORD ما فيه قفل.
RD_USER, RD_PASSWORD = os.environ.get("RD_USER", "roblox"), os.environ.get("RD_PASSWORD", "")


@app.middleware("http")
async def basic_auth(request, call_next):
    if RD_PASSWORD:
        import base64, hmac
        ok = False
        h = request.headers.get("authorization", "")
        if h.startswith("Basic "):
            try:
                u, _, p = base64.b64decode(h[6:]).decode("utf-8").partition(":")
                ok = hmac.compare_digest(u.encode(), RD_USER.encode()) & hmac.compare_digest(p.encode(), RD_PASSWORD.encode())
            except Exception:
                ok = False
        if not ok:
            return Response("مطلوب تسجيل دخول", status_code=401, headers={"WWW-Authenticate": 'Basic realm="roblox"'})
    return await call_next(request)


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT, current_rev INTEGER, approved_rev INTEGER);
    CREATE TABLE IF NOT EXISTS revisions(project_id TEXT, n INTEGER, parent INTEGER, command TEXT, message TEXT,
        spec TEXT, created TEXT, PRIMARY KEY(project_id, n));
    CREATE TABLE IF NOT EXISTS approvals(project_id TEXT, rev INTEGER, shirt_sha TEXT, pants_sha TEXT, created TEXT);
    """)
    return c


def rdir(pid, n): return os.path.join(DATA, "projects", pid, f"rev_{n}")
def now(): return datetime.datetime.utcnow().isoformat() + "Z"


def make_rev(pid, parent, spec, command, message):
    c = db()
    n = (c.execute("SELECT COALESCE(MAX(n),0)+1 FROM revisions WHERE project_id=?", (pid,)).fetchone()[0])
    reuse = rdir(pid, parent) if parent else None
    ps = rev_info(pid, parent)["spec"] if parent else {}
    rp = [g for g in spec["locked"] if parent and ps.get(g) == spec[g]]
    meta = render_revision(spec, rdir(pid, n), reuse=reuse, reuse_parts=rp)
    c.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?)", (pid, n, parent, command, message, json.dumps(spec), now()))
    c.execute("UPDATE projects SET current_rev=? WHERE id=?", (n, pid))
    c.commit(); return n


def rev_info(pid, n):
    r = db().execute("SELECT * FROM revisions WHERE project_id=? AND n=?", (pid, n)).fetchone()
    if not r: raise HTTPException(404, "إصدار غير موجود")
    d = rdir(pid, n)
    return {"n": n, "parent": r["parent"], "command": r["command"], "message": r["message"], "created": r["created"],
            "spec": json.loads(r["spec"]),
            "shirt_sha": sha256(os.path.join(d, "shirt.png")), "pants_sha": sha256(os.path.join(d, "pants.png"))}


def project_state(pid):
    c = db(); p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p: raise HTTPException(404, "مشروع غير موجود")
    revs = [dict(r) for r in c.execute("SELECT n,parent,command,message,created FROM revisions WHERE project_id=? ORDER BY n", (pid,))]
    cur = rev_info(pid, p["current_rev"])
    return {"id": pid, "name": p["name"], "current": cur, "approved_rev": p["approved_rev"], "revisions": revs,
            "template": layout.load_report(DATA)}


class Cmd(BaseModel):
    text: str
    selection: dict | None = None


@app.post("/api/projects")
def create_project():
    pid = uuid.uuid4().hex[:10]
    spec = copy.deepcopy(DEFAULT_SPEC)
    c = db(); c.execute("INSERT INTO projects VALUES(?,?,?,?)", (pid, spec["name"], 0, None)); c.commit()
    make_rev(pid, None, spec, "إنشاء الطقم الأول", "أنشأت الهودي والبنطلون الكارجو")
    return project_state(pid)


@app.get("/api/projects/{pid}")
def get_project(pid: str): return project_state(pid)


@app.get("/api/projects")
def list_projects():
    return [dict(r) for r in db().execute("SELECT id,name,current_rev,approved_rev FROM projects")]


@app.post("/api/projects/{pid}/command")
def command(pid: str, body: Cmd):
    st = project_state(pid); cur = st["current"]
    if not body.text.strip(): raise HTTPException(400, "أمر فارغ")
    ops, err = commands.parse(body.text, body.selection, cur["spec"])
    if err: return {"ok": False, "reply": err, "state": st}
    if ops[0]["op"] == "undo":
        if not cur["parent"]: return {"ok": False, "reply": "لا يوجد إصدار سابق.", "state": st}
        n = make_rev(pid, cur["n"], rev_info(pid, cur["parent"])["spec"], body.text, f"رجعت إلى الإصدار {cur['parent']}")
        # ملاحظة: الرجوع ينشئ إصدارًا جديدًا بمحتوى القديم ولا يمحو التاريخ
        return {"ok": True, "reply": f"رجعت إلى محتوى الإصدار {cur['parent']} (إصدار جديد رقم {n}).", "state": project_state(pid)}
    spec, msg = commands.apply(cur["spec"], ops)
    for g in spec["locked"]: spec[g] = cur["spec"][g]  # المقفل لا يتغير أبدًا
    if spec == cur["spec"]:
        return {"ok": False, "reply": "لم يتغير شيء (قد يكون الجزء مثبّتًا أو بلغ الحد).", "state": st}
    n = make_rev(pid, cur["n"], spec, body.text, msg)
    return {"ok": True, "reply": f"{msg}. الإصدار {n} جاهز للمراجعة.", "state": project_state(pid)}


@app.post("/api/projects/{pid}/restore/{n}")
def restore(pid: str, n: int):
    info = rev_info(pid, n); cur = project_state(pid)["current"]
    m = make_rev(pid, cur["n"], info["spec"], f"استرجاع {n}", f"استرجعت محتوى الإصدار {n}")
    return project_state(pid)


@app.get("/api/projects/{pid}/rev/{n}/{name}")
def get_file(pid: str, n: int, name: str):
    if name not in ("shirt.png", "pants.png", "shirt.psd", "pants.psd", "shirt.json", "pants.json"):
        raise HTTPException(404)
    p = os.path.join(rdir(pid, n), name)
    if not os.path.exists(p): raise HTTPException(404)
    return FileResponse(p)


@app.post("/api/projects/{pid}/hit/{n}")
def hit(pid: str, n: int, pt: dict):
    """النقر على القالب المسطح: يرجع أصغر عنصر يحتوي النقطة."""
    x, y = pt["x"], pt["y"]; best = None
    for g in ("shirt", "pants"):
        for e in json.load(open(os.path.join(rdir(pid, n), f"{g}.json"), encoding="utf-8")):
            bx, by, bw, bh = e["box"]
            if bx <= x <= bx + bw and by <= y <= by + bh and (g == pt.get("garment", g)):
                if best is None or bw * bh < best["box"][2] * best["box"][3]: best = e
    return best or {}


@app.get("/api/template")
def template_status(): return layout.load_report(DATA)


@app.post("/api/template/fetch")
def template_fetch(): return layout.fetch_template(DATA)


# ---------- فحص وتقارير وحزمة ----------
def technical_validation(pid, n):
    d = rdir(pid, n); checks = []
    tpl = layout.load_report(DATA)

    def add(cid, rule, status, evidence, limits=""):
        checks.append({"id": cid, "rule": rule, "status": status, "evidence": evidence, "limits": limits})
    for g in ("shirt", "pants"):
        im = Image.open(os.path.join(d, f"{g}.png"))
        add(f"{g}_png_size", "PNG بأبعاد القالب 585×559", "passed" if im.size == layout.SIZE and im.mode == "RGBA" else "failed",
            f"{im.size} {im.mode}")
        psd = PSDImage.open(os.path.join(d, f"{g}.psd"))
        names = [l.name for l in psd]
        add(f"{g}_psd_reopen", "إعادة فتح PSD وقراءة الطبقات", "passed" if len(names) >= 5 and psd.size == layout.SIZE else "failed",
            f"{len(names)} طبقة: {names}")
        a = im.getchannel("A")
        opaque_ok = all(a.crop((x, y, x + w, y + h)).getextrema()[0] == 255 for (p, f), (x, y, w, h) in layout.REGIONS.items())
        add(f"{g}_regions_opaque", "كل مناطق الأوجه معتمة بالكامل (لا فراغات)", "passed" if opaque_ok else "failed", "فحص alpha لكل منطقة")
        outside = im.copy(); mask = Image.new("L", layout.SIZE, 255)
        for (p, f), (x, y, w, h) in layout.REGIONS.items(): mask.paste(0, (x, y, x + w, y + h))
        stray = sum(1 for v, m in zip(a.getdata(), mask.getdata()) if m and v)
        add(f"{g}_no_stray", "لا بكسلات خارج المناطق (لا إرشادات ظاهرة)", "passed" if stray == 0 else "failed", f"{stray} بكسل خارج المناطق")
    info = rev_info(pid, n)
    locked = info["spec"]["locked"]
    if locked and info["parent"]:
        pd = rdir(pid, info["parent"])
        same = all(sha256(os.path.join(d, f"{g}.png")) == sha256(os.path.join(pd, f"{g}.png")) for g in locked)
        add("locks_respected", "الأجزاء المثبّتة لم تتغير عن الإصدار السابق", "passed" if same else "failed", f"المثبّت: {locked}")
    add("template_layout", "الخريطة مطابقة للقالب الرسمي (تغطية المناطق)",
        tpl.get("status", "not_run") if tpl.get("status") in ("passed", "failed") else "not_run",
        json.dumps(tpl.get("files", tpl.get("reason", "")), ensure_ascii=False)[:300],
        "يفحص التغطية فقط؛ اتجاه الأوجه يُثبت باختبار Studio")
    add("studio_import", "اختبار الارتداء والرفع في Roblox Studio", "not_run", "لم يُنفَّذ", "يتطلب Studio على جهاز المستخدم")
    return checks


def rights_md(info):
    return f"""# مراجعة الحقوق — الإصدار {info['n']}

هذا سجل فحص لتقليل المخاطر وليس ضمانًا قانونيًا. موافقة Roblox ليست تصريحًا من أصحاب الحقوق.

- **حالة الحقوق:** غير مفحوصة تجاريًا.
- **الاسم الداخلي:** «{info['spec']['name']}» اسم مؤقت لم يُفحص كعلامة تجارية، ولم يُطبع على أي ملف.
- **أصول الإنتاج:** كل الرسومات أشكال هندسية مولّدة بالكود في هذا التطبيق؛ لا خطوط ولا صور ولا مجسمات خارجية ولا نصوص على الملفات.
- **التشابه مع عناصر موجودة:** `not_run` — لم يُجرَ بحث بصري أو في سجلات العلامات. راجع WIPO Global Brand Database والمصادر السعودية المناسبة قبل أي اعتماد تجاري.
- **التوصية:** عند أي شك جدي، راجع مختص ملكية فكرية.
"""


def checklist_md(info, checks):
    st = {c["id"]: c["status"] for c in checks}
    return f"""# قائمة النشر — الإصدار {info['n']}

| البند | الحالة |
|---|---|
| لا نص على العنصر | passed (لا يُرسم أي نص) |
| لا أصول Roblox أو شعاراتها | passed (توليد ذاتي) |
| تصنيف صحيح: القميص Top والبنطلون Bottom (ملفان منفصلان) | passed |
| تطابق الخريطة مع القالب الرسمي | {st.get('template_layout')} |
| اختبار Studio على أجسام متعددة | not_run |
| عدم التشابه المفرط مع عناصر موجودة | not_run |
| أهلية الحساب (هوية، خطوتان، Plus/Premium) | غير متحقق حاليًا — راجع صفحتك في Roblox |
| رسم الرفع ومقدّم النشر | اقرأ القيم الحالية من واجهة الحساب وقت الرفع |

لا نشر ولا دفع يتمان من هذا التطبيق. كل الإجراءات المالية والعلنية تتم بيدك على موقع Roblox.
"""


README_AR = """# حزمة الإصدار

## ماذا أرفع؟
- `upload/classic-shirt.png` ← Create → Avatar items → Shirts (قميص)
- `upload/classic-pants.png` ← Create → Avatar items → Pants (بنطلون)
(أو من Studio عبر Avatar → Import.)

## ملفات التعديل
- `source/*.psd` ملفات بطبقات حقيقية تفتح في Photoshop أو Photopea أو Krita.

## ما الذي اختُبر؟
انظر `reports/technical-validation.json`. اختبار Studio **لم يُنفَّذ** — جرّب القطعة على Block Avatar قبل الرفع، وتأكد من اتجاه الأوجه.

## ما الذي بقي؟
الحقوق التجارية والاسم لم تُفحص (`reports/rights-review.md`). النشر والرسوم بيدك (`reports/publishing-checklist.md`).
"""


@app.get("/api/projects/{pid}/package/{n}")
def package(pid: str, n: int):
    info = rev_info(pid, n); d = rdir(pid, n); checks = technical_validation(pid, n)
    files = {"upload/classic-shirt.png": "shirt.png", "upload/classic-pants.png": "pants.png",
             "source/classic-shirt.psd": "shirt.psd", "source/classic-pants.psd": "pants.psd"}
    buf = io.BytesIO(); manifest = {"revision": n, "created": now(), "files": []}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in files.items():
            p = os.path.join(d, src); z.write(p, arc)
            manifest["files"].append({"path": arc, "bytes": os.path.getsize(p), "sha256": sha256(p),
                                      "role": "upload" if arc.startswith("upload") else "source"})
        flat = Image.new("RGBA", (585 * 2, 559), (40, 40, 46, 255))
        for i, g in enumerate(("shirt", "pants")): flat.alpha_composite(Image.open(os.path.join(d, f"{g}.png")), (585 * i, 0))
        b = io.BytesIO(); flat.save(b, "PNG"); z.writestr("previews/flat-templates.png", b.getvalue())
        col = info["spec"]["shirt"]["colors"]
        acc = accessory.export_glasses(col["base"], col["accent"])
        z.writestr("accessory/glasses.glb", acc["glb"]); z.writestr("accessory/glasses_texture.png", acc["texture"])
        z.writestr("reports/accessory-validation.json", json.dumps(acc["checks"], ensure_ascii=False, indent=2))
        for arc, data in (("accessory/glasses.glb", acc["glb"]), ("accessory/glasses_texture.png", acc["texture"])):
            manifest["files"].append({"path": arc, "bytes": len(data), "role": "accessory-source"})
        checks = checks + [c for c in acc["checks"] if c["status"] != "passed"]
        failed = [c for c in checks if c["status"] == "failed"]
        tech = {"technical_status": "failed" if failed else ("files_generated" if any(c["status"] == "not_run" for c in checks) else "local_checks_passed"),
                "rights_status": "unchecked", "publishing_status": "not_uploaded", "checks": checks}
        z.writestr("reports/technical-validation.json", json.dumps(tech, ensure_ascii=False, indent=2))
        z.writestr("reports/rights-review.md", rights_md(info))
        z.writestr("reports/publishing-checklist.md", checklist_md(info, checks))
        z.writestr("README_AR.md", README_AR)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename=roblox-set-rev{n}.zip"})


@app.get("/api/projects/{pid}/validation/{n}")
def validation(pid: str, n: int): return technical_validation(pid, n)


@app.post("/api/projects/{pid}/approve/{n}")
def approve(pid: str, n: int):
    info = rev_info(pid, n); c = db()
    c.execute("INSERT INTO approvals VALUES(?,?,?,?,?)", (pid, n, info["shirt_sha"], info["pants_sha"], now()))
    c.execute("UPDATE projects SET approved_rev=? WHERE id=?", (n, pid)); c.commit()
    return {"ok": True, "note": "اعتماد تصميم فقط؛ لا رفع ولا دفع ولا نشر.", "state": project_state(pid)}


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
