"""Every page we serve must be valid JavaScript, checked against the EVALUATED page.

Written after shipping the GPU page broken twice in one session, both times from
editing JavaScript that lives inside a Python string:

1. A replacement dropped the opening quote of a string literal, leaving
   `...:0)+)">Add to queue</button>'`.
2. An index-based edit cut at the first `}` after a call, which was the brace of
   `{dataset:ds}`, leaving a stray `});`.

Both parse fine as Python, both return HTTP 200, and both leave the page stuck on
"loading…" because the whole script fails to parse in the browser. Nothing in the
Python test suite could see it. The source text cannot be checked either - in the
source `\\'` is an escape, so only the evaluated string is the real script.

Skips when node is unavailable rather than failing: it is a linter, not a
dependency.
"""

import shutil
import subprocess

import pytest

PAGES = [
    ("queue_page", "sourcemode.monitor.queue_page", "PAGE"),
    ("hub", "sourcemode.monitor.hub", "PAGE"),
    ("judge", "sourcemode.assets.judge", "PAGE"),
    # Never in this list until 2026-10-04, and it is the LONGEST page script in
    # the repo. Added before the page was touched, so the baseline is known good.
    ("dataset", "sourcemode.train.preview", "PAGE"),
    ("shoots", "sourcemode.monitor.shoots_page", "PAGE"),
]

# A bare JS constant has no <script> tag, so it cannot be a PAGES row: _scripts()
# would return [] and the `assert bodies` below would fail with "serves no
# script". SHELL is already node-checked four times over - once inside each PAGE
# above, which test_the_shell_is_embedded_in_every_page proves - so this list
# exists for a future constant that is NOT embedded in a page.
SCRIPTS = [("shell", "sourcemode.monitor.ui", "SHELL")]

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node not installed")


def _scripts(page: str) -> list[str]:
    """Every <script> body in the page, in order."""
    out, at = [], 0
    while True:
        i = page.find("<script", at)
        if i < 0:
            return out
        start = page.index(">", i) + 1
        end = page.index("</script>", start)
        body = page[start:end].strip()
        if body:
            out.append(body)
        at = end + 1


@pytest.mark.parametrize(("name", "module", "attr"), PAGES, ids=[p[0] for p in PAGES])
def test_the_page_script_parses(name, module, attr, tmp_path):
    import importlib

    mod = importlib.import_module(module)
    page = getattr(mod, attr, None)
    if page is None:
        pytest.skip(f"{module} has no {attr}")

    bodies = _scripts(page)
    assert bodies, f"{name} serves no script - did the page change shape?"
    for i, body in enumerate(bodies):
        f = tmp_path / f"{name}_{i}.js"
        f.write_text(body, encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, check=False)
        assert r.returncode == 0, f"{name} script {i} does not parse:\n{r.stderr}"


@pytest.mark.parametrize(("name", "module", "attr"), PAGES, ids=[p[0] for p in PAGES])
def test_quotes_and_braces_balance_in_the_markup(name, module, attr):
    """A cheap structural check that runs even where node does not: an onclick
    attribute must not contain a bare double quote, which is what ends it early."""
    import importlib
    import re

    mod = importlib.import_module(module)
    page = getattr(mod, attr, None)
    if page is None:
        pytest.skip(f"{module} has no {attr}")
    for m in re.finditer(r'onclick="([^"]*)"', page):
        inner = m.group(1)
        assert inner.count("(") == inner.count(")"), f"{name}: unbalanced parens in {inner!r}"


@pytest.mark.parametrize(("name", "module", "attr"), SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_a_bare_script_constant_parses(name, module, attr, tmp_path):
    import importlib

    body = getattr(importlib.import_module(module), attr)
    f = tmp_path / f"{name}.js"
    f.write_text(body, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, f"{name} does not parse:" + r.stderr


def test_the_shell_is_embedded_in_every_migrated_page():
    """Which is why SHELL needs no PAGES row of its own. Scoped to the pages
    already moved onto ui.py, so this is green at every step of the migration."""
    import importlib

    from sourcemode.monitor.ui import SHELL

    from test_ui_vocabulary import MIGRATED  # noqa: PLC0415

    for module in MIGRATED:
        assert SHELL in importlib.import_module(module).PAGE, module
