import pytest
from pydantic import ValidationError

from sourcemode.source import CharacterSource, bump_version, load_source, save_source, update_operational
from sourcemode.source.store import ApprovedVersionError


def test_roundtrip(chars_root, sample_source):
    loaded = load_source(chars_root, "testchar")
    assert loaded == sample_source


def test_id_and_version_patterns():
    with pytest.raises(ValidationError):
        CharacterSource(character_id="Bad Name", name="x", version="v001", trigger_token="t", invariants=[])
    with pytest.raises(ValidationError):
        CharacterSource(character_id="ok", name="x", version="1.0", trigger_token="t", invariants=[])


def test_invariants_capped_at_10():
    with pytest.raises(ValidationError):
        CharacterSource(
            character_id="ok", name="x", version="v001", trigger_token="t",
            invariants=[f"i{n}" for n in range(11)],
        )


def test_wardrobe_needs_default():
    with pytest.raises(ValidationError):
        CharacterSource(
            character_id="ok", name="x", version="v001", trigger_token="t",
            wardrobe_states={"armor": " in armor"},
        )


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        CharacterSource(
            character_id="ok", name="x", version="v001", trigger_token="t", surprise=1,
        )


def test_approved_version_is_immutable(chars_root, sample_source):
    approved = sample_source.model_copy(update={"approved": True})
    save_source(chars_root, approved, force=True)
    edited = approved.model_copy(update={"name": "Renamed"})
    with pytest.raises(ApprovedVersionError):
        save_source(chars_root, edited)


def test_operational_update_allowed_on_approved(chars_root, sample_source):
    save_source(chars_root, sample_source.model_copy(update={"approved": True}), force=True)
    updated = update_operational(chars_root, "testchar", identity_threshold=0.42)
    assert updated.identity_threshold == 0.42
    with pytest.raises(ValueError):
        update_operational(chars_root, "testchar", name="nope")


def test_bump_archives_and_increments(chars_root, sample_source):
    save_source(chars_root, sample_source.model_copy(update={"approved": True}), force=True)
    bumped = bump_version(chars_root, "testchar")
    assert bumped.version == "v002"
    assert bumped.approved is False
    archive = chars_root / "testchar" / "versions" / "v001.json"
    assert archive.exists()
    # and the archived copy still says v001
    assert CharacterSource.model_validate_json(archive.read_text()).version == "v001"


def test_wardrobe_suffix(sample_source):
    assert sample_source.wardrobe_suffix() == ""
    assert sample_source.wardrobe_suffix("armor") == " wearing scuffed armor"
    with pytest.raises(KeyError):
        sample_source.wardrobe_suffix("gown")


def test_gwen_source_parses(gwen_available):
    if not gwen_available:
        pytest.skip("gwen assets not present")
    from tests.conftest import GWEN_DIR, REPO_ROOT

    gwen = load_source(REPO_ROOT / "characters", "gwen")
    assert gwen.trigger_token == "gwen_ch"
    assert gwen.approved is True
    assert len(gwen.reference_images) == 5
    for rel in gwen.reference_images:
        assert (GWEN_DIR / rel).exists(), rel
