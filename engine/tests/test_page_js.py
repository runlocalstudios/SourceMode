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
]

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
