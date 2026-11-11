from copy import deepcopy

import pytest

from app.generate import DEFAULT_SPEC, render_pants, render_shirt


@pytest.mark.parametrize(
    ("garment", "render"),
    [("shirt", render_shirt), ("pants", render_pants)],
    ids=["shirt", "pants"],
)
def test_template_dimensions(garment, render):
    spec = deepcopy(DEFAULT_SPEC[garment])

    image = render(spec).composite()

    assert image.size == (585, 559)
