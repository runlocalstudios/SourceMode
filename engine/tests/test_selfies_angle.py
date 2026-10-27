from sourcemode.assets import selfies as S


def test_half_the_selfies_are_shot_straight_on_and_the_mirror_slots_are_untouched():
    looks = {cat: [{"outfit": "a tee", "hair": "loose"}] * n for cat, n in S.GROUPS}
    sl = S.slots(looks)
    plain = [s for s in sl if s["shot_type"] == S.SHOT_TYPE]
    level = [s for s in plain if S.LEVEL in s["stance"]]
    assert abs(len(level) - len(plain) / 2) <= 1
    assert all(S.LEVEL not in s["stance"] for s in sl if s["shot_type"] != S.SHOT_TYPE)


def test_a_mirror_selfie_gets_one_gaze_target_and_refuses_crossed_eyes():
    looks = {cat: [{"outfit": "a tee", "hair": "loose"}] * n for cat, n in S.GROUPS}
    mirrors = [s for s in S.slots(looks) if s["shot_type"] != S.SHOT_TYPE]
    assert mirrors and all(s["gaze"] == S.MIRROR_GAZE and "crossed eyes" in s["negative"] for s in mirrors)


def test_a_bed_selfie_rests_on_the_bed_and_refuses_sinking_into_it():
    looks = {cat: [{"outfit": "a tee", "hair": "loose"}] * n for cat, n in S.GROUPS}
    sl = S.slots(looks)
    bed = [s for s in sl if s["shot_type"] == S.SHOT_TYPE and S.BED_RE.search(s["setting"])]
    assert bed and all(S.BED_PLACE in s["stance"] and "sinking into the mattress" in s["negative"] for s in bed)
    assert all(S.BED_PLACE not in s["stance"] for s in sl if s not in bed)
