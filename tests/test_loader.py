"""Loader: command/alias dispatch + introspection of module classes.

These exercises go through ``Modules`` without touching importlib or the
filesystem — we hand the loader pre-built fake module instances.
"""

import pytest

from friendly_telegram import loader


# ---------- introspection helpers (pure functions) ----------

class FakeMod:
    """A bare-bones module instance the loader can introspect."""

    async def echocmd(self, message): pass

    async def picgallery_inline_handler(self, query): pass

    async def picgallery_callback_handler(self, call): pass

    # Decoys: these must NOT be picked up
    def helper(self): pass

    async def cmd(self): pass  # too short, len <= 3


class TestIntrospection:
    def test_get_commands_picks_only_cmd_suffix(self):
        cmds = loader.get_commands(FakeMod())
        assert list(cmds) == ["echo"]

    def test_get_commands_strips_three_chars(self):
        # The slicing is ``method_name[:-3]``; "echocmd" → "echo"
        m = FakeMod()
        cmds = loader.get_commands(m)
        assert cmds["echo"].__name__ == "echocmd"

    def test_get_inline_handlers_picks_inline_handler_suffix(self):
        ih = loader.get_inline_handlers(FakeMod())
        assert list(ih) == ["picgallery"]

    def test_get_callback_handlers_picks_callback_handler_suffix(self):
        ch = loader.get_callback_handlers(FakeMod())
        assert list(ch) == ["picgallery"]


# ---------- dispatch: cmd lookup with keyboard-layout fallbacks ----------

@pytest.fixture
def modules():
    """A ``Modules`` instance with two registered commands and one alias."""
    m = loader.Modules()
    m.commands = {"echo": object(), "ping": object()}
    m.aliases = {"e": "echo"}
    return m


class TestDispatch:
    def test_direct_match(self, modules):
        cmd, handler = modules.dispatch("echo")
        assert cmd == "echo"
        assert handler is modules.commands["echo"]

    def test_case_insensitive(self, modules):
        cmd, handler = modules.dispatch("ECHO")
        assert handler is modules.commands["echo"]

    def test_alias_resolves(self, modules):
        cmd, handler = modules.dispatch("e")
        # Alias resolution returns the canonical name plus its handler
        assert cmd == "echo"
        assert handler is modules.commands["echo"]

    def test_unknown_returns_none(self, modules):
        cmd, handler = modules.dispatch("nope")
        assert cmd == "nope"
        assert handler is None

    def test_keyboard_layout_typo(self, modules):
        # "усрщ" is what comes out of typing E-C-H-O with the
        # Cyrillic ЙЦУКЕН layout still active. The dispatcher's
        # keyboard-flip fallback should resolve it back to ``echo``.
        cmd, handler = modules.dispatch("усрщ")
        assert cmd == "echo"
        assert handler is modules.commands["echo"]


# ---------- alias mutation ----------

class TestAliasMutation:
    def test_add_alias_for_known_command(self, modules):
        assert modules.add_alias("p", "ping") is True
        assert modules.aliases["p"] == "ping"

    def test_add_alias_for_unknown_rejected(self, modules):
        assert modules.add_alias("x", "doesnotexist") is False
        assert "x" not in modules.aliases

    def test_alias_lowercased_and_stripped(self, modules):
        modules.add_alias("  P  ", "ping")
        assert modules.aliases["p"] == "ping"

    def test_remove_existing(self, modules):
        modules.add_alias("p", "ping")
        assert modules.remove_alias("p") is True
        assert "p" not in modules.aliases

    def test_remove_missing_returns_false(self, modules):
        assert modules.remove_alias("nope") is False
