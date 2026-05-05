"""Pure-function utilities — no mocks, no async, no I/O."""

from unittest.mock import MagicMock

import pytest

from friendly_telegram import utils
from tests.conftest import make_message


# ---------- arg parsing ----------

class TestGetArgs:
    def test_no_args(self):
        assert utils.get_args(make_message(".cmd")) == []

    def test_simple(self):
        assert utils.get_args(make_message(".cmd foo bar baz")) == ["foo", "bar", "baz"]

    def test_quoted(self):
        assert utils.get_args(make_message('.cmd "hello world" three')) == [
            "hello world", "three",
        ]

    def test_unbalanced_quote_returns_raw(self):
        # shlex raises ValueError → falls back to the whole arg-string
        assert utils.get_args(make_message('.cmd "broken')) == '"broken'

    def test_string_input_works(self):
        assert utils.get_args(".cmd foo bar") == ["foo", "bar"]

    def test_empty_message_returns_false(self):
        assert utils.get_args(make_message("")) is False


class TestGetArgsRaw:
    def test_returns_after_first_split(self):
        assert utils.get_args_raw(make_message(".cmd  hello   world")) == "hello   world"

    def test_no_args_empty_string(self):
        assert utils.get_args_raw(make_message(".cmd")) == ""


def test_get_args_split_by_strips_blanks():
    msg = make_message(".cmd one | | two |   ")
    assert utils.get_args_split_by(msg, "|") == ["one", "two"]


# ---------- escaping ----------

@pytest.mark.parametrize("inp,exp", [
    ("plain", "plain"),
    ("<b>bold</b>", "&lt;b&gt;bold&lt;/b&gt;"),
    ("a & b", "a &amp; b"),
    # & must be escaped first or "<" → "&amp;lt;" double-escape
    ("<&>", "&lt;&amp;&gt;"),
    (42, "42"),
    (None, "None"),
])
def test_escape_html(inp, exp):
    assert utils.escape_html(inp) == exp


def test_escape_quotes_handles_both():
    assert utils.escape_quotes('She said "hi" & <left>') == \
        'She said &quot;hi&quot; &amp; &lt;left&gt;'


# ---------- relocate_entities ----------

class TestRelocateEntities:
    def _ent(self, offset, length):
        e = MagicMock()
        e.offset = offset
        e.length = length
        return e

    def test_simple_shift(self):
        ents = [self._ent(0, 5), self._ent(10, 3)]
        out = utils.relocate_entities(ents, 4)
        assert (out[0].offset, out[0].length) == (4, 5)
        assert (out[1].offset, out[1].length) == (14, 3)

    def test_negative_offset_clamps_at_zero(self):
        ents = [self._ent(2, 5)]
        out = utils.relocate_entities(ents, -3)
        # original starts at 2, shift -3 → offset -1 → clamps to 0, length 5-1=4
        assert (out[0].offset, out[0].length) == (0, 4)

    def test_zero_length_drops(self):
        ents = [self._ent(0, 2)]
        out = utils.relocate_entities(ents, -5)
        assert out == []

    def test_truncates_past_text_end(self):
        ents = [self._ent(0, 100)]
        out = utils.relocate_entities(ents, 0, text="hello")
        assert out[0].length == 5

    def test_none_entities(self):
        # Some Telethon paths pass None; relocate_entities must tolerate it
        assert utils.relocate_entities(None, 0) is None


# ---------- merge ----------

class TestMerge:
    def test_simple_merge(self):
        out = utils.merge({"a": 1}, {"b": 2})
        assert out == {"a": 1, "b": 2}

    def test_nested_dict_recursive(self):
        out = utils.merge({"x": {"a": 1}}, {"x": {"b": 2}})
        assert out["x"] == {"a": 1, "b": 2}

    def test_list_dedup_and_merge(self):
        out = utils.merge({"l": [1, 2]}, {"l": [2, 3]})
        assert sorted(out["l"]) == [1, 2, 3]


# ---------- platform name ----------

class TestPlatformName:
    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("GTG_PLATFORM", "🐧 Custom")
        monkeypatch.delenv("FTG_PLATFORM", raising=False)
        monkeypatch.delenv("LAVHOST", raising=False)
        assert utils.get_platform_name() == "🐧 Custom"

    def test_lavhost(self, monkeypatch):
        monkeypatch.delenv("GTG_PLATFORM", raising=False)
        monkeypatch.delenv("FTG_PLATFORM", raising=False)
        monkeypatch.setenv("LAVHOST", "free")
        assert "lavHost" in utils.get_platform_name()

    def test_termux(self, monkeypatch):
        monkeypatch.delenv("GTG_PLATFORM", raising=False)
        monkeypatch.delenv("FTG_PLATFORM", raising=False)
        monkeypatch.delenv("LAVHOST", raising=False)
        monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
        assert "Termux" in utils.get_platform_name()

    def test_fallback_vds(self, monkeypatch):
        for v in ("GTG_PLATFORM", "FTG_PLATFORM", "LAVHOST", "PREFIX"):
            monkeypatch.delenv(v, raising=False)
        assert utils.get_platform_name() == "📻 VDS"


# ---------- data dir override ----------

def test_data_dir_respects_env_override(tmp_data_dir):
    assert utils.get_data_dir() == str(tmp_data_dir)


def test_data_dir_creates_path(tmp_data_dir):
    import os
    assert os.path.isdir(utils.get_data_dir())


# ---------- normalize_requirement (used by manifest persistence) ----------

@pytest.mark.parametrize("inp,exp", [
    ("Pillow", "pillow"),
    ("Pillow[heif]>=10", "pillow"),
    ("googletrans==4.0.0rc1", "googletrans"),
    ('Wand[Cairo]>=0.7 ; python_version<"3.14"', "wand"),
    ("  numpy  ", "numpy"),
])
def test_normalize_requirement(inp, exp):
    assert utils._normalize_requirement(inp) == exp


def test_auto_requirements_round_trip(tmp_path):
    p = tmp_path / "auto_requirements.txt"
    utils._save_auto_requirements(str(p), {"pillow": "==11.3.0", "wand": "", "foo": ">=1"})
    got = utils._load_auto_requirements(str(p))
    assert got == {"pillow": "==11.3.0", "wand": "", "foo": ">=1"}


def test_auto_requirements_skips_comments(tmp_path):
    p = tmp_path / "auto_requirements.txt"
    p.write_text("# comment\n\npillow==1.0\n   # indented\nwand\n")
    assert utils._load_auto_requirements(str(p)) == {"pillow": "==1.0", "wand": ""}
