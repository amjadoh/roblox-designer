"""محلل أوامر عربي قائم على القواعد (بدون أي مزود ذكاء اصطناعي).
يحوّل النص إلى عمليات منظمة مسموحة فقط؛ لا يُنفَّذ أي نص حر كسكربت."""
import re

COLORS = {"احمر": "#D71920", "اسود": "#111116", "ازرق": "#1F4FD8", "اخضر": "#1E9E4A", "ذهبي": "#C9A227",
          "ابيض": "#F2F2F2", "رمادي": "#6B6B73", "بنفسجي": "#6A2BB8", "برتقالي": "#E8761A", "فضي": "#B8BCC4",
          "كحلي": "#10205A", "بني": "#5A3A22", "وردي": "#E86BA8"}
ELEMENTS = {  # كلمة -> (العنصر، الثوب أو None)
    "شعار": ("emblem", "shirt"), "رمز": ("emblem", "shirt"), "خطوط": ("sleeve_stripe", "shirt"),
    "شريط": ("sleeve_stripe", "shirt"), "ياقه": ("collar", "shirt"), "رقبه": ("collar", "shirt"),
    "حزام": ("belt", "pants"), "اساور": ("cuff", None), "كفوف": ("cuff", None), "نقش": ("pattern", None),
    "زخرفه": ("pattern", None), "حبال": ("drawstrings", "shirt"), "جيب": ("pocket", None),
}
PATTERNS = {"معيني": "diamond", "سداسي": "diamond", "شيفرون": "chevron", "متعرج": "chevron", "بدون": "none"}
EXAMPLES = ["خفف الأحمر", "غمّق الأسود", "غيّر لون الهودي إلى الأزرق", "كبّر الجيب", "صغّر الشعار",
            "كبّر جيب البنطلون الكارجو", "احذف الخطوط", "أضف النقش", "ثبّت البنطلون", "تراجع"]


