#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2022 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

#    Modded by GeekTG Team

import argparse
import asyncio
import collections
import importlib
import json
import logging
import os
import random
import signal
import socket
import sqlite3
import sys

from telethon import TelegramClient, events
from telethon.errors.rpcerrorlist import (
    ApiIdInvalidError,
    AuthKeyDuplicatedError,
    PhoneNumberInvalidError,
)
from telethon.network.connection import (
    ConnectionTcpFull,
    ConnectionTcpMTProxyRandomizedIntermediate,
)
from telethon.sessions import SQLiteSession, StringSession

from . import __version__, loader, utils
from ._device import telethon_kwargs as _device_kwargs
from .database import backend, frontend
from .dispatcher import CommandDispatcher
from .translations.core import Translator

BASE_DIR = utils.get_data_dir()

try:
    from .web import core
except ImportError:
    web_available = False
    logging.exception("Unable to import web")
else:
    web_available = True


def run_config(db, data_root, phone=None, modules=None):
    """Load configurator.py"""
    from . import configurator

    return configurator.run(db, data_root, phone, phone is None, modules)


CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def get_config_key(key):
    """Parse and return key from config"""
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.loads(f.read())

        return config.get(key, False)
    except FileNotFoundError:
        return False


def save_config_key(key, value):
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.loads(f.read())
    except FileNotFoundError:
        config = {}

    config[key] = value

    with open(CONFIG_PATH, "w") as f:
        f.write(json.dumps(config))

    return True


save_config_key("use_fs_for_modules", get_config_key("use_fs_for_modules"))


def gen_port():
    """Pick a port: persisted one from config, else a random free one.

    Only invoked when the user did NOT pass ``--port`` (see
    ``parse_arguments``) — historically this ran on every startup as an
    eagerly-evaluated argparse default and uselessly hit the loopback
    listener for free-port detection.
    """
    port = get_config_key("port")
    if port:
        return port

    while True:
        port = random.randint(1024, 65535)  # 65535 is the last valid port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port


def save_db_type(use_file_db):
    return save_config_key("use_file_db", use_file_db)


