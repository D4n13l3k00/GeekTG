"""Unit tests for inline/types.py — the freestanding helpers."""

from unittest.mock import MagicMock

from friendly_telegram.inline import (
    InlineCall,
    array_sum,
    rand,
)
from friendly_telegram.inline.types import GeekInlineQuery


class TestRand:
    def test_length(self):
        assert len(rand(10)) == 10

    def test_charset(self):
        s = rand(50)
        assert all(c in "abcdefghijklmnopqrstuvwxyz1234567890" for c in s)

    def test_zero(self):
        assert rand(0) == ""


class TestArraySum:
    def test_flatten_one_level(self):
        assert array_sum([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]

    def test_empty(self):
        assert array_sum([]) == []

    def test_strings(self):
        # Treat them as iterables of chars — array_sum is generic +=
        assert array_sum(["ab", "cd"]) == ["a", "b", "c", "d"]


class TestInlineCall:
    def test_attributes_default_none(self):
        call = InlineCall()
        assert call.delete is None
        assert call.unload is None
        assert call.edit is None
        assert call.form is None

    def test_delegates_to_event(self):
        event = MagicMock()
        event.data = "click"
        event.from_user.id = 42
        call = InlineCall(event=event)
        assert call.data == "click"
        assert call.from_user.id == 42

    def test_helpers_shadow_event(self):
        # When ``edit`` is set on the wrapper it must take precedence over
        # any same-named attribute on the underlying event.
        event = MagicMock()
        event.edit = "from-event"
        call = InlineCall(event=event, edit="from-wrapper")
        assert call.edit == "from-wrapper"


class TestGeekInlineQuery:
    def test_args_extracted(self):
        # Simulate aiogram's InlineQuery shape with .query
        iq = MagicMock()
        iq.query = "search foo bar baz"
        # Make dir() return a known shape so the attribute-copy loop is bounded
        type(iq).__dir__ = lambda self: ["query", "from_user", "id"]
        iq.from_user = "u"
        iq.id = "x"
        wrapped = GeekInlineQuery(iq)
        assert wrapped.args == "foo bar baz"
        assert wrapped.query == "search foo bar baz"

    def test_no_args(self):
        iq = MagicMock()
        iq.query = "ping"
        type(iq).__dir__ = lambda self: ["query"]
        wrapped = GeekInlineQuery(iq)
        assert wrapped.args == ""
