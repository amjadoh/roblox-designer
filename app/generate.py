"""توليد إجرائي لطبقات القميص والبنطلون، وتصدير PNG وPSD بطبقات حقيقية.
لا يستخدم أي أصول خارجية ولا نصوصًا ولا خطوطًا: كل شيء أشكال هندسية مرسومة بالكود."""
import colorsys, hashlib, os
from PIL import Image, ImageDraw, ImageFilter
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from .layout import SIZE, REGIONS

DEFAULT_SPEC = {
    "name": "BLACK VENOM (اسم داخلي مؤقت)",
    "shirt": {
        "colors": {"base": "#111116", "accent": "#D71920"},
        "pattern": "diamond", "pattern_opacity": 0.22,
        "pocket": True, "pocket_scale": 1.0,
        "emblem": True, "emblem_scale": 1.0,
        "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True,
        "drawstrings": True,
    },
    "pants": {
        "colors": {"base": "#111116", "accent": "#D71920"},
        "pattern": "none", "pattern_opacity": 0.15,
        "cargo_pocket": True, "cargo_pocket_scale": 1.0,
        "belt": True, "cuff": True, "knee_seams": True,
    },
    "locked": [],
}


def hex2rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(c): return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in c)


def blend(a, b, t): return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def lighten(c, t): return blend(c, (255, 255, 255), t)


def darken(c, t): return blend(c, (0, 0, 0), t)


def adjust_hex(h, mode, amount=0.2):
    c = hex2rgb(h)
    if mode == "lighten": c = lighten(c, amount)
    elif mode == "darken": c = darken(c, amount)
    else:
        hh, l, s = colorsys.rgb_to_hls(*[v / 255 for v in c])
        s = s * (1 - amount) if mode == "soften" else min(1, s * (1 + amount))
        l = min(1, l * (1 + amount * 0.5)) if mode == "soften" else l
        c = tuple(v * 255 for v in colorsys.hls_to_rgb(hh, l, s))
    return rgb2hex(c)


class Layers:
    """مجموعة طبقات RGBA بحجم القالب + سجل عناصر قابلة للتحديد بالنقر."""

    def __init__(self):
        self.order, self.imgs, self.elements = [], {}, []

    def get(self, name):
        if name not in self.imgs:
            self.imgs[name] = Image.new("RGBA", SIZE, (0, 0, 0, 0)); self.order.append(name)
        return self.imgs[name]

    def local(self, name, part, face, fn, element=None, box=None):
        """يرسم داخل منطقة محلية (0,0,w,h) ويلصقها على الطبقة بحدود المنطقة تمامًا."""
        x, y, w, h = REGIONS[(part, face)]
        tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile, "RGBA")
        fn(d, w, h)
        self.get(name).alpha_composite(tile, (x, y))
        if element:
            bx = box or (0, 0, w, h)
            self.elements.append({"element": element, "part": part, "face": face,
                                  "box": [x + bx[0], y + bx[1], bx[2], bx[3]]})

    def paste_tile(self, name, part, face, tile):
        """يلصق صورة جاهزة بحجم المنطقة (للتأثيرات اللي تحتاج تنعيم)."""
        x, y, w, h = REGIONS[(part, face)]
        self.get(name).alpha_composite(tile, (x, y))

    def fabric_on_top(self):
        """الظل والطيات فوق التفاصيل (الجيب والخطوط تنطوي مع القماش)."""
        top = [n for n in ("shade", "folds") if n in self.order]
        self.order = [n for n in self.order if n not in top] + top

    def composite(self):
        out = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        for n in self.order:
            out.alpha_composite(self.imgs[n])
        return out


def rgba(c, a=255): return tuple(int(v) for v in c) + (int(a),)


def _scale_pts(pts, cx, cy, s): return [(cx + (x - cx) * s, cy + (y - cy) * s) for x, y in pts]


def _pattern(d, w, h, kind, col, op):
    if kind == "none": return
    a = int(255 * op); step = 16
    if kind in ("diamond", "hex"):
        for k in range(-h, w + h, step):
            d.line([(k, 0), (k + h, h)], fill=rgba(col, a), width=1)
            d.line([(k, h), (k + h, 0)], fill=rgba(col, a), width=1)
    elif kind == "chevron":
        for y in range(0, h, step):
            d.line([(0, y), (w / 2, y + 8), (w, y)], fill=rgba(col, a), width=2)


# ---------- مظهر القماش (ظلال، طيات، خياطة، ملمس) ----------
# كله ثابت لكل منطقة (بدون عشوائية)، فنفس المواصفات تعطي نفس البايتات دائمًا.

