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

"""Utility functions to help modules do stuff"""

import asyncio
import functools
import io
import logging
import os
import shlex
import socket
import random
import string

import telethon
from telethon.tl.custom.message import Message
from telethon.tl.types import (
    PeerUser,
    PeerChat,
    PeerChannel,
    MessageEntityMentionName,
    User,
    MessageMediaWebPage,
)

from . import __version__


def get_platform_name():
    """Return the platform display name.

    Resolution order:

    1. ``$GTG_PLATFORM`` (or legacy ``$FTG_PLATFORM``) — explicit override
       set by the user or by ``--platform`` at startup.
    2. ``$LAVHOST`` — auto-detect lavHost.
    3. ``$PREFIX`` containing ``com.termux`` — Termux.
    4. Fallback: ``"📻 VDS"``.

    Not cached because the override env-var may be set after first import.
    """
    override = os.environ.get("GTG_PLATFORM") or os.environ.get("FTG_PLATFORM")
    if override:
        return override
    if "LAVHOST" in os.environ:
        return f"✌️ lavHost {os.environ['LAVHOST']}"
    if "com.termux" in os.environ.get("PREFIX", ""):
        return "📱 Termux"
    return "📻 VDS"


def get_args(message):
    """Get arguments from message (str or Message), return list of arguments"""
    try:
        message = message.message
    except AttributeError:
        pass

    if not message:
        return False

    message = message.split(maxsplit=1)

    if len(message) <= 1:
        return []

    message = message[1]

    try:
        split = shlex.split(message)
    except ValueError:
        return message  # Cannot split, let's assume that it's just one long message

    return list(filter(lambda x: len(x) > 0, split))


def get_args_raw(message):
    """Get the parameters to the command as a raw string (not split)"""
    try:
        message = message.message
    except AttributeError:
        pass

    if not message:
        return False

    args = message.split(maxsplit=1)

    if len(args) > 1:
        return args[1]

    return ""


def get_args_split_by(message, sep):
    """Split args by ``sep``, strip each section, drop blanks.

    The ``if section`` filter previously ran *before* the strip so a
    section consisting of only whitespace ("foo | | bar") would survive
    as an empty string in the output. Filter post-strip so callers can
    rely on "no blanks" actually meaning that.
    """
    raw = get_args_raw(message)
    return [stripped for section in raw.split(sep)
            if (stripped := section.strip())]


def get_chat_id(message):
    """Get the chat ID, but without -100 if its a channel"""
    return telethon.utils.resolve_id(message.chat_id)[0]


def rand(length):
    """Generate a random string of given length"""
    return "".join(
        [random.choice(string.ascii_letters + string.digits) for _ in range(length)]
    )


def get_version_raw():
    """Get the version of the userbot"""
    return ".".join(map(str, __version__))


def get_git_info():
    # Lazy import: ``gitpython`` is only needed for the startup banner /
    # ``.info`` and is a meaningful chunk of import time. Wheel/Docker
    # installs don't have ``.git`` anyway and end up in the except path.
    try:
        import git
        repo = git.Repo(search_parent_directories=True)
        ver = repo.head.commit.hexsha
    except Exception:
        ver = ""
    return [
        ver,
        f"https://github.com/D4n13l3k00/GeekTG/commit/{ver}" if ver else "",
    ]


def get_entity_id(entity):
    return telethon.utils.get_peer_id(entity)


