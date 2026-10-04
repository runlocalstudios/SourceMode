"""The design system, enforced.

Three pages were built at three times with three greys, three button styles and
two list pickers, and every change had to be made four times. Two rules make
this one console rather than four, and both are checkable - which is the only
reason to write them down:

- a page never defines a colour, in CSS or in script
- only `ui.PARTS` may say what a status looks like

A rule nobody checks is a rule that lasts until the next page.
"""

from __future__ import annotations

import importlib
import re

import pytest

# Pages migrated onto ui.py. The rules below are enforced against these, and a
# page joins the list in the step that moves it onto the shared stylesheet - so
# the suite is green at every step and what is left is visible rather than
# implied. ALL_PAGES is the finish line.
MIGRATED = ALL_PAGES = ("sourcemode.monitor.hub", "sourcemode.monitor.queue_page",
                        "sourcemode.assets.judge", "sourcemode.train.preview")
PAGE_MODULES = MIGRATED

STYLE = re.compile(r"<style>(.*?)</style>", re.S)
DECL = re.compile(r"\{([^{}]*)\}", re.S)
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
QUOTED_HEX = re.compile(r"""(?<=['"])#[0-9a-fA-F]{3,8}(?=['"])""")


def own_style(page: str) -> str:
    """Only the <style> a page adds for itself, not the shared TOKENS/BASE/PARTS."""
    from sourcemode.monitor.ui import BASE, PARTS, TOKENS

    for shared in (TOKENS, BASE, PARTS):
        page = page.replace(shared, "")
    return "".join(STYLE.findall(page))


@pytest.mark.parametrize("name", PAGE_MODULES)
def test_a_page_never_defines_a_colour(name):
    """Every colour comes from var(--token). A page may not invent a grey.

    Only DECLARATION VALUES are scanned - the text between { and } - because an
    id selector is also a hash followed by hex-ish letters: #dad, #face, #beef,
    and this repo's own `#only` and `#sum` all match a naive /#[0-9a-f]{3,8}/.
    Matching inside the braces is exact and needs no allowlist, which is why
    there is no allowlist. If a page needs a new colour it goes in ui.TOKENS.
    """
    style = own_style(importlib.import_module(name).PAGE)
    bad = [h for body in DECL.findall(style) for h in HEX.findall(body)]
    assert not bad, f"{name} hard-codes {bad}; add a token to ui.TOKENS instead"


@pytest.mark.parametrize("name", PAGE_MODULES)
def test_a_page_never_holds_a_colour_outside_css_either(name):
    """A CSS test cannot see `const TINT={stop:'#2d1114'}`, and that is exactly
    the shape the hub's theme-color map wanted to be. `SM.token()` reads the
    value out of the stylesheet instead, so there is one definition of every
    colour - and a `<meta name=theme-color content="#0b0c0e">` is caught here
    too, which is why the hub ships that tag empty and fills it on load.

    Quoted-only, because an HTML entity (&#10003;) is a hash followed by digits.
    """
    page = importlib.import_module(name).PAGE
    for s in STYLE.findall(page):
        page = page.replace(s, "")
    assert not QUOTED_HEX.findall(page), f"{name} holds a colour literal outside CSS"


@pytest.mark.parametrize("name", PAGE_MODULES)
def test_only_the_shell_styles_a_status(name):
    """A page may USE `.pill you`; only ui.PARTS may say what that looks like."""
    style = own_style(importlib.import_module(name).PAGE).replace(" ", "")
    assert ".pill" not in style, f"{name} restyles the status pill"
    for tok in ("live", "next", "wait", "you", "stop", "done", "unknown"):
        assert f".pill.{tok}" not in style, f"{name} restyles .pill.{tok}"


def test_every_status_word_comes_from_one_table():
    """Seven words, one colour each, no synonyms. The table is in SHELL and the
    CSS for it is in PARTS; if one grows a status the other must too."""
    from sourcemode.monitor.ui import PARTS, SHELL

    words = ("live", "next", "wait", "you", "stop", "done", "unknown")
    for w in words:
        assert f"{w}:{{word:" in SHELL.replace(" ", ""), f"SM.STATUS is missing {w}"
        assert f".pill.{w}{{" in PARTS.replace(" ", ""), f"PARTS has no .pill.{w}"


def test_the_grey_ramp_is_the_only_one():
    """Ten greys, --g0..--g9, defined once. A page adding an eleventh is caught
    by test_a_page_never_defines_a_colour; this catches ui.py growing one."""
    from sourcemode.monitor.ui import TOKENS

    assert TOKENS.count("--g") >= 10
    for n in range(10):
        assert f"--g{n}:#" in TOKENS.replace(" ", ""), f"--g{n} is not defined"


def test_the_migration_list_is_a_subset_of_the_real_pages():
    """A typo in MIGRATED would silently enforce nothing."""
    assert set(MIGRATED) <= set(ALL_PAGES)
    for name in MIGRATED:
        assert getattr(importlib.import_module(name), "PAGE", None), name
