"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# meta pic: https://img.icons8.com/fluency/48/000000/chatbot.png

import inspect
import logging

from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Message

from .. import loader, main, security, utils

logger = logging.getLogger(__name__)


def _modname(mod) -> str:
    """Best-effort display name. ``strings`` may be a dict or callable."""
    try:
        return mod.strings["name"]
    except (KeyError, TypeError):
        return getattr(mod, "name", mod.__class__.__name__)


def _is_inline(mod) -> bool:
    return bool(
        getattr(mod, "inline_handlers", None) or getattr(mod, "callback_handlers", None)
    )


def _is_core(mod) -> bool:
    return getattr(mod, "__origin__", None) == "<file>"


@loader.tds
class HelpMod(loader.Module):
    """Help module, made specifically for GeekTG with <3"""

    strings = {
        "name": "Help",
        "bad_module": "🚫 <b>Module <code>{}</code> not found</b>",
        "single_mod_header": "📼 <b>{}</b>:",
        "single_cmd": "\n▫️ <code>{}{}</code> 👉🏻 ",
        "undoc_cmd": "🦥 No docs",
        "all_header": "👓 <b>{} mods available, {} hidden:</b>",
        "mod_tmpl": "\n{} <code>{}</code>",
        "first_cmd_tmpl": ": ( {}",
        "cmd_tmpl": " | {}",
        "no_mod": "🚫 <b>Specify module to hide</b>",
        "hidden_shown": ("👓 <b>{} modules hidden, {} module shown:</b>\n{}\n{}"),
        "ihandler": "\n🎹 <code>{}</code> 👉🏻 ",
        "perm_warn": "<i>You have permissions to execute only this commands</i>\n",
        "joined": (
            "👩‍💼 <b>Joined the</b> "
            "<a href='https://t.me/GeekTGChat'>support chat</a>"
        ),
        "join": (
            "👩‍💼 <b>Join the</b> " "<a href='https://t.me/GeekTGChat'>support chat</a>"
        ),
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "core_emoji",
            "▪️",
            lambda: "Core module bullet",
            "geek_emoji",
            "🕶",
            lambda: "Geek-only module bullet",
            "plain_emoji",
            "▫️",
            lambda: "Plain module bullet",
        )

    # ---------------------------------------------------------------- helpers

    def _hidden(self) -> list:
        return self.ctx.db.get(self.strings["name"], "hide", [])

    def _set_hidden(self, value) -> None:
        self.ctx.db.set(self.strings["name"], "hide", value)

    def _bullet(self, mod) -> str:
        if _is_core(mod):
            return self.config["core_emoji"]
        if _is_inline(mod):
            return self.config["geek_emoji"]
        return self.config["plain_emoji"]

    def _prefix(self) -> str:
        return (self.ctx.db.get(main.__name__, "command_prefix", False) or ".")[0]

    async def _allowed_cmds(self, message, mod, force):
        return [
            name
            for name, func in mod.commands.items()
            if force or await self.allmodules.check_security(message, func)
        ]

    def _allowed_ihandlers(self, message, mod, force):
        ih = getattr(mod, "inline_handlers", None) or {}
        if force:
            return list(ih)
        return [
            name
            for name, func in ih.items()
            if self.inline.check_inline_security(func, message.sender_id)
        ]

    # --------------------------------------------------------------- commands

    @loader.unrestricted
    async def helpcmd(self, message: Message) -> None:
        """[module|command] [-f] - Show help"""
        args = utils.get_args_raw(message) or ""
        force = "-f" in args.split()
        if force:
            args = args.replace("-f", "").strip()

        prefix = utils.escape_html(self._prefix())

        if args:
            return await self._render_single(message, args, prefix, force)
        return await self._render_all(message, force)

    async def _render_single(self, message, args, prefix, force):
        # 1) module by display name
        target = next(
            (m for m in self.allmodules.modules if _modname(m).lower() == args.lower()),
            None,
        )
        # 2) module owning the command
        if target is None:
            cmd = args.lower().lstrip(prefix)
            handler = self.allmodules.commands.get(cmd)
            if handler is not None:
                target = handler.__self__

        if target is None:
            return await utils.answer(
                message,
                self.strings("bad_module").format(utils.escape_html(args)),
            )

        reply = self.strings("single_mod_header").format(
            utils.escape_html(_modname(target))
        )
        if target.__doc__:
            reply += "<i>\nℹ️ " + utils.escape_html(inspect.getdoc(target)) + "\n</i>"

        for name, fun in (getattr(target, "inline_handlers", None) or {}).items():
            reply += self.strings("ihandler").format(
                f"@{self.inline.bot_username} {name}"
            )
            reply += self._fmt_doc(fun, strip_at=True)

        for name in await self._allowed_cmds(message, target, force):
            fun = target.commands[name]
            reply += self.strings("single_cmd").format(prefix, name)
            reply += self._fmt_doc(fun)

        await utils.answer(message, reply)

    def _fmt_doc(self, fun, *, strip_at: bool = False) -> str:
        doc = inspect.getdoc(fun)
        if not doc:
            return self.strings("undoc_cmd")
        if strip_at:
            doc = "\n".join(
                line.strip()
                for line in doc.splitlines()
                if not line.strip().startswith("@")
            )
        return utils.escape_html(doc)

    async def _render_all(self, message, force):
        # prune stale hide entries
        names = {_modname(m) for m in self.allmodules.modules if hasattr(m, "strings")}
        hidden = [h for h in self._hidden() if h in names]
        self._set_hidden(hidden)

        groups = {"core": [], "plain": [], "inline": []}
        perm_warn = False
        count = 0

        for mod in self.allmodules.modules:
            if not hasattr(mod, "commands"):
                logger.error("Module %s is not initialised yet", mod.__class__.__name__)
                continue

            name = _modname(mod)
            if name in hidden and not force:
                continue

            cmds = await self._allowed_cmds(message, mod, force)
            ihs = self._allowed_ihandlers(message, mod, force)

            has_any = mod.commands or getattr(mod, "inline_handlers", None)
            if not (cmds or ihs):
                if has_any and not perm_warn:
                    perm_warn = True
                continue

            count += 1
            line = self.strings("mod_tmpl").format(self._bullet(mod), name)
            tokens = cmds + [f"🎹 {n}" for n in ihs]
            for i, tok in enumerate(tokens):
                tmpl = "first_cmd_tmpl" if i == 0 else "cmd_tmpl"
                line += self.strings(tmpl).format(tok)
            line += " )"

            if _is_core(mod):
                groups["core"].append(line)
            elif _is_inline(mod):
                groups["inline"].append(line)
            else:
                groups["plain"].append(line)

        for key in groups:
            groups[key].sort(key=str.lower)

        header = self.strings("all_header").format(count, 0 if force else len(hidden))
        warn = self.strings("perm_warn") if perm_warn else ""
        body = "".join(groups["core"] + groups["plain"] + groups["inline"])
        await utils.answer(message, f"{warn}{header}\n{body}")

    async def helphidecmd(self, message: Message) -> None:
        """<module or modules> - Hide module(-s) from help
        *Split modules by spaces"""
        targets = utils.get_args(message)
        if not targets:
            return await utils.answer(message, self.strings("no_mod"))

        names = {_modname(m) for m in self.allmodules.modules if hasattr(m, "strings")}
        targets = [t for t in targets if t in names]

        hidden = self._hidden()
        added, removed = [], []
        for t in targets:
            if t in hidden:
                hidden.remove(t)
                removed.append(t)
            else:
                hidden.append(t)
                added.append(t)
        self._set_hidden(hidden)

        await utils.answer(
            message,
            self.strings("hidden_shown").format(
                len(added),
                len(removed),
                "\n".join(f"👁‍🗨 <i>{m}</i>" for m in added),
                "\n".join(f"👁 <i>{m}</i>" for m in removed),
            ),
        )

    async def supportcmd(self, message):
        """Joins the support GeekTG chat"""
        is_owner = await self.allmodules.check_security(
            message, security.OWNER | security.SUDO
        )
        if is_owner:
            await self.ctx.client(JoinChannelRequest("https://t.me/GeekTGChat"))

        key = "joined" if is_owner else "join"
        try:
            await self.inline.form(
                self.strings(key, message),
                reply_markup=[
                    [{"text": "👩‍💼 Chat", "url": "https://t.me/GeekTGChat"}]
                ],
                ttl=10,
                message=message,
            )
        except Exception:
            await utils.answer(message, self.strings(key, message))