def _edge_shadow(w, h, side):
    """ظل ناعم عند الحواف الرأسية (box shading). الجوانب أغمق من الأمام والخلف."""
    t = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(t)
    ew, peak = (14, 95) if side else (12, 70)
    for i in range(ew):
        a = int(peak * (1 - i / ew) ** 2)
        d.line([(i, 0), (i, h)], fill=(0, 0, 0, a)); d.line([(w - 1 - i, 0), (w - 1 - i, h)], fill=(0, 0, 0, a))
    for i in range(10):  # ظل خفيف تحت (الجاذبية)
        d.line([(0, h - 1 - i), (w, h - 1 - i)], fill=(0, 0, 0, int(45 * (1 - i / 10))))
    return t


def _folds(w, h, lines):
    """طيات: خط ظل منعّم مع لمعة فوقه بشوي (حسب دروس DevForum: اللمعة فوق الطية مو عليها)."""
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0)); hi = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ds, dh = ImageDraw.Draw(sh), ImageDraw.Draw(hi)
    for pts in lines:
        ds.line(pts, fill=(0, 0, 0, 95), width=2)
        dh.line([(x, y - 3) for x, y in pts], fill=(255, 255, 255, 45), width=2)
    sh = sh.filter(ImageFilter.GaussianBlur(1.4)); hi = hi.filter(ImageFilter.GaussianBlur(1.8))
    sh.alpha_composite(hi)
    return sh


def _sleeve_folds(w, h):
    return _folds(w, h, [[(8, 60), (w * .4, 65), (w - 14, 61)], [(w * .35, 73), (w - 8, 70)],
                         [(10, h - 33), (w * .6, h - 30)]])


def _torso_folds(w, h):
    return _folds(w, h, [[(4, 30), (22, 44)], [(w - 4, 30), (w - 22, 44)],          # تحت الإبط
                         [(10, h - 30), (w * .3, h - 26)], [(w - 10, h - 30), (w * .7, h - 26)]])


def _leg_folds(w, h):
    return _folds(w, h, [[(8, 82), (w * .45, 87), (w - 12, 83)], [(w * .3, 95), (w - 8, 92)],
                         [(10, h - 30), (w * .55, h - 27)]])


def _pants_torso_folds(w, h):
    return _folds(w, h, [[(w * .5 - 4, h - 4), (w * .5 - 16, h - 30)], [(w * .5 + 4, h - 4), (w * .5 + 16, h - 30)]])


