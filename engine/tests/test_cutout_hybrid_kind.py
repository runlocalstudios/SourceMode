"""backdrop_kind: a cool studio grey is grey, not green (2026-11-02, maya);
the grey cut solves her edge by matting (2026-11-09, fiona)."""

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


def _studio(key=(204, 203, 206)):
    rgb = np.full((140, 140, 3), key, dtype=np.float32)
    b = np.zeros((140, 140), dtype=np.float32)
    return rgb, b, key


def _grain(rgb):
    """a render has grain; a flat synthetic image leaves matting nothing to read"""
    return np.clip(rgb + np.random.default_rng(7).normal(0, 3, rgb.shape), 0, 255).astype(np.float32)


def test_a_grey_hoodie_near_the_wall_grey_keeps_its_whole_edge():
    """the grey-on-grey case every colour rule on top of BiRefNet ate"""
    rgb, b, key = _studio()
    rgb[20:120, 20:120] = (160, 160, 162)
    b[20:120, 20:120] = 1.0
    _, alpha, _ = hybrid_matte(_grain(rgb), key, "grey", b)
    assert alpha[70, 70] == 1.0 and alpha[70, 21] > 0.9 and alpha[70, 10] == 0.0


def test_wall_the_matte_kept_along_her_dark_hair_is_taken_back_out():
    """fiona work_03 (2026-11-09): grey streaks down the outside of her hair,
    called solid by BiRefNet."""
    rgb, b, key = _studio()
    rgb[20:120, 40:120] = (20, 18, 18)                 # her black hair
    rgb[20:120, 30:40] = key                          # wall between the outer strands
    rgb[20:120, 33:36] = (20, 18, 18)                 # one lock of strands inside it
    b[20:120, 26:120] = 1.0                           # BiRefNet: all of it her
    out, alpha, _ = hybrid_matte(_grain(rgb), key, "grey", b)
    assert alpha[70, 31] < 0.15 and alpha[70, 38] < 0.15   # the wall is cut
    assert alpha[70, 34] > 0.6 and alpha[70, 80] == 1.0    # the strand and the hair stay
    assert out[70, 34].mean() < 70                         # the strand is dark, not grey
