"""Tests for the click-to-navigate directory browser (workspace add/edit form).

Covers api.workspace.list_directory and the GET /api/workspaces/browse route.

Security is the priority: directory browsing must stay strictly within the
trusted workspace roots (reusing _trusted_workspace_roots /
_is_blocked_workspace_path).  Any path outside that boundary -- /etc, /, a
sibling of a trusted root, or a ``..`` escape -- must be rejected with
{"error": "not allowed"} and must never leak a listing.
"""
import os

import pytest


def _trusted_to(root):
    """Return a fake _trusted_workspace_roots() yielding a single root."""
    resolved = root.resolve()
    return lambda: [resolved]


def test_empty_path_returns_trusted_roots(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory("")
    assert res["current"] == ""
    assert res["parent"] is None
    assert res["entries"] == []
    roots = res["roots"]
    assert len(roots) == 1
    assert roots[0]["path"] == str(root.resolve())
    assert roots[0]["is_root"] is True


def test_lists_subdirectories_sorted(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    (root / "Zeta").mkdir(parents=True)
    (root / "alpha").mkdir()
    (root / "Mango").mkdir()
    # a file should NOT show up (only directories)
    (root / "notes.txt").write_text("hi")
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory(str(root))
    assert res["current"] == str(root.resolve())
    names = [e["name"] for e in res["entries"]]
    # case-insensitive alphabetical: alpha, Mango, Zeta
    assert names == ["alpha", "Mango", "Zeta"]
    assert "notes.txt" not in names
    # at the trusted-root top, parent is None
    assert res["parent"] is None
    for e in res["entries"]:
        assert e["path"].startswith(str(root.resolve()))


def test_hidden_dot_directories_filtered(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    (root / ".git").mkdir(parents=True)
    (root / ".cache").mkdir()
    (root / "visible").mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory(str(root))
    names = [e["name"] for e in res["entries"]]
    assert names == ["visible"]


def test_parent_points_up_within_root(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    child = root / "proj"
    child.mkdir(parents=True)
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory(str(child))
    assert res["current"] == str(child.resolve())
    assert res["parent"] == str(root.resolve())


def test_outside_trusted_root_rejected(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    root.mkdir()
    sibling = tmp_path / "elsewhere"
    sibling.mkdir()
    (sibling / "secret").mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory(str(sibling))
    assert res.get("error") == "not allowed"
    assert res["entries"] == []


def test_etc_rejected(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory("/etc")
    assert res.get("error") == "not allowed"
    assert res["entries"] == []


def test_filesystem_root_rejected(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    res = workspace.list_directory("/")
    assert res.get("error") == "not allowed"
    assert res["entries"] == []


def test_dotdot_escape_rejected(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    child = root / "proj"
    child.mkdir(parents=True)
    # Sibling of the root that the escape would reach.
    sibling = tmp_path / "elsewhere"
    sibling.mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    # ../../elsewhere resolves outside the trusted root -> rejected.
    escape = str(child) + "/../../elsewhere"
    res = workspace.list_directory(escape)
    assert res.get("error") == "not allowed"
    assert res["entries"] == []


def test_dotdot_within_root_allowed(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    child = root / "proj"
    child.mkdir(parents=True)
    (root / "ok").mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    # proj/.. resolves back to root, which is still trusted -> allowed.
    res = workspace.list_directory(str(child) + "/..")
    assert "error" not in res
    assert res["current"] == str(root.resolve())
    assert "ok" in [e["name"] for e in res["entries"]]


def test_nonexistent_path_does_not_crash(monkeypatch, tmp_path):
    from api import workspace

    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(workspace, "_trusted_workspace_roots", _trusted_to(root))

    missing = root / "nope"
    res = workspace.list_directory(str(missing))
    # Inside the trusted root but does not exist -> graceful, not a crash.
    assert res["entries"] == []
    assert res.get("error") == "not found"


# ── Route-level tests ───────────────────────────────────────────────────────

def test_browse_route_is_registered():
    """The GET handler must wire /api/workspaces/browse to list_directory."""
    import inspect

    from api import routes

    src = inspect.getsource(routes)
    assert '"/api/workspaces/browse"' in src
    assert "list_directory(" in src


def test_browse_route_imports_list_directory():
    """list_directory must be importable into routes (registration prereq)."""
    from api import routes

    assert hasattr(routes, "list_directory")

