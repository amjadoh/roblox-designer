"""قواعد تعديل مواصفات التصميم: المفاتيح والقيم المسموحة، والدمج.

يستخدمها الموقع (/apply) وأداة الوكيل (design_cli) عشان تكون القواعد وحدة.
"""
import copy, re

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
