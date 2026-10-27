from sourcemode.assets import selfies as S


def test_half_the_selfies_are_shot_straight_on_and_the_mirror_slots_are_untouched():
    looks = {cat: [{"outfit": "a tee", "hair": "loose"}] * n for cat, n in S.GROUPS}
    sl = S.slots(looks)
    plain = [s for s in sl if s["shot_type"] == S.SHOT_TYPE]
    level = [s for s in plain if S.LEVEL in s["stance"]]
    assert abs(len(level) - len(plain) / 2) <= 1
    assert all(S.LEVEL not in s["stance"] for s in sl if s["shot_type"] != S.SHOT_TYPE)
