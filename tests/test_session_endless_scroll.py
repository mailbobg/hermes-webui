"""Earlier-message reveal is now always-on scroll-up, with no opt-in setting.

The old opt-in ``session_endless_scroll`` setting and the manual "Load earlier
messages" button were removed: scrolling upward reveals earlier transcript
content naturally (expand the in-memory render window first, then page older
messages from the server). These tests pin that the setting and button are gone
and that the scroll handler drives the reveal unconditionally.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PY = (ROOT / "api" / "config.py").read_text(encoding="utf-8")
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
UI_JS = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


def test_endless_scroll_setting_is_gone():
    assert "session_endless_scroll" not in CONFIG_PY
    assert "session_endless_scroll" not in PANELS_JS
    assert "_sessionEndlessScrollEnabled" not in PANELS_JS
    assert "_sessionEndlessScrollEnabled" not in BOOT_JS
    assert "session_endless_scroll" not in BOOT_JS
    assert "settingsSessionEndlessScroll" not in INDEX_HTML
    assert "settings_label_session_endless_scroll" not in INDEX_HTML


def test_endless_scroll_i18n_keys_are_gone():
    assert "settings_label_session_endless_scroll" not in I18N_JS
    assert "settings_desc_session_endless_scroll" not in I18N_JS
    assert "load_older_messages" not in I18N_JS


def test_load_earlier_button_is_gone():
    assert "loadOlderIndicator" not in UI_JS
    assert "_wireMessageWindowLoadEarlierButton" not in UI_JS
    assert "_isSessionEndlessScrollEnabled" not in UI_JS


def test_scroll_listener_reveals_earlier_content_unconditionally():
    assert "const olderPrefetchPx=Math.max(600,el.clientHeight*1.5)" in UI_JS
    assert "if(el.scrollTop<olderPrefetchPx){" in UI_JS
    # Local DOM-window expansion is attempted before paging from the server.
    assert "if(_messageHiddenBeforeCount()>0) _showEarlierRenderedMessages();" in UI_JS
    assert "el.scrollTop<80 && typeof _messagesTruncated" not in UI_JS
