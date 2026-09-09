"""The dev server proxies to the API by a hand-kept list of paths.

A route missing from it fails in development only, and it fails confusingly: index.html
comes back where JSON was expected, so the panel that called it shows a JSON parse error
rather than anything about a missing route. It has caught people out twice. This keeps the
list honest.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "backend" / "main.py"
CONFIG = ROOT / "frontend" / "vite.config.ts"

ROUTE = re.compile(r'@app\.(?:get|post|put|delete|patch)\(\s*"(/[a-zA-Z0-9_-]*)')
MOUNT = re.compile(r'app\.mount\(\s*"(/[a-zA-Z0-9_-]+)"')


def answered_by_the_api() -> set[str]:
    """Every top-level path the API answers on, mounts included, minus the catch-all."""
    text = MAIN.read_text(encoding="utf-8")
    found = {m for m in ROUTE.findall(text)} | {m for m in MOUNT.findall(text)}
    return {path for path in found if path != "/"}


def proxied_in_development() -> set[str]:
    """The paths the dev server hands to the API."""
    text = CONFIG.read_text(encoding="utf-8")
    listed = re.search(r"\[([^\]]*)\]\.map\(", text, re.S)
    assert listed, "vite.config.ts no longer lists the proxied paths as an array"
    return set(re.findall(r"'(/[a-zA-Z0-9_-]+)'", listed.group(1)))


def test_every_api_route_is_reachable_from_the_dev_server():
    missing = sorted(answered_by_the_api() - proxied_in_development())
    assert not missing, (
        f"vite.config.ts does not proxy {missing}. In development those calls return "
        "index.html, and the caller reports it as broken JSON.")


def test_the_list_holds_nothing_the_api_does_not_answer():
    """A path that no longer exists sends dev traffic somewhere it will only 404."""
    stale = sorted(proxied_in_development() - answered_by_the_api())
    assert not stale, f"vite.config.ts proxies {stale}, which the API no longer answers on"


def test_the_check_can_see_something():
    """A regex that matched nothing would let anything through."""
    assert len(answered_by_the_api()) >= 8
    assert "/services" in answered_by_the_api()
    assert "/kerkdienstgemist" in answered_by_the_api()