def parse_arguments():
    """Parse the arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", "-s", action="store_true")
    parser.add_argument(
        "--port",
        dest="port",
        action="store",
        default=None,
        type=int,
        help="Web port (default: random free port, persisted in config.json)",
    )
    parser.add_argument("--phone", "-p", action="append")
    parser.add_argument("--token", "-t", action="append", dest="tokens")
    parser.add_argument("--no-nickname", "-nn", dest="no_nickname", action="store_true")
    parser.add_argument("--no-inline", dest="use_inline", action="store_false")
    parser.add_argument("--hosting", "-lh", dest="hosting", action="store_true")
    parser.add_argument("--default-app", "-da", dest="default_app", action="store_true")
    parser.add_argument("--web-only", dest="web_only", action="store_true")
    parser.add_argument("--no-web", dest="web", action="store_false")
    parser.add_argument(
        "--data-root",
        dest="data_root",
        default="",
        help="Root path to store session files in",
    )
    parser.add_argument(
        "--no-auth",
        dest="no_auth",
        action="store_true",
        help="Disable authentication and API token input, exitting if needed",
    )
    parser.add_argument(
        "--proxy-host",
        dest="proxy_host",
        action="store",
        help="MTProto proxy host, without port",
    )
    parser.add_argument(
        "--proxy-port",
        dest="proxy_port",
        action="store",
        type=int,
        help="MTProto proxy port",
    )
    parser.add_argument(
        "--proxy-secret",
        dest="proxy_secret",
        action="store",
        help="MTProto proxy secret",
    )
    parser.add_argument(
        "--docker-deps-internal",
        dest="docker_deps_internal",
        action="store_true",
        help="This is for internal use only. If you use it, things will go wrong.",
    )
    parser.add_argument(
        "--root",
        "--allow-root",
        "-R",
        dest="disable_root_check",
        action="store_true",
        help="Disable `force_insecure` warning when launching as root",
    )
    parser.add_argument(
        "--platform",
        dest="platform",
        default=None,
        help=(
            "Override platform display name shown in the startup banner and "
            ".info module (also via $GTG_PLATFORM)"
        ),
    )
    parser.add_argument(
        "--print-data-dir",
        dest="print_data_dir",
        action="store_true",
        help="Print the resolved data directory (sessions, config, modules) and exit",
    )
    arguments = parser.parse_args()
    logging.debug(arguments)
    # ``asyncio.run`` (used by ``main()``) selects ProactorEventLoop on
    # Windows automatically since Python 3.8 — no manual setup needed.
    return arguments


def get_phones(arguments):
    """Get phones from the --token, --phone, and environment"""
    phones = {
        phone.split(":", maxsplit=1)[0]: phone
        for phone in map(
            lambda f: f[18:-8],
            filter(
                lambda f: f.startswith("friendly-telegram-") and f.endswith(".session"),
                os.listdir(arguments.data_root or BASE_DIR),
            ),
        )
    }

    phones.update(
        **(
            {phone.split(":", maxsplit=1)[0]: phone for phone in arguments.phone}
            if arguments.phone
            else {}
        )
    )

    authtoken = {}
    if arguments.tokens:
        for token in arguments.tokens:
            phone = sorted(filter(lambda phone: ":" not in phone, phones.values()))[0]
            del phones[phone]
            authtoken[phone] = token

    return phones, authtoken


def get_api_token(arguments, use_default_app=False):
    """Get API Token from disk or environment"""
    api_token_type = collections.namedtuple("api_token", ("ID", "HASH"))

    # Allow user to use default API credintials
    # These are android ones
    if use_default_app:
        return api_token_type(2040, "b18441a1ff607e10a989891a5462e627")

    # Try to retrieve credintials from file, or from env vars
    try:
        with open(
            os.path.join(
                arguments.data_root or BASE_DIR,
                "api_token.txt",
            )
        ) as f:
            api_token = api_token_type(*[line.strip() for line in f.readlines()])
    except FileNotFoundError:
        try:
            from . import api_token
        except ImportError:
            try:
                api_token = api_token_type(os.environ["api_id"], os.environ["api_hash"])
            except KeyError:
                api_token = None

    return api_token


def get_proxy(arguments):
    """Get proxy tuple from --proxy-host, --proxy-port and --proxy-secret
    and connection to use (depends on proxy - provided or not)"""
    if (
        arguments.proxy_host is not None
        and arguments.proxy_port is not None
        and arguments.proxy_secret is not None
    ):
        logging.debug("Using proxy: %s:%s", arguments.proxy_host, arguments.proxy_port)
        return (
            (arguments.proxy_host, arguments.proxy_port, arguments.proxy_secret),
            ConnectionTcpMTProxyRandomizedIntermediate,
        )

    return None, ConnectionTcpFull


async def _shutdown(clients):
    """Disconnect every client and cancel any leftover tasks."""
    for c in clients:
        try:
            if c.is_connected():
                await c.disconnect()
        except Exception:
            logging.debug("disconnect failed", exc_info=True)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


class SuperList(list):
    """A list of Telethon clients with attribute fan-out.

    ``self.allclients.send_message("foo", "bar")`` dispatches the call to
    every client in the list. Hot-path lookups (``len``, indexing, etc.)
    go through native ``list`` because we override only ``__getattr__``,
    which Python invokes solely on attribute *misses*.
    """

    def __getattr__(self, attr):
        if not self:
            raise AttributeError(attr)
        sample = getattr(self[0], attr)
        if asyncio.iscoroutinefunction(sample):

            async def fanout(*args, **kwargs):
                return [await getattr(c, attr)(*args, **kwargs) for c in self]

            return fanout
        if callable(sample):
            return lambda *args, **kwargs: [
                getattr(c, attr)(*args, **kwargs) for c in self
            ]
        return [getattr(c, attr) for c in self]


async def _announce_web_ready(web):
    """Print reachable web URLs once the web UI has finished initializing.

    Cancellation-safe: returns silently if cancelled before the event fires
    (typical when shutdown happens before the last client logs in).
    """
    try:
        await web.ready.wait()
    except asyncio.CancelledError:
        return
    print()
    utils.print_web_urls(web.port)


async def _async_main(arguments):  # noqa: C901
    """Async core of :func:`main`."""
    clients = SuperList()
    phones, authtoken = get_phones(arguments)
    api_token = get_api_token(arguments, arguments.default_app)
    proxy, conn = get_proxy(arguments)

    if web_available:
        web = (
            core.Web(
                data_root=arguments.data_root,
                api_token=api_token,
                proxy=proxy,
                connection=conn,
                hosting=arguments.hosting,
                default_app=arguments.default_app,
            )
            if arguments.web
            else None
        )
    else:
        web = None

    if arguments.port is None:
        arguments.port = gen_port()
    save_config_key("port", arguments.port)

    while api_token is None:
        if arguments.no_auth:
            return
        if web:
            await web.start(arguments.port)
            print("Web mode ready for configuration")  # noqa: T001
            utils.print_web_urls(web.port)
            await web.wait_for_api_token_setup()
            api_token = web.api_token
        else:
            run_config({}, arguments.data_root)
            importlib.invalidate_caches()
            api_token = get_api_token(arguments)

    if authtoken:
        for phone, token in authtoken.items():
            try:
                client = TelegramClient(
                    StringSession(token),
                    api_token.ID,
                    api_token.HASH,
                    connection=conn,
                    proxy=proxy,
                    connection_retries=None,
                    **_device_kwargs(),
                )
                await client.start()
                clients.append(client)
            except ValueError:
                run_config({}, arguments.data_root)
                return

            clients[-1].phone = phone  # for consistency

    if not clients and not phones:
        if arguments.no_auth:
            return

        if web:
            if not web.running.is_set():
                await web.start(arguments.port)
                print("Web mode ready for configuration")  # noqa: T001
                utils.print_web_urls(web.port)
            await web.wait_for_clients_setup()
            clients = web.clients
            for client in clients:
                session = SQLiteSession(
                    os.path.join(
                        arguments.data_root or BASE_DIR,
                        f"friendly-telegram-+{'X' * (len(client.phone) - 5)}{client.phone[-4:]}",
                    )
                )

                session.set_dc(
                    client.session.dc_id,
                    client.session.server_address,
                    client.session.port,
                )
                session.auth_key = client.session.auth_key
                session.save()
                client.session = session
        else:
            phone = input("Please enter your phone: ")
            phones = {phone.split(":", maxsplit=1)[0]: phone}

    for phone_id, phone in phones.items():
        session = os.path.join(
            arguments.data_root or BASE_DIR,
            f"friendly-telegram{(('-' + phone_id) if phone_id else '')}",
        )

        try:
            client = TelegramClient(
                session,
                api_token.ID,
                api_token.HASH,
                connection=conn,
                proxy=proxy,
                connection_retries=None,
                **_device_kwargs(),
            )
            await client.start()
            client.phone = phone
            clients.append(client)
        except sqlite3.OperationalError as ex:
            print(
                f"Error initialising phone"
                f"{(phone or 'unknown')} {','.join(ex.args)}\n"
                ": this is probably your fault."
                "Try checking that this is"
                "the only instance running and"
                "that the session is not copied."
                "If that doesn't help, delete the file named"
                f"'friendly-telegram-{phone if phone else ''}.session'"
            )
            continue
        except (TypeError, AuthKeyDuplicatedError):
            os.remove(f"{session}.session")
            return await _async_main(arguments)
        except (ValueError, ApiIdInvalidError):
            run_config({}, arguments.data_root)
            return
        except PhoneNumberInvalidError:
            print(
                "Please check the phone number."
                "Use international format (+XX...)"
                " and don't put spaces in it."
            )
            continue

    loop = asyncio.get_running_loop()
    loop.set_exception_handler(
        lambda _, x: logging.error(
            "Exception on event loop! %s",
            x["message"],
            exc_info=x.get("exception", None),
        )
    )

    # POSIX signal hooks for clean ``docker stop`` / ``systemctl stop``.
    # Windows lacks loop.add_signal_handler — KeyboardInterrupt path in
    # ``main()`` covers Ctrl-C there.
    stop = asyncio.Event()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                pass

    runners = asyncio.gather(
        *(amain_wrapper(client, clients, web, arguments) for client in clients),
        return_exceptions=True,
    )
    waiter = asyncio.create_task(stop.wait())
    # Announce reachable URLs once the web UI is fully ready (i.e. after the
    # last client logs in). The setup-time print fires only on first-run /
    # missing-session paths; this one always fires for normal startups.
    announce = (
        asyncio.create_task(_announce_web_ready(web)) if web is not None else None
    )
    try:
        done, _ = await asyncio.wait(
            {runners, waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if waiter in done:
            print("\n⏻ Shutting down…", flush=True)
    except asyncio.CancelledError:
        # asyncio.run propagates CancelledError up to here when the loop
        # is being torn down; treat it the same as a graceful stop.
        pass
    finally:
        waiter.cancel()
        if announce is not None:
            announce.cancel()
        runners.cancel()
        # Drain runners so their CancelledError doesn't leak as "Task was
        # destroyed but it is pending!" warnings.
        try:
            await runners
        except (asyncio.CancelledError, Exception):
            pass
        await _shutdown(clients)


def _print_startup_banner(arguments):
    """Print where on disk we keep state — first thing the user sees."""
    data_dir = arguments.data_root or BASE_DIR
    print()
    print("📂 Data directory:", data_dir)
    print("   • config:  ", os.path.join(data_dir, "config.json"))
    print("   • api:     ", os.path.join(data_dir, "api_token.txt"))
    print("   • sessions:", os.path.join(data_dir, "friendly-telegram-*.session"))
    print("   • modules: ", os.path.join(data_dir, "loaded_modules"))
    print(f"🖥  Platform: {utils.get_platform_name()}")
    print()


def main():
    """Sync entrypoint used by ``[project.scripts]``."""
    arguments = parse_arguments()

    # Platform override propagates through env so any code path that asks
    # ``utils.get_platform_name()`` (modules, .info, banner) sees the same
    # value without us having to thread it everywhere.
    if arguments.platform:
        os.environ["GTG_PLATFORM"] = arguments.platform

    if arguments.print_data_dir:
        print(arguments.data_root or BASE_DIR)
        return

    _print_startup_banner(arguments)
    try:
        asyncio.run(_async_main(arguments))
    except KeyboardInterrupt:
        # Catches the Ctrl-C raised before our signal handler is installed
        # (rare, but possible during very early init) and on Windows where
        # loop.add_signal_handler is unavailable.
        print("\n⏻ Interrupted, exiting.", flush=True)
        sys.exit(130)


async def amain_wrapper(client, *args, **kwargs):
    """Wrap ``amain`` so locals get cleared on soft restart.

    ``CancelledError`` is the normal shutdown path (SIGINT/SIGTERM cancels
    the runners gather in ``_async_main``); swallow it silently so the user
    sees the "⏻ Shutting down…" line and not a 20-line traceback.
    """
    try:
        async with client:
            first = True
            while await amain(first, client, *args, **kwargs):
                first = False
    except asyncio.CancelledError:
        return


async def amain(first, client, allclients, web, arguments):
    """Entrypoint for async init, run once for each user"""
    setup = arguments.setup
    web_only = arguments.web_only
    client.parse_mode = "HTML"
    await client.start()

    handlers = logging.getLogger().handlers
    db = backend.CloudBackend(client)

    if setup:
        await db.init(lambda e: None)
        jdb = await db.do_download()

        try:
            pdb = json.loads(jdb)
        except (json.decoder.JSONDecodeError, TypeError):
            pdb = {}

        modules = loader.Modules(arguments.use_inline)
        babelfish = Translator([], [], arguments.data_root)
        await babelfish.init(client)
        modules.register_all()
        fdb = frontend.Database(db, True)
        await fdb.init()
        modules.send_config(fdb, babelfish)
        await modules.send_ready(
            client, fdb, allclients
        )  # Allow normal init even in setup

        for handler in handlers:
            handler.setLevel(50)

        pdb = run_config(
            pdb,
            arguments.data_root,
            getattr(client, "phone", "Unknown Number"),
            modules,
        )

        if pdb is None:
            # Setup cancelled — wipe the local config file for this account
            # (no Telegram channel to delete anymore).
            try:
                os.remove(db._db_path)
            except FileNotFoundError:
                pass
            return

        await db.do_upload(json.dumps(pdb))
        return False

    db = frontend.Database(db)
    await db.init()

    logging.debug("got db")
    logging.info("Loading logging config...")
    for handler in handlers:
        handler.setLevel(db.get(__name__, "loglevel", logging.WARNING))

    to_load = None

    babelfish = Translator(
        db.get(__name__, "langpacks", []),
        db.get(__name__, "language", ["en"]),
        arguments.data_root,
    )

    await babelfish.init(client)

    modules = loader.Modules()
    no_nickname = arguments.no_nickname

    if web:
        await web.add_loader(client, modules, db)
        await web.start_if_ready(len(allclients), arguments.port)
    if not web_only:
        dispatcher = CommandDispatcher(modules, db, no_nickname)
        client.dispatcher = dispatcher

    if not web_only:
        await dispatcher.init(client)
        modules.check_security = dispatcher.check_security

        client.add_event_handler(dispatcher.handle_incoming, events.NewMessage)

        client.add_event_handler(dispatcher.handle_incoming, events.ChatAction)

        client.add_event_handler(
            dispatcher.handle_command, events.NewMessage(forwards=False)
        )

        client.add_event_handler(dispatcher.handle_command, events.MessageEdited())

    modules.register_all(to_load)

    modules.send_config(db, babelfish)

    await modules.send_ready(client, db, allclients)

    if first:
        # One info-level line per client. The data dir / version / platform
        # banner already printed by ``_print_startup_banner`` before login
        # covers the rest. Build SHA is shown only when actually available
        # (git checkout) — wheel/Docker installs skip it silently.
        me = await client.get_me(True)
        version = ".".join(map(str, __version__))
        sha, _ = utils.get_git_info()
        build = f" build {sha[:7]}" if sha else ""
        logging.info(
            "🚀 GeekTG %s%s ready for user %d on %s",
            version,
            build,
            me.user_id,
            utils.get_platform_name(),
        )

    await client.run_until_disconnected()

    # Previous line will stop code execution, so this part is
    # reached only when client is by some reason disconnected
    # At this point we need to close database
    await db.close()
    return False
