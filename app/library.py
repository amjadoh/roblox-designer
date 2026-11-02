"""المكتبة الجاهزة: ستايلات وطقوم ألوان أصلية بأسماء تناسب الأطفال.

كل شي هنا أشكال هندسية وألوان بس، بدون شعارات ولا شخصيات ولا كتابة.
الستايل يحدد الشكل (نقش، عناصر)، وطقم الألوان يحدد الألوان، فالولد يقدر يخلطهم.
تجنبنا الأسود الصافي والأبيض الصافي (حسب دروس التصميم).
"""

# طقوم الألوان: الأساسي للقميص، واللون الثاني (التفاصيل)، والأساسي للبنطلون
PALETTES = [
    {"id": "night_red", "name": "ليل وأحمر", "emoji": "🌑", "shirt": "#18181E", "accent": "#D71920", "pants": "#1E1E26"},
    {"id": "ocean", "name": "محيط", "emoji": "🌊", "shirt": "#1F4FD8", "accent": "#7FD3FF", "pants": "#10205A"},
    {"id": "desert", "name": "صحراء", "emoji": "🏜️", "shirt": "#C2A878", "accent": "#5A3A22", "pants": "#8A7350"},
    {"id": "forest", "name": "غابة", "emoji": "🌲", "shirt": "#2E5E3A", "accent": "#C9A227", "pants": "#3B3B2E"},
    {"id": "lava", "name": "حمم", "emoji": "🌋", "shirt": "#2A1A16", "accent": "#FF6A1A", "pants": "#3A2420"},
    {"id": "candy", "name": "حلاوة", "emoji": "🍬", "shirt": "#E86BA8", "accent": "#FFF0A8", "pants": "#7A4FD8"},
    {"id": "ice", "name": "ثلج", "emoji": "❄️", "shirt": "#DDE8F2", "accent": "#3A8FD8", "pants": "#6B7A8C"},
    {"id": "gold", "name": "ذهب ملكي", "emoji": "👑", "shirt": "#3A1E5A", "accent": "#E0B43A", "pants": "#24123A"},
    {"id": "toxic", "name": "سم أخضر", "emoji": "🧪", "shirt": "#1A1F1A", "accent": "#7CFF3A", "pants": "#24302A"},
    {"id": "sunset", "name": "غروب", "emoji": "🌅", "shirt": "#E8761A", "accent": "#6A2BB8", "pants": "#3A2A4A"},
    {"id": "storm", "name": "عاصفة", "emoji": "⛈️", "shirt": "#4A5060", "accent": "#F2E04A", "pants": "#2A2E38"},
    {"id": "cream", "name": "كريمي", "emoji": "🥛", "shirt": "#EDEBE6", "accent": "#5A3A22", "pants": "#6B5A48"},
]

