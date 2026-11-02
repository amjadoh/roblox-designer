import copy, datetime, io, json, os, sqlite3, threading, uuid, zipfile
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from psd_tools import PSDImage

from . import accessory, commands, layout, library
from .spec import SpecError, merge, validate_patch
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
    CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, base_rev INTEGER,
        text TEXT, status TEXT DEFAULT 'pending', created TEXT, reply TEXT, reply_rev INTEGER, replied_at TEXT,
        notified INTEGER DEFAULT 0);
    """)
    if "kind" not in [r[1] for r in c.execute("PRAGMA table_info(approvals)")]:
        c.execute("ALTER TABLE approvals ADD COLUMN kind TEXT DEFAULT 'design'"); c.commit()
    return c


def rdir(pid, n): return os.path.join(DATA, "projects", pid, f"rev_{n}")
def now(): return datetime.datetime.utcnow().isoformat() + "Z"


# قفل كتابة واحد: يمنع أمرين متزامنين من إنشاء نفس رقم الإصدار أو الكتابة فوق بعض
WRITE_LOCK = threading.RLock()


def stale(pid, base):
    """يرجع رسالة لو الأمر مبني على إصدار أقدم من الحالي، وإلا None."""
    if base is None: return None
    cur = db().execute("SELECT current_rev FROM projects WHERE id=?", (pid,)).fetchone()
    if cur and cur[0] != base:
        return (f"الأمر مبني على الإصدار {base}، بس صار فيه إصدار أحدث ({cur[0]}). "
                "ما عدّلت شي عشان ما أكتب فوقه. شوف الإصدار الحالي وأعد الأمر.")
    return None


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
    base_revision: int | None = None  # الإصدار اللي شافه المستخدم وقت كتابة الأمر


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
    with WRITE_LOCK:
        return _command(pid, body)


def _command(pid, body):
    st = project_state(pid); cur = st["current"]
    if not body.text.strip(): raise HTTPException(400, "أمر فارغ")
    msg_stale = stale(pid, body.base_revision)
    if msg_stale: return {"ok": False, "conflict": True, "reply": msg_stale, "state": st}
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


@app.get("/api/library")
def get_library(): return library.public()


class Action(BaseModel):
    action: str                      # style | palette | pattern | toggle | color | scale | surprise
    style: str | None = None
    palette: str | None = None
    value: str | bool | None = None
    garment: str | None = None
    key: str | None = None           # اسم العنصر للـ toggle و scale
    slot: str | None = None          # base | accent
    hex: str | None = None
    factor: float | None = None
    base_revision: int | None = None


TOGGLES = {"shirt": ("pocket", "emblem", "sleeve_stripe", "collar", "hem", "cuff", "drawstrings"),
           "pants": ("cargo_pocket", "belt", "cuff", "knee_seams")}
SCALES = {"pocket": "shirt", "emblem": "shirt", "cargo_pocket": "pants"}
NAMES = {"pocket": "جيب الصدر", "emblem": "الشعار", "sleeve_stripe": "خط الأكمام", "collar": "الياقة", "hem": "الحاشية",
         "cuff": "الأساور", "drawstrings": "حبال الهودي", "cargo_pocket": "جيوب الكارجو", "belt": "الحزام", "knee_seams": "خياطة الركبة"}
GARMENT = {"shirt": "الهودي", "pants": "البنطلون"}


def action_patch(a: Action, spec):
    """يحوّل ضغطة زر لـ patch مسموح ورسالة. يرجع (patch, رسالة) أو يرفع SpecError."""
    import random
    if a.action == "surprise":
        st = random.choice(library.STYLES); pal = random.choice(library.PALETTES)
        return library.style_patch(st["id"], pal["id"]), f"مفاجأة! {st['emoji']} {st['name']} بألوان {pal['emoji']} {pal['name']}"
    if a.action == "style":
        p = library.style_patch(a.style, a.palette)
        if not p: raise SpecError("ستايل غير معروف")
        st = next(x for x in library.STYLES if x["id"] == a.style)
        return p, f"لبّستك ستايل {st['emoji']} {st['name']}"
    if a.action == "palette":
        p = library.palette_patch(a.palette)
        if not p: raise SpecError("ألوان غير معروفة")
        pal = library.palette(a.palette)
        return p, f"غيّرت الألوان لـ {pal['emoji']} {pal['name']}"
    gs = [a.garment] if a.garment in ("shirt", "pants") else ["shirt", "pants"]
    if a.action == "pattern":
        return {g: {"pattern": a.value} for g in gs}, "غيّرت النقش"
    if a.action == "toggle":
        g = a.garment if a.garment in TOGGLES else SCALES.get(a.key, "shirt")
        if a.key not in TOGGLES[g]: raise SpecError("عنصر غير معروف")
        v = (not spec[g][a.key]) if a.value is None else bool(a.value)
        return {g: {a.key: v}}, ("أضفت " if v else "شلت ") + NAMES[a.key]
    if a.action == "color":
        if a.slot not in ("base", "accent"): raise SpecError("لون غير معروف")
        what = "اللون الأساسي" if a.slot == "base" else "لون التفاصيل"
        return {g: {"colors": {a.slot: a.hex}} for g in gs}, f"غيّرت {what}" + (f" في {GARMENT[gs[0]]}" if len(gs) == 1 else "")
    if a.action == "scale":
        g = SCALES.get(a.key)
        if not g or not a.factor: raise SpecError("ما يتكبّر هذا العنصر")
        k = a.key + "_scale"; v = round(max(.4, min(1.8, spec[g][k] * a.factor)), 3)
        return {g: {k: v}}, f"{'كبّرت' if a.factor > 1 else 'صغّرت'} {NAMES[a.key]}"
    raise SpecError("أمر غير معروف")


@app.post("/api/projects/{pid}/apply")
def apply_action(pid: str, a: Action):
    with WRITE_LOCK:
        st = project_state(pid); cur = st["current"]
        msg_stale = stale(pid, a.base_revision)
        if msg_stale: return {"ok": False, "conflict": True, "reply": msg_stale, "state": st}
        try:
            patch, msg = action_patch(a, cur["spec"])
            validate_patch(patch)
        except SpecError as e:
            return {"ok": False, "reply": f"ما قدرت: {e}", "state": st}
        spec = merge(cur["spec"], patch)
        locked = [g for g in cur["spec"]["locked"] if g in patch]
        for g in cur["spec"]["locked"]: spec[g] = cur["spec"][g]
        if spec == cur["spec"]:
            why = f" ({'، '.join(GARMENT[g] for g in locked)} مثبّت)" if locked else ""
            return {"ok": False, "reply": "ما تغيّر شي" + why + ".", "state": st}
        n = make_rev(pid, cur["n"], spec, a.action, msg)
        return {"ok": True, "reply": msg + " ✨", "state": project_state(pid)}


class FreeRequest(BaseModel):
    text: str
    base_revision: int | None = None


@app.post("/api/projects/{pid}/requests")
def create_request(pid: str, body: FreeRequest):
    """طلب حر يروح لكلود (Claude Code) عن طريق الطابور؛ ما يتنفذ أي شي تلقائيًا هنا."""
    project_state(pid)  # 404 لو المشروع مو موجود
    t = " ".join(body.text.split())
    if not t: raise HTTPException(400, "طلب فاضي")
    if len(t) > 300: raise HTTPException(400, "الطلب طويل، اختصره (300 حرف بالكثير)")
    with WRITE_LOCK:
        c = db()
        if c.execute("SELECT COUNT(*) FROM requests WHERE project_id=? AND status='pending'", (pid,)).fetchone()[0] >= 3:
            raise HTTPException(429, "عندك 3 طلبات تنتظر كلود. استنى لين يرد عليها.")
        cur = c.execute("INSERT INTO requests(project_id, base_rev, text, created) VALUES(?,?,?,?)",
                        (pid, body.base_revision, t, now()))
        c.commit(); rid = cur.lastrowid
    return {"ok": True, "id": rid, "reply": "وصل طلبك لكلود ✅ بيرد عليك هنا أول ما يخلص."}


@app.get("/api/projects/{pid}/requests")
def list_requests(pid: str):
    rows = db().execute("SELECT id, base_rev, text, status, created, reply, reply_rev, replied_at FROM requests "
                        "WHERE project_id=? ORDER BY id DESC LIMIT 20", (pid,))
    return [dict(r) for r in rows]


@app.post("/api/projects/{pid}/restore/{n}")
def restore(pid: str, n: int, base_revision: int | None = None):
    with WRITE_LOCK:
        msg_stale = stale(pid, base_revision)
        if msg_stale: raise HTTPException(409, msg_stale)
        info = rev_info(pid, n); cur = project_state(pid)["current"]
        make_rev(pid, cur["n"], info["spec"], f"استرجاع {n}", f"استرجعت محتوى الإصدار {n}")
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


@app.get("/api/template/regions")
def template_regions():
    """خريطة الأوجه للمعاينة ثلاثية الأبعاد: {part: {face: [x, y, w, h]}}."""
    out = {}
    for (p, f), box in layout.REGIONS.items(): out.setdefault(p, {})[f] = list(box)
    return out


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


def rights_blockers(info):
    """البنود اللي تمنع الاعتماد التجاري. ما فيه فحص حقوق آلي، فكلها مفتوحة لين تنحسم يدويًا."""
    return [
        f"اسم الطقم «{info['spec']['name']}» ما انفحص كعلامة تجارية (WIPO والمصادر السعودية).",
        "التشابه مع قطع موجودة في متجر روبلوكس ما انفحص (not_run).",
        "اختبار Roblox Studio للإصدار نفسه ما انفّذ (not_run).",
    ]


@app.post("/api/projects/{pid}/approve/{n}")
def approve(pid: str, n: int, kind: str = "design"):
    with WRITE_LOCK:
        info = rev_info(pid, n)
        if kind not in ("design", "commercial"): raise HTTPException(400, "نوع اعتماد غير معروف")
        if kind == "commercial":
            b = rights_blockers(info)
            return {"ok": False, "blocked": True, "blockers": b,
                    "note": "ما أقدر أعتمد هالإصدار للبيع لين تنحسم هالبنود: " + " / ".join(b),
                    "state": project_state(pid)}
        c = db()
        c.execute("INSERT INTO approvals(project_id, rev, shirt_sha, pants_sha, created, kind) VALUES(?,?,?,?,?,?)",
                  (pid, n, info["shirt_sha"], info["pants_sha"], now(), kind))
        c.execute("UPDATE projects SET approved_rev=? WHERE id=?", (n, pid)); c.commit()
        return {"ok": True, "note": "اعتماد تصميم فقط؛ لا رفع ولا دفع ولا نشر.", "state": project_state(pid)}


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
