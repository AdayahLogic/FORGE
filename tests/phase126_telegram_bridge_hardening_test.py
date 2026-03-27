"""
Phase 126: Telegram bridge hardening tests.

Run:
  python tests/phase126_telegram_bridge_hardening_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(name: str, fn):
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as exc:
        print(f"FAIL: {name} - {exc}")
        return False


def test_parse_allowed_chat_ids_valid_and_invalid():
    from NEXUS.telegram_bridge import _parse_allowed_chat_ids

    ids, err = _parse_allowed_chat_ids("123, 456, 789")
    assert ids == {123, 456, 789}
    assert err is None

    ids2, err2 = _parse_allowed_chat_ids("123, nope")
    assert ids2 == set()
    assert err2 and "invalid entries" in err2.lower()


def test_missing_allowlist_defaults_to_deny_all():
    from NEXUS.telegram_bridge import handle_telegram_message

    prev = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS")
    try:
        if "TELEGRAM_ALLOWED_CHAT_IDS" in os.environ:
            del os.environ["TELEGRAM_ALLOWED_CHAT_IDS"]
        out = handle_telegram_message({"chat": {"id": 999}, "text": "status"})
        assert "deny-all mode" in out.lower()
    finally:
        if prev is not None:
            os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = prev


def test_unauthorized_chat_is_not_processed():
    from NEXUS.telegram_bridge import handle_telegram_message

    prev = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS")
    try:
        os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = "123"
        out = handle_telegram_message({"chat": {"id": 999}, "text": "status"})
        assert out.strip().lower() == "unauthorized."
    finally:
        if prev is not None:
            os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = prev
        else:
            del os.environ["TELEGRAM_ALLOWED_CHAT_IDS"]


def test_unknown_command_has_no_passthrough():
    from NEXUS.telegram_bridge import _route_command

    out = _route_command("runtime_route --dangerous")
    assert "unsupported command" in out.lower()


def main():
    tests = [
        test_parse_allowed_chat_ids_valid_and_invalid,
        test_missing_allowlist_defaults_to_deny_all,
        test_unauthorized_chat_is_not_processed,
        test_unknown_command_has_no_passthrough,
    ]
    passed = sum(1 for test in tests if _run(test.__name__, test))
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