# الستايلات: الشكل والعناصر + طقم ألوان افتراضي
STYLES = [
    {"id": "ninja", "name": "نينجا", "emoji": "🥷", "palette": "night_red",
     "shirt": {"pattern": "chevron", "pattern_opacity": 0.2, "pocket": False, "emblem": True, "emblem_scale": 0.8,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "none", "cargo_pocket": False, "belt": True, "cuff": True, "knee_seams": True}},
    {"id": "explorer", "name": "مستكشف", "emoji": "🧭", "palette": "desert",
     "shirt": {"pattern": "none", "pocket": True, "pocket_scale": 1.2, "emblem": False, "sleeve_stripe": False,
               "collar": True, "hem": True, "cuff": True, "drawstrings": True},
     "pants": {"pattern": "none", "cargo_pocket": True, "cargo_pocket_scale": 1.3, "belt": True, "cuff": True, "knee_seams": True}},
    {"id": "space", "name": "رائد فضاء", "emoji": "🚀", "palette": "ice",
     "shirt": {"pattern": "hex", "pattern_opacity": 0.15, "pocket": False, "emblem": True, "emblem_scale": 1.5,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "none", "cargo_pocket": True, "cargo_pocket_scale": 0.9, "belt": True, "cuff": True, "knee_seams": True}},
    {"id": "dragon", "name": "تنين", "emoji": "🐉", "palette": "lava",
     "shirt": {"pattern": "diamond", "pattern_opacity": 0.3, "pocket": False, "emblem": True, "emblem_scale": 1.3,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "diamond", "pattern_opacity": 0.2, "cargo_pocket": False, "belt": True, "cuff": True, "knee_seams": False}},
    {"id": "street", "name": "ستايل شارع", "emoji": "🛹", "palette": "storm",
     "shirt": {"pattern": "none", "pocket": True, "pocket_scale": 1.0, "emblem": True, "emblem_scale": 1.0,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True, "drawstrings": True},
     "pants": {"pattern": "none", "cargo_pocket": True, "cargo_pocket_scale": 1.1, "belt": False, "cuff": True, "knee_seams": True}},
    {"id": "knight", "name": "فارس", "emoji": "🛡️", "palette": "gold",
     "shirt": {"pattern": "diamond", "pattern_opacity": 0.18, "pocket": False, "emblem": True, "emblem_scale": 1.6,
               "sleeve_stripe": False, "collar": True, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "none", "cargo_pocket": False, "belt": True, "cuff": True, "knee_seams": True}},
    {"id": "robot", "name": "روبوت", "emoji": "🤖", "palette": "toxic",
     "shirt": {"pattern": "hex", "pattern_opacity": 0.25, "pocket": False, "emblem": True, "emblem_scale": 1.0,
               "sleeve_stripe": True, "collar": False, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "hex", "pattern_opacity": 0.15, "cargo_pocket": True, "cargo_pocket_scale": 0.8, "belt": True, "cuff": True, "knee_seams": True}},
    {"id": "sport", "name": "رياضي", "emoji": "⚽", "palette": "ocean",
     "shirt": {"pattern": "none", "pocket": False, "emblem": True, "emblem_scale": 0.7,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": False, "drawstrings": False},
     "pants": {"pattern": "none", "cargo_pocket": False, "belt": False, "cuff": True, "knee_seams": False}},
    {"id": "chill", "name": "مريح", "emoji": "😎", "palette": "cream",
     "shirt": {"pattern": "none", "pocket": True, "pocket_scale": 1.0, "emblem": False, "sleeve_stripe": False,
               "collar": True, "hem": True, "cuff": True, "drawstrings": True},
     "pants": {"pattern": "none", "cargo_pocket": False, "belt": False, "cuff": True, "knee_seams": False}},
    {"id": "hunter", "name": "صياد", "emoji": "🏹", "palette": "forest",
     "shirt": {"pattern": "chevron", "pattern_opacity": 0.15, "pocket": True, "pocket_scale": 0.9, "emblem": False,
               "sleeve_stripe": False, "collar": True, "hem": True, "cuff": True, "drawstrings": True},
     "pants": {"pattern": "none", "cargo_pocket": True, "cargo_pocket_scale": 1.4, "belt": True, "cuff": True, "knee_seams": True}},
    {"id": "party", "name": "حفلة", "emoji": "🎉", "palette": "candy",
     "shirt": {"pattern": "diamond", "pattern_opacity": 0.22, "pocket": False, "emblem": True, "emblem_scale": 1.2,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "none", "cargo_pocket": False, "belt": True, "cuff": True, "knee_seams": False}},
    {"id": "sunset_rider", "name": "راكب الغروب", "emoji": "🏍️", "palette": "sunset",
     "shirt": {"pattern": "chevron", "pattern_opacity": 0.25, "pocket": True, "pocket_scale": 0.8, "emblem": True, "emblem_scale": 0.9,
               "sleeve_stripe": True, "collar": True, "hem": True, "cuff": True, "drawstrings": False},
     "pants": {"pattern": "none", "cargo_pocket": True, "cargo_pocket_scale": 1.0, "belt": True, "cuff": True, "knee_seams": True}},
]

# إضافات سريعة (أزرار تشغيل/إطفاء)
EXTRAS = [
    {"id": "pocket", "name": "جيب الصدر", "emoji": "👝", "garment": "shirt", "key": "pocket"},
    {"id": "emblem", "name": "شعار هندسي", "emoji": "💠", "garment": "shirt", "key": "emblem"},
    {"id": "sleeve_stripe", "name": "خط الأكمام", "emoji": "➖", "garment": "shirt", "key": "sleeve_stripe"},
    {"id": "drawstrings", "name": "حبال الهودي", "emoji": "🪢", "garment": "shirt", "key": "drawstrings"},
    {"id": "cargo_pocket", "name": "جيوب كارجو", "emoji": "🎒", "garment": "pants", "key": "cargo_pocket"},
    {"id": "belt", "name": "حزام", "emoji": "🔗", "garment": "pants", "key": "belt"},
]

PATTERN_CHOICES = [
    {"id": "none", "name": "سادة", "emoji": "⬛"},
    {"id": "diamond", "name": "معيّنات", "emoji": "🔷"},
    {"id": "chevron", "name": "شيفرون", "emoji": "〰️"},
    {"id": "hex", "name": "خلايا", "emoji": "🐝"},
]


def palette(pid):
    return next((p for p in PALETTES if p["id"] == pid), None)


def style_patch(style_id, palette_id=None):
    """يرجع patch كامل (شكل + ألوان) لستايل، بطقم ألوانه أو بطقم ثاني."""
    st = next((s for s in STYLES if s["id"] == style_id), None)
    if not st: return None
    pal = palette(palette_id or st["palette"])
    if not pal: return None
    return {"shirt": {**st["shirt"], "colors": {"base": pal["shirt"], "accent": pal["accent"]}},
            "pants": {**st["pants"], "colors": {"base": pal["pants"], "accent": pal["accent"]}}}


def palette_patch(palette_id):
    pal = palette(palette_id)
    if not pal: return None
    return {"shirt": {"colors": {"base": pal["shirt"], "accent": pal["accent"]}},
            "pants": {"colors": {"base": pal["pants"], "accent": pal["accent"]}}}


def public():
    return {"styles": [{k: s[k] for k in ("id", "name", "emoji", "palette")} for s in STYLES],
            "palettes": PALETTES, "extras": EXTRAS, "patterns": PATTERN_CHOICES}
