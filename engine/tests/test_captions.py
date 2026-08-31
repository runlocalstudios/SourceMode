from sourcemode.prompts.captions import clean, clean_concept


def test_clean_binds_identity_to_trigger():
    caption = "The image shows a young woman with red hair standing in a park."
    out = clean(caption, "gwen_ch", strip_terms=["red hair"])
    assert out.startswith("gwen_ch")
    assert "red hair" not in out
    assert "a young woman" not in out


def test_clean_replaces_later_persons_with_she():
    caption = "A woman walks. The woman smiles."
    out = clean(caption, "gwen_ch")
    assert out.startswith("gwen_ch")
    assert out.lower().count("gwen_ch") == 1
    assert "she" in out.lower()


def test_clean_prefixes_trigger_when_no_person_phrase():
    out = clean("standing on a hill at dusk", "gwen_ch")
    assert out.startswith("gwen_ch, ")


def test_clean_concept_keeps_subjects_generic():
    caption = "A photo of a woman pouring coffee."
    out = clean_concept(caption, "pour_cf")
    assert out.startswith("pour_cf, ")
    assert "a woman" in out.lower()
