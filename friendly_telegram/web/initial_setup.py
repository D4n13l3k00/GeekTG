"""First-run wizard: API token + Telegram login flow."""

import collections
import logging
import os
import string

import aiohttp_jinja2
import telethon
from aiohttp import web

from .. import utils
from .._device import telethon_kwargs as _device_kwargs
from .context import WebContext

logger = logging.getLogger(__name__)

BASE_DIR = utils.get_data_dir()


class InitialSetupRouter:
    """Wizard endpoints + the ``/`` dispatcher.

    ``/`` is owned by this router because it has to decide between the
    wizard and the post-auth dashboard based on whether any clients are
    logged in. Handlers from ``RootRouter`` are called in-process when
    we're past the auth gate.
    """

    def __init__(self, ctx: WebContext, root_handler):
        self.ctx = ctx
        self._root = root_handler  # bound RootRouter.root

    def register(self, app: web.Application) -> None:
        app.router.add_get("/", self.root)
        app.router.add_get("/initialSetup", self.initial_setup)
        app.router.add_put("/setApi", self.set_tg_api)
        app.router.add_post("/sendTgCode", self.send_tg_code)
        app.router.add_post("/tgCode", self.tg_code)
        app.router.add_post("/finishLogin", self.finish_login)

    # ---- public events for main.py to await ----------------------------

    def wait_for_api_token_setup(self):
        return self.ctx.api_set.wait()

    def wait_for_clients_setup(self):
        return self.ctx.clients_set.wait()

    # ---- handlers ------------------------------------------------------

    async def root(self, request):
        if self.ctx.clients_set.is_set():
            await self.ctx.ready.wait()
        if self.ctx.redirect_url:
            self.ctx.root_redirected.set()
            return web.Response(
                status=302, headers={"Location": self.ctx.redirect_url}
            )
        if self.ctx.client_data:
            # Past the auth gate — hand off to the dashboard renderer.
            return await self._root(request)
        return await self.initial_setup(request)

    @aiohttp_jinja2.template("initial_root.jinja2")
    async def initial_setup(self, request):
        return {
            "api_done": self.ctx.api_token is not None,
            "tg_done": bool(self.ctx.client_data),
            "hosting": self.ctx.hosting,
            "default_app": self.ctx.default_app,
        }

    async def set_tg_api(self, request):
        text = await request.text()
        if len(text) < 36:
            return web.Response(status=400)
        api_id = text[32:]
        api_hash = text[:32]
        if any(c not in string.hexdigits for c in api_hash) or any(
            c not in string.digits for c in api_id
        ):
            return web.Response(status=400)
        with open(
            os.path.join(self.ctx.data_root or BASE_DIR, "api_token.txt"),
            "w",
        ) as f:
            f.write(api_id + "\n" + api_hash)
        self.ctx.api_token = collections.namedtuple("api_token", ("ID", "HASH"))(
            api_id, api_hash
        )
        self.ctx.api_set.set()
        return web.Response()

    async def send_tg_code(self, request):
        text = await request.text()
        phone = telethon.utils.parse_phone(text)
        if not phone:
            return web.Response(status=400, text="invalid phone")
        # Use print(): main app logger is WARNING by default, INFO would be
        # eaten — and the user explicitly needs to see where the code went.
        print(f"[setup] sending code to +{phone} (api_id={self.ctx.api_token.ID})",
              flush=True)
        client = telethon.TelegramClient(
            telethon.sessions.MemorySession(),
            self.ctx.api_token.ID,
            self.ctx.api_token.HASH,
            connection=self.ctx.connection,
            proxy=self.ctx.proxy,
            connection_retries=3,
            **_device_kwargs(),
        )
        try:
            await client.connect()
            sent = await client.send_code_request(phone)
        except telethon.errors.rpcerrorlist.ApiIdInvalidError:
            print("[setup] Telegram rejected api_id/api_hash", flush=True)
            return web.Response(status=400, text="api_invalid")
        except telethon.errors.rpcerrorlist.PhoneNumberInvalidError:
            print("[setup] Telegram says the phone is invalid", flush=True)
            return web.Response(status=400, text="phone_invalid")
        except telethon.errors.rpcerrorlist.PhoneNumberBannedError:
            print("[setup] Telegram banned this phone", flush=True)
            return web.Response(status=403, text="phone_banned")
        except telethon.errors.FloodWaitError as e:
            print(f"[setup] flood wait: {e.seconds}s", flush=True)
            return web.Response(status=429, text=f"flood_wait:{e.seconds}")
        except Exception as e:
            logger.exception("send_code_request failed")
            print(f"[setup] send_code_request failed: {e}", flush=True)
            return web.Response(status=500, text=str(e))

        # SentCode tells us *where* Telegram delivered (or claims to deliver)
        # the code. Surface it so the user knows whether to look in SMS,
        # the Telegram app, or wait for a call.
        ch = type(sent.type).__name__.replace("SentCodeType", "").lower()
        print(f"[setup] code accepted by Telegram, channel={ch}", flush=True)
        self.ctx.sign_in_clients[phone] = client
        return web.Response(text=ch)

    async def tg_code(self, request):
        text = await request.text()
        if len(text) < 6:
            return web.Response(status=400)
        split = text.split("\n", 2)
        if len(split) not in (2, 3):
            return web.Response(status=400)
        code = split[0]
        phone = telethon.utils.parse_phone(split[1])
        password = split[2]
        if (
            (len(code) not in (5, 6) and not password)
            or any(c not in string.digits for c in code)
            or not phone
        ):
            return web.Response(status=400)
        client = self.ctx.sign_in_clients[phone]
        if not password:
            try:
                user = await client.sign_in(phone, code=code)
            except telethon.errors.SessionPasswordNeededError:
                return web.Response(status=401)  # Requires 2FA login
            except telethon.errors.PhoneCodeExpiredError:
                return web.Response(status=404)
            except telethon.errors.PhoneCodeInvalidError:
                return web.Response(status=403)
            except telethon.errors.FloodWaitError:
                return web.Response(status=421)
        else:
            try:
                user = await client.sign_in(phone, password=password)
            except telethon.errors.PasswordHashInvalidError:
                return web.Response(status=403)  # Invalid 2FA password
            except telethon.errors.FloodWaitError:
                return web.Response(status=421)
        del self.ctx.sign_in_clients[phone]
        client.phone = f"+{user.phone}"
        self.ctx.clients.append(client)
        return web.Response()

    async def finish_login(self, request):
        if not self.ctx.clients:
            return web.Response(status=400)
        self.ctx.clients_set.set()
        return web.Response()