def escape_html(text):
    """Pass all untrusted/potentially corrupt input here"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_quotes(text):
    """Escape quotes to html quotes"""
    return escape_html(text).replace('"', "&quot;")


def get_base_dir():
    """Return the installed package directory.

    ``utils`` lives at ``friendly_telegram/utils.py``, so its parent dir is
    the package root. Using ``__file__`` directly avoids the historic
    ``utils → main → utils`` import cycle.
    """
    return os.path.abspath(os.path.dirname(__file__))


def get_dir(mod):
    """Get directory of given module"""
    return os.path.abspath(os.path.dirname(os.path.abspath(mod)))


@functools.lru_cache(maxsize=1)
def get_data_dir():
    """Return user-writable data directory for sessions, config and modules.

    Resolution order:
      1. ``$GTG_DATA_DIR`` (or legacy ``$FTG_DATA_DIR``) if set
      2. ``$XDG_DATA_HOME/friendly-telegram`` (default
         ``~/.local/share/friendly-telegram``)

    Cached: the result is constant for a given process. The first call
    creates the directory; subsequent ones just return the cached path
    without any syscalls.
    """
    override = os.environ.get("GTG_DATA_DIR") or os.environ.get("FTG_DATA_DIR")
    if override:
        path = override
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
        path = os.path.join(xdg, "friendly-telegram")
    os.makedirs(path, exist_ok=True)
    return path


def _local_ips():
    """Return a sorted list of routable local IPs (IPv4 + IPv6, no loopback)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ips.add(info[4][0])
    except socket.gaierror:
        pass

    # The hostname-based lookup misses some setups (containers, NAT). Use the
    # "UDP-connect" trick to ask the kernel which interface would be used to
    # reach the internet — this exposes the real LAN IP without any traffic.
    for family, target in ((socket.AF_INET, ("8.8.8.8", 80)),
                           (socket.AF_INET6, ("2001:4860:4860::8888", 80))):
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(target)
                ips.add(s.getsockname()[0])
        except OSError:
            continue

    def _is_loopback(ip):
        return ip.startswith("127.") or ip == "::1"

    def _is_link_local(ip):
        return ip.startswith("169.254.") or ip.lower().startswith("fe80")

    cleaned = [ip for ip in ips if not _is_loopback(ip) and not _is_link_local(ip)]
    return sorted(cleaned, key=lambda ip: (":" in ip, ip))


def _public_ip(timeout=2.0):
    """Best-effort public IP lookup. Returns ``None`` on any failure."""
    import requests
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip",
                "https://ipv4.icanhazip.com"):
        try:
            r = requests.get(url, timeout=timeout)
            if r.ok and r.text.strip():
                return r.text.strip()
        except Exception:
            continue
    return None


AUTO_REQUIREMENTS = "auto_requirements.txt"


def _load_auto_requirements(path):
    """Read the persisted ``pkg==version`` manifest. Empty dict if absent."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Tolerate any pinned form (==, >=, ~=) by splitting on the
                # first comparator. We persist == ourselves, but if a user
                # hand-edits the file we don't want to corrupt it.
                for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                    if sep in line:
                        name, _, ver = line.partition(sep)
                        out[name.strip().lower()] = sep + ver.strip()
                        break
                else:
                    out[line.lower()] = ""
    except FileNotFoundError:
        pass
    return out


def _save_auto_requirements(path, manifest):
    """Write ``manifest`` (``{name: '==ver'}``) sorted, one entry per line."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(
            "# Packages installed at runtime by `# requires:` auto-installer.\n"
            "# Replayed by docker/entrypoint.sh after `uv sync` so deps survive\n"
            "# container restarts and `uv tool upgrade`. Edit if you must;\n"
            "# format: <name><pin>, e.g. `googletrans==4.0.0rc1`.\n"
        )
        for name in sorted(manifest):
            f.write(f"{name}{manifest[name]}\n")
    os.replace(tmp, path)


