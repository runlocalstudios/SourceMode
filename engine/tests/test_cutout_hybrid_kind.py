"""backdrop_kind: a cool studio grey is grey, not green (2026-11-02, maya)."""

import numpy as np

from sourcemode.assets.cutout import backdrop_kind, hybrid_matte


def test_a_cool_grey_backdrop_is_grey_and_the_matte_does_not_crash():
    key = (180, 190, 200)
    assert backdrop_kind(key, 9.7) == "grey"
    assert backdrop_kind((40, 200, 60), 5.0) == "green"
    assert backdrop_kind((230, 40, 150), 5.0) == "pink"
    rgb = np.full((8, 8, 3), key, dtype=np.float32)
    b = np.zeros((8, 8), dtype=np.float32); b[2:6, 2:6] = 1.0
    _, alpha, _ = hybrid_matte(rgb, key, backdrop_kind(key, 9.7), b)
    assert alpha[3, 3] == 1.0 and alpha[0, 0] == 0.0