def norm(t):
    t = re.sub(r"[\u064B-\u065F\u0640]", "", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", t).strip()


def _has(t, *words): return any(w in t for w in words)


def parse(text, selection=None, spec=None):
    """يعيد (ops, رسالة_خطأ). كل op قاموس ببنية ثابتة."""
    t = norm(text)
    if not t: return [], "اكتب أمرًا."
    ops = []
    if _has(t, "تراجع", "ارجع للنسخه", "الغ اخر"): return [{"op": "undo"}], None
    if _has(t, "ثبت"):
        part = "pants" if _has(t, "بنطلون", "بنطال", "كارجو") else "shirt" if _has(t, "هودي", "قميص", "تيشيرت") else None
        if part: return [{"op": "lock", "part": part}], None
    if _has(t, "الغ التثبيت", "فك تثبيت", "فك"):
        return [{"op": "unlock"}], None

    part = None
    if _has(t, "بنطلون", "بنطال", "كارجو"): part = "pants"
    elif _has(t, "هودي", "قميص", "تيشيرت", "جاكيت"): part = "shirt"
    only = _has(t, "فقط")

    # عنصر مذكور أو محدد بالنقر
    el = None
    for w, (e, g) in ELEMENTS.items():
        if w in t:
            el = e
            if e == "pocket":
                el = "cargo_pocket" if part == "pants" or _has(t, "كارجو") else "pocket"
                g = "pants" if el == "cargo_pocket" else "shirt"
            part = part or g
            break
    if el is None and selection and _has(t, "هذا", "هذه", "هدا", "هاد", "ذا") and selection.get("element"):
        el = selection["element"]; part = part or selection.get("garment")
        if el == "base": el = None
    garment = part

    # تغيير حجم
    m = re.search(r"(\d+)\s*%", t)
    if _has(t, "كبر", "اكبر", "وسع", "ضخم", "زود حجم"):
        f = 1 + (int(m.group(1)) / 100 if m else 0.25)
        if el in ("pocket", "cargo_pocket", "emblem"):
            return [{"op": "scale", "element": el, "factor": f}], None
        return [], "حدّد العنصر المراد تكبيره (الجيب، الشعار) أو انقر عليه في المعاينة أولًا."
    if _has(t, "صغر", "قلل", "قلص"):
        f = 1 - (int(m.group(1)) / 100 if m else 0.2)
        if el in ("pocket", "cargo_pocket", "emblem"):
            return [{"op": "scale", "element": el, "factor": max(f, .3)}], None
        return [], "حدّد العنصر المراد تصغيره (الجيب، الشعار) أو انقر عليه في المعاينة أولًا."

    # إزالة/إضافة
    if _has(t, "احذف", "شيل", "ازل", "امسح") and el:
        return [{"op": "toggle", "element": el, "value": False}], None
    if _has(t, "اضف", "ضع", "رجع") and el:
        return [{"op": "toggle", "element": el, "value": True}], None
    for w, v in PATTERNS.items():
        if w in t and _has(t, "نقش", "زخرفه", "بدون"):
            return [{"op": "pattern", "value": v, "garment": garment}], None

    # الألوان
    named = [c for c in COLORS if c in t]
    slot = "accent" if "احمر" in t and not _has(t, "الي", "الى", "لون") else None
    if _has(t, "خفف", "خفض", "اهدا", "اهدي"):
        sl = _slot_for(t, named) or "accent"
        return [{"op": "adjust", "slot": sl, "mode": "soften", "amount": .25, "garment": garment}], None
    if _has(t, "غمق", "اغمق", "غامق"):
        sl = _slot_for(t, named) or "base"
        return [{"op": "adjust", "slot": sl, "mode": "darken", "amount": .25, "garment": garment}], None
    if _has(t, "فتح", "افتح", "فاتح"):
        sl = _slot_for(t, named) or "base"
        return [{"op": "adjust", "slot": sl, "mode": "lighten", "amount": .2, "garment": garment}], None
    if _has(t, "قوي", "شبع"):
        sl = _slot_for(t, named) or "accent"
        return [{"op": "adjust", "slot": sl, "mode": "intensify", "amount": .25, "garment": garment}], None
    if _has(t, "غير", "بدل", "خلي", "اجعل") and named:
        target = named[-1]
        sl = "accent" if _has(t, "الاحمر", "التفاصيل", "الخطوط") and target != "احمر" else "base"
        if _has(t, "الاكسنت", "التفاصيل", "الاحمر"): sl = "accent"
        return [{"op": "set_color", "slot": sl, "hex": COLORS[target], "garment": garment}], None
    return [], "ما فهمت الأمر. جرّب مثلًا: " + " ، ".join(EXAMPLES[:6])


def _slot_for(t, named):
    if "احمر" in named: return "accent"
    if "اسود" in named: return "base"
    return None


def apply(spec, ops):
    """يطبّق العمليات على نسخة من المواصفات. يعيد (spec, وصف_التغيير)."""
    import copy
    from .generate import adjust_hex
    s = copy.deepcopy(spec); msgs = []
    for o in ops:
        k = o["op"]
        if k == "lock":
            if o["part"] not in s["locked"]: s["locked"].append(o["part"])
            msgs.append("ثبّتُّ " + ("البنطلون" if o["part"] == "pants" else "الهودي"))
        elif k == "unlock":
            s["locked"] = []; msgs.append("أُلغي التثبيت")
        elif k == "scale":
            e = o["element"]; g = "pants" if e == "cargo_pocket" else "shirt"
            key = e + "_scale"; s[g][key] = round(max(.4, min(1.8, s[g][key] * o["factor"])), 3)
            msgs.append(f"{'كبّرت' if o['factor'] > 1 else 'صغّرت'} العنصر إلى {int(s[g][key] * 100)}%")
        elif k == "toggle":
            e = o["element"]; g = "pants" if e in ("cargo_pocket", "belt") else "shirt"
            if e == "cuff" or e == "pattern":
                for gg in ("shirt", "pants"):
                    if e == "pattern": s[gg]["pattern"] = "diamond" if o["value"] and gg == "shirt" else "none"
                    else: s[gg]["cuff"] = o["value"]
            elif e in s[g]: s[g][e] = o["value"]
            msgs.append(("أضفت" if o["value"] else "حذفت") + " العنصر")
        elif k == "pattern":
            gs = [o["garment"]] if o.get("garment") else ["shirt", "pants"]
            for g in gs: s[g]["pattern"] = o["value"]
            msgs.append("غيّرت النقش")
        elif k in ("adjust", "set_color"):
            gs = [o["garment"]] if o.get("garment") else ["shirt", "pants"]
            for g in gs:
                if g in s["locked"]: continue
                cur = s[g]["colors"][o["slot"]]
                s[g]["colors"][o["slot"]] = adjust_hex(cur, o["mode"], o["amount"]) if k == "adjust" else o["hex"]
            msgs.append("عدّلت اللون")
    return s, "، ".join(msgs)
