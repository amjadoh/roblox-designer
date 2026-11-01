"""خريطة قالب الملابس الكلاسيكية + التحقق منها مقابل القالب الرسمي.

تنبيه: الإحداثيات هنا "افتراضية غير متحقق منها" حتى ينجح validate_template على
القالب الرسمي الذي ينزّله التطبيق من Roblox على جهازك. التحقق يفحص التغطية فقط
(أن المناطق تقع على المربعات المرسومة في القالب)، ولا يثبت صحة تسمية الأوجه؛
اختبار Studio هو الفيصل في اتجاه الأوجه.
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


def _limb(name, x0):
    for i, f in enumerate(["right", "front", "left", "back"]):
        REGIONS[(name, f)] = (x0 + 66 * i, 355, 64, 128)
    REGIONS[(name, "up")] = (x0 + 66, 289, 64, 64)
    REGIONS[(name, "down")] = (x0 + 66, 485, 64, 64)


_torso(); _limb("limbA", 19); _limb("limbB", 308)

SHIRT_PARTS = ["torso", "limbA", "limbB"]
PANTS_PARTS = ["torso", "limbA", "limbB"]


def regions_of(parts):
    return {k: v for k, v in REGIONS.items() if k[0] in parts}


def validate_template(img, min_cover=0.9, max_outside=0.03):
    """يتحقق أن المناطق المعرّفة تقع على بكسلات معتمة في القالب وأن لا شيء كبير خارجها."""
    img = img.convert("RGBA")
    if img.size != SIZE:
        return {"status": "failed", "reason": f"أبعاد القالب {img.size} لا تطابق {SIZE}"}
    a = img.getchannel("A").point(lambda v: 255 if v > 20 else 0)
    total = sum(1 for v in a.getdata() if v)
    if total == 0:
        return {"status": "failed", "reason": "القالب شفاف بالكامل"}
    inside = 0
    worst = 1.0
    for (p, f), (x, y, w, h) in REGIONS.items():
        c = a.crop((x, y, x + w, y + h))
        n = sum(1 for v in c.getdata() if v)
        cover = n / (w * h)
        worst = min(worst, cover)
        inside += n
    outside = (total - inside) / total
    ok = worst >= min_cover and outside <= max_outside
    return {"status": "passed" if ok else "failed", "worst_region_cover": round(worst, 3),
            "outside_fraction": round(outside, 3),
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
