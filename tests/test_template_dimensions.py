import os
import sys
from copy import deepcopy

import pytest

# يسمح بتشغيل الملف منفردًا (pytest tests/test_template_dimensions.py) وليس فقط عبر python -m pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import layout  # noqa: E402
from app.generate import DEFAULT_SPEC, render_pants, render_shirt  # noqa: E402

TEMPLATE_SIZE = (585, 559)  # مقاس قالب روبلوكس الكلاسيكي (عرض × ارتفاع)


def test_layout_size_is_classic_template():
    assert layout.SIZE == TEMPLATE_SIZE


@pytest.mark.parametrize(
    ("garment", "render"),
    [("shirt", render_shirt), ("pants", render_pants)],
    ids=["shirt", "pants"],
)
def test_template_dimensions(garment, render):
    spec = deepcopy(DEFAULT_SPEC[garment])

    layers = render(spec)
    image = layers.composite()

    assert image.size == TEMPLATE_SIZE
    assert image.mode == "RGBA"
    # كل طبقة (اللي تنحفظ في PSD) لازم تكون بنفس مقاس القالب
    assert layers.order, f"{garment}: ما فيه طبقات"
    for name in layers.order:
        assert layers.imgs[name].size == TEMPLATE_SIZE, f"{garment}/{name}"


def test_template_regions_fit_inside_template():
    w, h = TEMPLATE_SIZE
    for key, (x, y, rw, rh) in layout.REGIONS.items():
        assert x >= 0 and y >= 0 and x + rw <= w and y + rh <= h, key
