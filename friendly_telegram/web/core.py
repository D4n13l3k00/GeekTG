"""Web entry point.

Composes a single ``aiohttp`` application from independent routers
sharing a ``WebContext``. Replaces the previous multi-inheritance
``core.Web(initial_setup.Web, root.Web, status.Web)`` chain — adding a
new sub-section is now a one-liner here, not a four-file kwargs.pop()
exercise.
"""

import asyncio
import inspect
from importlib.resources import files

import aiohttp_jinja2
import jinja2
from aiohttp import web

from .context import WebContext
from .initial_setup import InitialSetupRouter
from .root import RootRouter
from .status import StatusRouter

_STATIC_DIR = str(files("friendly_telegram.web").joinpath("static"))


class Web:
    """Owns the aiohttp app and the runtime lifecycle of every router."""

    def __init__(self, *, api_token=None, data_root=None, connection=None,
                 hosting=False, default_app=False, proxy=None):
        self.ctx = WebContext(
            api_token=api_token,
            data_root=data_root,
            connection=connection,
            hosting=hosting,
            default_app=default_app,
            proxy=proxy,
        )
        self.runner = None
        self.port = None
        self.running = asyncio.Event()
        # ``ready`` is consumed by main.py and InitialSetupRouter.root —
        # keep it on ctx so all routers see the same Event.
        self.ready = self.ctx.ready

        self.app = web.Application()
        aiohttp_jinja2.setup(
            self.app,
            filters={"getdoc": inspect.getdoc, "ascii": ascii},
            loader=jinja2.PackageLoader("friendly_telegram.web", "templates"),
        )

        # Routers — order is irrelevant beyond ``InitialSetupRouter`` needing
        # the dashboard's ``root`` handler to delegate to once auth completes.
        self.root_router = RootRouter(self.ctx)
        self.status_router = StatusRouter(self.ctx)
        self.initial_router = InitialSetupRouter(
            self.ctx, root_handler=self.root_router.root,
        )
        self.root_router.register(self.app)
        self.status_router.register(self.app)
        self.initial_router.register(self.app)

        self.app.router.add_get("/favicon.ico", self.favicon)
        self.app.router.add_static("/static", _STATIC_DIR)

    # ---- backwards-compat shims ---------------------------------------
    #
    # main.py reaches into ``web.api_token``, ``web.client_data``,
    # ``web.redirect_url``, ``web.wait_for_clients_setup()`` etc — keep
    # those addressable without forcing a main.py update in this commit.
    @property
    def api_token(self):
        return self.ctx.api_token

    @api_token.setter
    def api_token(self, value):
        self.ctx.api_token = value

    @property
    def client_data(self):
        return self.ctx.client_data

    @property
    def redirect_url(self):
        return self.ctx.redirect_url

    @redirect_url.setter
    def redirect_url(self, value):
        self.ctx.redirect_url = value

    @property
    def clients(self):
        return self.ctx.clients

    @property
    def root_redirected(self):
        return self.ctx.root_redirected

    @property
    def started_at(self):
        return self.ctx.started_at

    def wait_for_api_token_setup(self):
        return self.initial_router.wait_for_api_token_setup()

    def wait_for_clients_setup(self):
        return self.initial_router.wait_for_clients_setup()

    # ---- lifecycle -----------------------------------------------------

    async def start_if_ready(self, total_count, port):
        if total_count <= len(self.ctx.client_data):
            if not self.running.is_set():
                await self.start(port)
            self.ready.set()

    async def start(self, port):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.port = port
        site = web.TCPSite(self.runner, None, self.port)
        await site.start()
        self.running.set()

    async def stop(self):
        await self.runner.shutdown()
        await self.runner.cleanup()
        self.running.clear()
        self.ready.clear()

    async def add_loader(self, client, loader, db):
        self.ctx.client_data[(await client.get_me(True)).user_id] = (
            loader, client, db,
        )

    @staticmethod
    async def favicon(request):
        return web.Response(
            status=301, headers={"Location": "/static/bot_avatar.png"}
        )
