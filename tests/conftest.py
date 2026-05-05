"""Shared test fixtures.

The test suite must never touch a real Telegram account, the network, or
the user's actual data dir. Fixtures here provide hermetic substitutes:

- ``tmp_data_dir``  redirects ``GTG_DATA_DIR`` (and clears the lru_cache
  on ``utils.get_data_dir``) so every test gets a fresh tmpdir.
- ``fake_db``       a dict-backed stand-in for the project's database.
- ``fake_message``  a Telethon-shaped Message with the most-used fields.
- ``fake_client``   the bare minimum a TelegramClient stub needs.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GTG_DATA_DIR", str(tmp_path))
    from friendly_telegram import utils
    utils.get_data_dir.cache_clear()
    yield tmp_path
    utils.get_data_dir.cache_clear()


class FakeDB:
    """In-memory replacement for the JSON-backed CloudBackend.

    The real backend exposes ``get(owner, key, default=None)`` and
    ``set(owner, key, value)``. That's all SecurityManager and
    InlineManager touch in the paths we care about.
    """

    def __init__(self, initial=None):
        self._d = dict(initial or {})

    def get(self, owner, key, default=None):
        return self._d.get((owner, key), default)

    def set(self, owner, key, value):
        self._d[(owner, key)] = value
        return self


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def fake_client():
    """The minimum surface most callers need."""
    c = MagicMock()
    c.is_bot = AsyncMock(return_value=False)
    c.parse_mode = "HTML"
    return c


def make_message(text="", out=True, sender_id=42, chat_id=42, reply_to=None,
                 entities=None, peer_id=None):
    """Construct a Telethon-shaped Message stub.

    Kept as a free function (not a fixture) so tests can produce many
    different message shapes inside a single test without juggling
    parametrized fixtures.
    """
    msg = MagicMock()
    msg.message = text
    msg.raw_text = text
    msg.text = text
    msg.out = out
    msg.sender_id = sender_id
    msg.chat_id = chat_id
    msg.reply_to_msg_id = reply_to
    msg.entities = entities
    msg.peer_id = peer_id
    msg.is_reply = reply_to is not None
    return msg


@pytest.fixture
def fake_message():
    return make_message
