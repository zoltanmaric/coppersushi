from dash import no_update

import app


def test_failed_load_becomes_banner(monkeypatch):
    def broken():
        raise RuntimeError("networks/x.nc is a Git LFS pointer; run `git lfs pull`")

    monkeypatch.setitem(app.NETWORK_LOADERS, "broken", broken)
    fig, *_, message, is_open = app.render("/broken", 0, slider_moved=False)
    assert fig is no_update
    assert is_open and "git lfs pull" in message


def linked_hrefs(component) -> set[str]:
    """Every `href` the layout links to."""
    found = {component.href} if hasattr(component, "href") else set()
    children = getattr(component, "children", None)
    for child in children if isinstance(children, list) else [children] if children else []:
        found |= linked_hrefs(child)
    return found


def test_every_sanctioned_network_is_linked():
    """A promoted network the nav does not link is reachable only by typing its URL."""
    sanctioned = {key for key in app.NETWORK_LOADERS if not key.startswith("candidates/")}
    hrefs = linked_hrefs(app.app.layout)
    missing = {key for key in sanctioned if f"/{key}" not in hrefs and not (key == "v1" and "/" in hrefs)}
    assert not missing, f"sanctioned networks with no link: {sorted(missing)}"