def _stitches(w, h, col, side):
    """خياطة متقطعة داخل الحواف الرأسية."""
    t = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(t)
    for x in ((3, w - 4) if not side else (w // 2,)):
        for y in range(4, h - 4, 7):
            d.line([(x, y), (x, y + 3)], fill=rgba(col, 150), width=1)
    return t


def _texture(w, h, seed):
    """ملمس قماش خفيف: نقاط فاتحة وغامقة ثابتة."""
    import numpy as np
    rng = np.random.default_rng(seed)
    v = rng.integers(0, 2, (h, w), dtype=np.uint8) * 255
    a = (rng.random((h, w)) * 14).astype(np.uint8)
    arr = np.dstack([v, v, v, a])
    return Image.fromarray(arr, "RGBA")


def _seed(*keys):
    return int(hashlib.sha256("/".join(keys).encode()).hexdigest()[:8], 16)


def add_fabric(L, garment, faces, base):
    stitch = darken(base, .45) if sum(base) > 200 else lighten(base, .28)
    for p, f in faces:
        x, y, w, h = REGIONS[(p, f)]
        L.paste_tile("texture", p, f, _texture(w, h, _seed(garment, p, f)))
        if f in ("up", "down"): continue
        L.paste_tile("shade", p, f, _edge_shadow(w, h, side=f in ("left", "right")))
        if p == "torso":
            if garment == "shirt": L.paste_tile("folds", p, f, _torso_folds(w, h))
            elif f in ("front", "back"): L.paste_tile("folds", p, f, _pants_torso_folds(w, h))
            if f in ("front", "back"): L.paste_tile("stitching", p, f, _stitches(w, h, stitch, side=False))
        else:
            L.paste_tile("folds", p, f, _sleeve_folds(w, h) if garment == "shirt" else _leg_folds(w, h))
            if f in ("left", "right"): L.paste_tile("stitching", p, f, _stitches(w, h, stitch, side=True))


def render_shirt(s):
    L = Layers(); c = s["colors"]
    base, acc = hex2rgb(c["base"]), hex2rgb(c["accent"]); trim = lighten(base, 0.10)
    parts = ["torso", "limbA", "limbB"]
    faces = [(p, f) for (p, f) in REGIONS if p in parts]
    for p, f in faces:
        L.local("base", p, f, lambda d, w, h: d.rectangle([0, 0, w, h], fill=rgba(base)),
                element="base" if f == "front" and p == "torso" else None)
    for p, f in faces:
        if f in ("up", "down"): continue
        L.local("pattern", p, f, lambda d, w, h: _pattern(d, w, h, s["pattern"], acc, s["pattern_opacity"]),
                element="pattern" if (p, f) == ("torso", "front") and s["pattern"] != "none" else None)
    add_fabric(L, "shirt", faces, base)
    for p, f in faces:
        if f == "down": L.local("shade", p, f, lambda d, w, h: d.rectangle([0, 0, w, h], fill=(0, 0, 0, 70)))
        if f == "up": L.local("shade", p, f, lambda d, w, h: d.rectangle([0, 0, w, h], fill=(255, 255, 255, 18)))
    if s["sleeve_stripe"]:
        for p in ("limbA", "limbB"):
            for f in ("right", "left", "front", "back"):
                def st(d, w, h):
                    d.rectangle([w // 2 - 8, 0, w // 2 - 6, h - 20], fill=rgba(trim))
                    d.rectangle([w // 2 - 4, 0, w // 2 + 1, h - 20], fill=rgba(acc))
                    d.rectangle([w // 2 + 3, 0, w // 2 + 5, h - 20], fill=rgba(trim))
                L.local("sleeve_stripe", p, f, st, element="sleeve_stripe" if (p, f) == ("limbA", "right") else None,
                        box=(24, 0, 16, 108) if (p, f) == ("limbA", "right") else None)
    if s["hem"]:
        for f in ("front", "back", "left", "right"):
            def hem(d, w, h):
                d.rectangle([0, h - 16, w, h], fill=rgba(trim)); d.rectangle([0, h - 18, w, h - 17], fill=rgba(acc))
            L.local("hem", "torso", f, hem, element="hem" if f == "front" else None, box=(0, 110, 128, 18))
    if s["cuff"]:
        for p in ("limbA", "limbB"):
            for f in ("right", "left", "front", "back"):
                def cuff(d, w, h):
                    d.rectangle([0, h - 18, w, h], fill=rgba(trim)); d.rectangle([0, h - 20, w, h - 19], fill=rgba(acc))
                L.local("cuffs", p, f, cuff, element="cuff" if (p, f) == ("limbA", "front") else None, box=(0, 108, 64, 20))
            L.local("cuffs", p, "down", lambda d, w, h: d.rectangle([0, 0, w, h], fill=rgba(trim)))
    if s["collar"]:
        L.local("collar", "torso", "up", lambda d, w, h: d.rectangle([0, 0, w, h], fill=rgba(trim)))
        def cf(d, w, h):
            d.polygon([(34, 0), (94, 0), (64, 36)], fill=rgba(trim)); d.line([(34, 0), (64, 36), (94, 0)], fill=rgba(acc), width=2)
        L.local("collar", "torso", "front", cf, element="collar", box=(34, 0, 60, 36))
        L.local("collar", "torso", "back", lambda d, w, h: (d.rectangle([0, 0, w, 12], fill=rgba(trim)), d.line([(0, 13), (w, 13)], fill=rgba(acc), width=2)))
    if s["pocket"]:
        k = s["pocket_scale"]; pw, ph = 84 * k, 28 * k; cx = 64; bot = 108; top = bot - ph
        def pk(d, w, h):
            poly = [(cx - pw * .4, top), (cx + pw * .4, top), (cx + pw / 2, bot), (cx - pw / 2, bot)]
            d.polygon(poly, fill=rgba(darken(base, .25), 235)); d.line(poly + [poly[0]], fill=rgba(acc), width=2)
            d.line([(cx, top), (cx, bot)], fill=rgba(acc, 150), width=1)
        L.local("pocket", "torso", "front", pk, element="pocket", box=(int(cx - pw / 2), int(top), int(pw), int(ph)))
    if s["drawstrings"] and s["collar"]:
        def ds(d, w, h):
            for x in (50, 78):
                d.line([(x, 20), (x - 2 if x < 64 else x + 2, 44)], fill=(215, 215, 220, 255), width=2)
                d.ellipse([x - 7 if x < 64 else x + 1, 43, x - 1 if x < 64 else x + 7, 49], fill=rgba(acc))
        L.local("drawstrings", "torso", "front", ds)
    if s["emblem"]:
        k = s["emblem_scale"]; cx, cy = 64, 60
        def em(d, w, h):
            for pts in ([(52, 50), (62, 50), (59, 70)], [(66, 50), (76, 50), (69, 70)]):
                d.polygon(_scale_pts(pts, cx, cy, k), fill=rgba(acc))
        L.local("emblem", "torso", "front", em, element="emblem",
                box=(int(cx - 14 * k), int(cy - 12 * k), int(28 * k), int(24 * k)))
    L.fabric_on_top()
    return L


def render_pants(s):
    L = Layers(); c = s["colors"]
    base, acc = hex2rgb(c["base"]), hex2rgb(c["accent"]); trim = lighten(base, 0.10)
    faces = [(p, f) for (p, f) in REGIONS]
    for p, f in faces:
        L.local("base", p, f, lambda d, w, h: d.rectangle([0, 0, w, h], fill=rgba(base)),
                element="base" if (p, f) == ("limbA", "front") else None)
    for p, f in faces:
        if f in ("up", "down"): continue
        L.local("pattern", p, f, lambda d, w, h: _pattern(d, w, h, s["pattern"], acc, s["pattern_opacity"]))
    add_fabric(L, "pants", faces, base)
    for p, f in faces:
        if f == "down": L.local("shade", p, f, lambda d, w, h: d.rectangle([0, 0, w, h], fill=(0, 0, 0, 70)))
    if s["belt"]:
        for f in ("front", "back", "left", "right"):
            def belt(d, w, h):
                d.rectangle([0, 0, w, 18], fill=rgba(darken(base, .35))); d.rectangle([0, 18, w, 19], fill=rgba(acc))
                if w == 128:
                    d.rectangle([54, 3, 74, 15], outline=rgba(acc), width=2)
            L.local("belt", "torso", f, belt, element="belt" if f == "front" else None, box=(0, 0, 128, 20))
    if s["knee_seams"]:
        for p in ("limbA", "limbB"):
            for f in ("front", "back"):
                L.local("knee", p, f, lambda d, w, h: d.line([(0, 76), (w, 76)], fill=(0, 0, 0, 110), width=2))
    if s["cargo_pocket"]:
        k = s["cargo_pocket_scale"]
        for p, f in (("limbA", "right"), ("limbB", "left")):
            def cp(d, w, h):
                pw, ph = 46 * k, 46 * k; x0 = (w - pw) / 2; y0 = 38
                d.rectangle([x0, y0, x0 + pw, y0 + ph], fill=rgba(darken(base, .2), 240), outline=rgba(acc), width=2)
                d.rectangle([x0, y0, x0 + pw, y0 + 14 * k], fill=rgba(trim), outline=rgba(acc), width=2)
                d.ellipse([w / 2 - 3, y0 + 8 * k, w / 2 + 3, y0 + 8 * k + 6], fill=rgba(acc))
            L.local("cargo_pocket", p, f, cp, element="cargo_pocket" if p == "limbA" else None,
                    box=(int(32 - 23 * k), 38, int(46 * k), int(46 * k)))
    if s["cuff"]:
        for p in ("limbA", "limbB"):
            for f in ("right", "left", "front", "back"):
                def cuff(d, w, h):
                    d.rectangle([0, h - 18, w, h], fill=rgba(trim)); d.rectangle([0, h - 20, w, h - 19], fill=rgba(acc))
                L.local("cuffs", p, f, cuff, element="cuff" if (p, f) == ("limbA", "front") else None, box=(0, 108, 64, 20))
    L.fabric_on_top()
    return L


# ---------- التصدير ----------
def save_png(img, path): img.save(path, "PNG")


def save_psd(layers, path):
    psd = PSDImage.new("RGBA", SIZE)
    for n in layers.order:
        psd.append(PixelLayer.frompil(layers.imgs[n], psd, n))
    psd.save(path)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""): h.update(ch)
    return h.hexdigest()


def render_revision(spec, outdir, reuse=None, reuse_parts=()):
    """يرسم القميص والبنطلون. الجزء المقفل يُنسخ بايتًا ببايت من الإصدار السابق (reuse)."""
    os.makedirs(outdir, exist_ok=True)
    meta = {"elements": []}
    for part, fn in (("shirt", render_shirt), ("pants", render_pants)):
        png, psd = (os.path.join(outdir, f"{part}.png"), os.path.join(outdir, f"{part}.psd"))
        if reuse and part in reuse_parts and os.path.exists(os.path.join(reuse, f"{part}.png")):
            import shutil
            for ext in ("png", "psd", "json"):
                src = os.path.join(reuse, f"{part}.{ext}")
                if os.path.exists(src): shutil.copyfile(src, os.path.join(outdir, f"{part}.{ext}"))
            import json
            meta["elements"] += json.load(open(os.path.join(outdir, f"{part}.json"), encoding="utf-8"))
            continue
        L = fn(spec[part])
        for e in L.elements: e["garment"] = part
        save_png(L.composite(), png); save_psd(L, psd)
        import json
        json.dump(L.elements, open(os.path.join(outdir, f"{part}.json"), "w", encoding="utf-8"))
        meta["elements"] += L.elements
    return meta