async def _resolve_installed_versions(python_exe, packages):
    """Ask the target python which versions of ``packages`` actually got installed.

    Best-effort: returns ``{name: '==ver'}`` for what we could resolve,
    leaves out the rest (manifest still records them with no pin).
    """
    import shutil
    import subprocess

    uv_bin = shutil.which("uv")
    if uv_bin:
        proc = await asyncio.create_subprocess_exec(
            uv_bin, "pip", "list", "--python", python_exe, "--format=json",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            python_exe, "-m", "pip", "list", "--format=json",
            "--disable-pip-version-check",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return {}
    try:
        import json as _json
        installed = {p["name"].lower(): p["version"] for p in _json.loads(out)}
    except Exception:
        return {}
    wanted = {p.lower() for p in packages}
    return {name: f"=={ver}" for name, ver in installed.items() if name in wanted}


def _normalize_requirement(spec):
    """Strip extras/markers from a requirement string, lowercase the name.

    ``Pillow[heif] >= 10`` → ``pillow``. We persist the resolved version
    separately, so the manifest just needs a clean package name to match.
    """
    spec = spec.strip()
    for sep in ("[", "==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
        if sep in spec:
            spec = spec.split(sep, 1)[0]
    return spec.strip().lower()


async def install_requirements(requirements, *, user_install=False, record=True):
    """Install ``requirements`` into the running interpreter's environment.

    Picks the best available installer at runtime:

    1. ``uv pip install --python <exe> ...`` — works in the uv-created venvs
       this project ships in (they do *not* contain pip).
    2. ``python -m pip install ...`` — classic path.
    3. ``python -m ensurepip --upgrade`` then ``-m pip`` — last resort when
       pip is missing but ensurepip is available.

    On success, also appends the resolved versions to
    ``<data_dir>/auto_requirements.txt`` so a subsequent ``uv sync --frozen``
    (e.g. on Docker entrypoint) doesn't wipe them. Pass ``record=False`` to
    opt out (used by tests / one-off installs).

    Returns the subprocess return code (``0`` on success).
    """
    import shutil
    import subprocess
    import sys

    base = ["install", "--upgrade", "-q",
            "--disable-pip-version-check",
            "--no-warn-script-location"]
    if user_install:
        base.append("--user")
    pkgs = list(requirements)

    uv_bin = shutil.which("uv")
    if uv_bin:
        argv = [uv_bin, "pip", "install", "--python", sys.executable, *pkgs]
        proc = await asyncio.create_subprocess_exec(*argv)
        rc = await proc.wait()
    else:
        async def _pip():
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", *base, *pkgs,
                stderr=subprocess.PIPE,
            )
            _, err = await proc.communicate()
            return proc.returncode, err or b""

        rc, err = await _pip()
        if rc != 0 and b"No module named pip" in err:
            # Bootstrap pip into the current venv, then retry once.
            boot = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "ensurepip", "--upgrade",
            )
            if await boot.wait() == 0:
                rc, err = await _pip()
        if err:
            sys.stderr.write(err.decode("utf-8", "replace"))

    if rc == 0 and record and pkgs:
        try:
            await _record_installed(pkgs)
        except Exception:
            logging.exception("install_requirements: failed to record manifest")
    return rc


async def _record_installed(packages):
    """Persist ``packages`` (raw requirement strings) to the data-dir manifest."""
    import sys
    path = os.path.join(get_data_dir(), AUTO_REQUIREMENTS)
    manifest = _load_auto_requirements(path)
    names = [_normalize_requirement(p) for p in packages]
    versions = await _resolve_installed_versions(sys.executable, names)
    for name in names:
        if not name:
            continue
        # Prefer a freshly-resolved == pin; fall back to "" (no pin) if we
        # couldn't read pip-list output for some reason.
        manifest[name] = versions.get(name, manifest.get(name, ""))
    _save_auto_requirements(path, manifest)


def print_web_urls(port):
    """Print every URL the user can use to reach the web setup."""
    def _fmt(host):
        return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"

    lines = ["", "🌐 Web UI is ready. Open one of:"]
    lines.append(f"  • {_fmt('localhost')}     (this machine only)")

    for ip in _local_ips():
        lines.append(f"  • {_fmt(ip)}     (local network)")

    public = _public_ip()
    if public:
        lines.append(f"  • {_fmt(public)}     (public — make sure port is open)")

    lines.append("")
    print("\n".join(lines))


async def get_user(message):
    """Get user who sent message, searching if not found easily"""
    try:
        return await message.client.get_entity(message.sender_id)
    except ValueError:  # Not in database. Lets go looking for them.
        logging.debug("user not in session cache. searching...")

    if isinstance(message.peer_id, PeerUser):
        try:
            await message.client.get_dialogs()
        except telethon.errors.rpcerrorlist.BotMethodInvalidError:
            return None

        return await message.client.get_entity(message.sender_id)

    if isinstance(message.peer_id, (PeerChannel, PeerChat)):
        async for user in message.client.iter_participants(
            message.peer_id, aggressive=True
        ):
            if user.id == message.sender_id:
                return user

        logging.critical("WTF! user isn't in the group where they sent the message")
        return None

    logging.critical("WTF! `peer_id` is not a user, chat or channel")
    return None


def run_sync(func, *args, **kwargs):
    """Run a non-async function in a new thread and return an awaitable"""
    # Returning a coro
    return asyncio.get_event_loop().run_in_executor(
        None, functools.partial(func, *args, **kwargs)
    )


def run_async(loop, coro):
    """Run an async function as a non-async function, blocking till it's done"""
    # When we bump minimum support to 3.7, use run()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def censor(
    obj, to_censor=None, replace_with="redacted_{count}_chars"
):  # pylint: disable=W0102
    # Safe to disable W0102 because we don't touch to_censor, mutably or immutably.
    """May modify the original object, but don't rely on it"""
    if to_censor is None:
        to_censor = ["phone"]

    for k, v in vars(obj).items():
        if k in to_censor:
            setattr(obj, k, replace_with.format(count=len(v)))
        elif k[0] != "_" and hasattr(v, "__dict__"):
            setattr(obj, k, censor(v, to_censor, replace_with))

    return obj


