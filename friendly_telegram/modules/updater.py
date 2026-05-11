#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2022 The Authors
#    Modded by GeekTG Team
#
#    Licensed under GNU AGPL v3 (see LICENSE).

"""Restart command + ``.source`` link.

The historic git-based self-update (``.update`` / ``.download``) has been
removed: pulling code into a wheel-installed package is fragile and the
recommended path is now ``uv tool upgrade gtg`` (or ``pipx upgrade``)
followed by ``.restart``. ``.update`` is kept as a stub so muscle memory
shows a clear "not implemented yet" message instead of erroring out.
"""

import asyncio
import atexit
import functools
import logging
import os
import sys
import uuid
from typing import Awaitable, cast

from telethon.tl.custom import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class UpdaterMod(loader.Module):
    """Restart and link to the source code."""

    strings = {
        "name": "Updater",
        "source": "ℹ️ <b>Read the source code</b> <a href='{}'>here</a>",
        "restarting_caption": "🔄 <b>Restarting...</b>",
        "success": "✅ <b>Restart successful!</b>",
        "not_implemented": (
            "🛠 <b>Self-update is not implemented yet.</b>\n\n"
            "<b>Until it lands</b>, update the package from your shell:\n"
            "<code>uv tool upgrade gtg</code> "
            "(or <code>pipx upgrade gtg</code>),\n"
            "then run <code>.restart</code>."
        ),
        "origin_cfg_doc": "Source repository URL shown by .source",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "GIT_ORIGIN_URL",
            "https://github.com/D4n13l3k00/GeekTG",
            lambda m: self.tr("origin_cfg_doc", m),
        )

    @loader.owner
    async def restartcmd(self, message: Message) -> None:
        """Restarts the userbot."""
        msg = (await utils.answer(message, self.tr("restarting_caption", message)))[0]
        await self.restart_common(msg)

    async def prerestart_common(self, message: Message) -> None:
        logger.debug(
            "Restart requested. exec=%s base=%s", sys.executable, utils.get_base_dir()
        )
        check = str(uuid.uuid4())
        self.ctx.db.set(__name__, "selfupdatecheck", check)
        await asyncio.sleep(3)
        if self.ctx.db.get(__name__, "selfupdatecheck", "") != check:
            raise ValueError("A restart is already in progress!")
        self.ctx.db.set(__name__, "selfupdatechat", utils.get_chat_id(message))
        self.ctx.db.set(__name__, "selfupdatemsg", message.id)

    async def restart_common(self, message: Message) -> None:
        await self.prerestart_common(message)
        atexit.register(functools.partial(_restart_via_execl, *sys.argv[1:]))
        # Squash log noise so the disconnect race below doesn't spam stderr.
        # We tolerate a missing handler — some test harnesses don't install one.
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.CRITICAL)
        # ``disconnect()`` returns a coroutine when called inside a running
        # loop (always true for us); the type stub widens it to
        # ``Awaitable | None`` to also cover the sync entry point. Cast it.
        for client in self.allclients:
            if client is not message.client:
                await cast(Awaitable[None], client.disconnect())
        client = message.client
        if client is not None:
            await cast(Awaitable[None], client.disconnect())

    @loader.owner
    async def updatecmd(self, message: Message) -> None:
        """Self-update — not implemented yet."""
        await utils.answer(message, self.tr("not_implemented", message))

    # Same body — preserved as separate command for muscle memory (.update / .download).
    downloadcmd = updatecmd

    @loader.unrestricted
    async def sourcecmd(self, message: Message) -> None:
        """Links the source code of this project."""
        await utils.answer(
            message,
            self.tr("source", message).format(self.config["GIT_ORIGIN_URL"]),
        )

    async def client_ready(self, client, db):
        chat = db.get(__name__, "selfupdatechat")
        msg = db.get(__name__, "selfupdatemsg")
        if chat is None or msg is None:
            return

        try:
            await self.update_complete(client)
        except Exception:
            logger.exception("Failed to deliver post-restart confirmation")
            # Keep state so the *next* startup can retry — clearing on failure
            # would silently lose the receipt.
            return

        self.ctx.db.set(__name__, "selfupdatechat", None)
        self.ctx.db.set(__name__, "selfupdatemsg", None)

    async def update_complete(self, client):
        logger.debug("Restart successful, editing the original message")
        await client.edit_message(
            self.ctx.db.get(__name__, "selfupdatechat"),
            self.ctx.db.get(__name__, "selfupdatemsg"),
            self.tr("success"),
        )


def _restart_via_execl(*argv):
    # ``python -m`` wants a module *name*, not a path. The previous
    # ``os.path.relpath(get_base_dir())`` worked when cwd was the project
    # root but produces dot-prefixed garbage for ``uv tool``/``pipx``-
    # installed copies (e.g. ``.local/share/uv/tools/.../friendly_telegram``);
    # CPython then rejects the invocation with
    # ``Relative module names not supported`` and the process dies on exec.
    os.execl(
        sys.executable,
        sys.executable,
        "-m",
        "friendly_telegram",
        *argv,
    )
