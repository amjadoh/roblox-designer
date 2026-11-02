"""خريطة قالب الملابس الكلاسيكية + التحقق منها مقابل القالب الرسمي.

الخريطة مطابقة لقالب روبلوكس الرسمي (Template-Shirts-R15 و Template-Pants-R15)،
وتحققنا منها بالبكسل في 2026-11-02. التحقق يثبت مواقع المربعات وتسمية الأوجه كما
هي مكتوبة على القالب؛ تجربة Studio تبقى الفيصل في الشكل النهائي على الشخصية.
"""
import hashlib, io, json, os, urllib.request, zipfile
from PIL import Image

SIZE = (585, 559)
TEMPLATE_URL = "https://prod.docsiteassets.roblox.com/assets/accessories/classic-clothing/Classic-Clothing-Templates.zip"

# (x, y, w, h) لكل وجه. limbA = اليمنى (ذراع/ساق)، limbB = اليسرى.
REGIONS = {}


def _torso():
    REGIONS[("torso", "up")] = (231, 8, 128, 64)
    REGIONS[("torso", "right")] = (165, 74, 64, 128)
    REGIONS[("torso", "front")] = (231, 74, 128, 128)
    REGIONS[("torso", "left")] = (361, 74, 64, 128)
    REGIONS[("torso", "back")] = (427, 74, 128, 128)
    REGIONS[("torso", "down")] = (231, 204, 128, 64)


def _limb(name, x0, order, ud_col):
    # ترتيب الأعمدة من القالب الرسمي (R15): اليمين L B R F، واليسار F L B R؛
    # ومربعا U و D فوق وتحت عمود F.
    for i, f in enumerate(order):
        REGIONS[(name, f)] = (x0 + 66 * i, 355, 64, 128)
    REGIONS[(name, "up")] = (x0 + 66 * ud_col, 289, 64, 64)
    REGIONS[(name, "down")] = (x0 + 66 * ud_col, 485, 64, 64)


_torso()
_limb("limbA", 19, ["left", "back", "right", "front"], 3)
_limb("limbB", 308, ["front", "left", "back", "right"], 0)

SHIRT_PARTS = ["torso", "limbA", "limbB"]
PANTS_PARTS = ["torso", "limbA", "limbB"]


def regions_of(parts):
    return {k: v for k, v in REGIONS.items() if k[0] in parts}


def _is_face(px):
    """بكسل وجه في القالب الرسمي: ملوّن (مشبع) أو حرف أبيض داخل الوجه."""
    r, g, b = px[:3]
    return max(r, g, b) - min(r, g, b) > 60 or min(r, g, b) > 245


def _is_colored(px):
    r, g, b = px[:3]
    return max(r, g, b) - min(r, g, b) > 60


def validate_template(img, min_cover=0.97, max_outside=0.03):
    """يقارن خريطتنا بالقالب الرسمي.

    القالب الرسمي خلفيته رمادية معتمة والأوجه مربعات ملوّنة، فنقيس:
    - تغطية كل منطقة عندنا بلون وجه (لازم تقريبًا كاملة)،
    - والبكسلات الملوّنة خارج مناطقنا (لازم قليلة؛ نستثني رسمة المجسم أعلى اليسار).
    """
    img = img.convert("RGB")
    if img.size != SIZE:
        return {"status": "failed", "reason": f"أبعاد القالب {img.size} لا تطابق {SIZE}"}
    px = img.load(); W, H = SIZE
    worst, worst_face = 1.0, None
    for key, (x, y, w, h) in REGIONS.items():
        n = sum(1 for yy in range(y, y + h) for xx in range(x, x + w) if _is_face(px[xx, yy]))
        cover = n / (w * h)
        if cover < worst: worst, worst_face = cover, "/".join(key)
    mask = Image.new("L", SIZE, 0)
    for (x, y, w, h) in REGIONS.values(): mask.paste(255, (x, y, x + w, y + h))
    m = mask.load(); total = outside = 0
    for yy in range(H):
        for xx in range(W):
            if xx < 160 and yy < 285: continue  # رسمة المجسم التوضيحية
            if _is_colored(px[xx, yy]):
                total += 1
                if not m[xx, yy]: outside += 1
    out = outside / total if total else 1.0
    ok = worst >= min_cover and out <= max_outside
    return {"status": "passed" if ok else "failed", "worst_region_cover": round(worst, 3),
            "worst_region": worst_face, "outside_fraction": round(out, 3),
            "reason": None if ok else "المناطق لا تطابق مربعات القالب الرسمي"}


def fetch_template(cache_dir):
    """ينزّل القالب الرسمي ويجرّب كل PNG فيه. يعيد تقريرًا؛ لا يختلق نجاحًا عند الفشل."""
    os.makedirs(cache_dir, exist_ok=True)
    rep = {"url": TEMPLATE_URL, "status": "not_run"}
    try:
        req = urllib.request.Request(TEMPLATE_URL, headers={"User-Agent": "roblox-designer/1"})
        data = urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:  # شبكة/حجب
        rep.update(status="blocked", reason=f"تعذّر التنزيل: {e}")
        _save(cache_dir, rep); return rep
    rep["sha256"] = hashlib.sha256(data).hexdigest()
    results = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.lower().endswith(".png"):
                try:
                    r = validate_template(Image.open(io.BytesIO(z.read(n))))
                except Exception as e:
                    r = {"status": "failed", "reason": str(e)}
                results.append({"file": n, **r})
    rep["files"] = results
    rep["status"] = "passed" if any(r["status"] == "passed" for r in results) else "failed"
    rep["checked_at"] = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    _save(cache_dir, rep)
    return rep


def _save(cache_dir, rep):
    with open(os.path.join(cache_dir, "template_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)


def load_report(cache_dir):
    p = os.path.join(cache_dir, "template_report.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {"status": "not_run", "reason": "لم يُنزَّل القالب الرسمي بعد"}