def relocate_entities(entities, offset, text=None):
    """Move all entities by offset (truncating at text)"""
    length = len(text) if text is not None else 0  # TODO: refactor about text=None

    for ent in entities.copy() if entities else ():
        ent.offset += offset
        if ent.offset < 0:
            ent.length += ent.offset
            ent.offset = 0
        if text is not None and ent.offset + ent.length > length:
            ent.length = length - ent.offset
        if ent.length <= 0:
            entities.remove(ent)

    return entities


async def answer(message, response, **kwargs):
    """Use this to give the response to a command"""
    if isinstance(message, list):
        delete_job = asyncio.ensure_future(
            message[0].client.delete_messages(message[0].input_chat, message[1:])
        )
        message = message[0]
    else:
        delete_job = None

    if (
        await message.client.is_bot()
        and isinstance(response, str)
        and len(response) > 4096
    ):
        kwargs.setdefault("asfile", True)

    kwargs.setdefault("link_preview", False)

    edit = message.out

    if not edit:
        kwargs.setdefault(
            "reply_to",
            getattr(message, "reply_to_msg_id", None),
        )

    parse_mode = telethon.utils.sanitize_parse_mode(
        kwargs.pop("parse_mode", message.client.parse_mode)
    )

    if isinstance(response, str) and not kwargs.pop("asfile", False):
        txt, ent = parse_mode.parse(response)

        if len(txt) >= 4096:
            file = io.BytesIO(txt.encode("utf-8"))
            file.name = "command_result.txt"

            ret = [
                await message.client.send_file(
                    message.peer_id,
                    file,
                    caption="<b>📤 Command output seems to be too long, so it's sent in file.</b>",  # noqa: E501
                ),
            ]

            if message.out:
                await message.delete()

            return ret

        ret = [
            await (message.edit if edit else message.respond)(
                txt, parse_mode=lambda t: (t, ent), **kwargs
            )
        ]
    elif isinstance(response, Message):
        if message.media is None and (
            response.media is None or isinstance(response.media, MessageMediaWebPage)
        ):
            ret = (
                await message.edit(
                    response.message,
                    parse_mode=lambda t: (t, response.entities or []),
                    link_preview=isinstance(response.media, MessageMediaWebPage),
                ),
            )
        else:
            ret = (await message.respond(response, **kwargs),)
    else:
        if isinstance(response, bytes):
            response = io.BytesIO(response)

        if isinstance(response, str):
            response = io.BytesIO(response.encode("utf-8"))

        if name := kwargs.pop("filename", None):
            response.name = name

        if message.media is not None and edit:
            await message.edit(file=response, **kwargs)
        else:
            kwargs.setdefault(
                "reply_to",
                getattr(message, "reply_to_msg_id", None),
            )
            ret = (await message.client.send_file(message.chat_id, response, **kwargs),)

    if delete_job:
        await delete_job

    return ret


async def get_target(message, arg_no=0):
    if any(
        isinstance(ent, MessageEntityMentionName) for ent in (message.entities or [])
    ):
        e = sorted(
            filter(lambda x: isinstance(x, MessageEntityMentionName), message.entities),
            key=lambda x: x.offset,
        )[0]
        return e.user_id

    if len(get_args(message)) > arg_no:
        user = get_args(message)[arg_no]
    elif message.is_reply:
        return (await message.get_reply_message()).sender_id
    elif hasattr(message.peer_id, "user_id"):
        user = message.peer_id.user_id
    else:
        return None

    try:
        ent = await message.client.get_entity(user)
    except ValueError:
        return None
    else:
        if isinstance(ent, User):
            return ent.id


def merge(a, b):
    """Merge dict ``a`` into dict ``b`` (in-place); return ``b``.

    Recursive for nested dicts, set-union for parallel lists, otherwise
    ``a`` overwrites ``b``. The previous implementation had a stray
    ``b[key] = a[key]`` outside the conditional that overwrote the fancy
    merge result on every key, effectively reducing ``merge`` to
    ``b.update(a)``.
    """
    for key in a:
        if key in b:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                b[key] = merge(a[key], b[key])
            elif isinstance(a[key], list) and isinstance(b[key], list):
                b[key] = list(set(b[key] + a[key]))
            else:
                b[key] = a[key]
        else:
            b[key] = a[key]
    return b
