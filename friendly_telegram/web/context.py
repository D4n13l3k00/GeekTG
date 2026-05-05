"""Shared state container threaded through every web sub-router.

Replaces the old multi-inheritance ``core.Web(initial_setup.Web,
root.Web, status.Web)`` chain — instead of every router subclass
popping its own kwargs out of a shared dict, all of them receive a
``WebContext`` and read whatever they need from it.

Anything mutated at runtime (``client_data``, the various
asyncio.Events, on-demand caches like ``_me_cache`` / gate slots)
lives here so it stays addressable from every router.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WebContext:
    # ---- bootstrapping kwargs (set once by main.py) ----------------------
    api_token: Any = None              # namedtuple("api_token", ("ID","HASH"))
    data_root: Optional[str] = None
    connection: Any = None
    proxy: Any = None
    hosting: bool = False
    default_app: bool = False

    # ---- runtime state ---------------------------------------------------
    started_at: float = field(default_factory=time.time)
    client_data: dict = field(default_factory=dict)

    # initial-setup events
    api_set: asyncio.Event = field(default_factory=asyncio.Event)
    sign_in_clients: dict = field(default_factory=dict)
    clients: list = field(default_factory=list)
    clients_set: asyncio.Event = field(default_factory=asyncio.Event)
    root_redirected: asyncio.Event = field(default_factory=asyncio.Event)
    redirect_url: Optional[str] = None

    # post-auth caches (lazily populated)
    me_cache: Optional[dict] = None
    avatar_cache: Optional[tuple] = None  # (bytes, content-type)

    # status & gates (initialised by StatusRouter)
    backup_gate: Any = None
    restore_gate: Any = None
    logout_gate: Any = None

    # web app lifecycle (set by Web)
    ready: asyncio.Event = field(default_factory=asyncio.Event)

    def first_authed_client(self):
        """Return the first signed-in Telethon client, or ``None``."""
        if not self.client_data:
            return None
        return next(iter(self.client_data.values()))[1]

    def first_loader(self):
        """Return the first signed-in account's ``Modules`` instance, or ``None``."""
        if not self.client_data:
            return None
        return next(iter(self.client_data.values()))[0]

    def effective_data_dir(self) -> str:
        """``data_root`` if set, otherwise the XDG default."""
        from .. import utils
        return self.data_root or utils.get_data_dir()
