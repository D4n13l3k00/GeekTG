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

import logging

_formatter = logging.Formatter


class MemoryHandler(logging.Handler):
    """
    Keeps 2 buffers.
    One for dispatched messages.
    One for unused messages.
    When the length of the 2 together is 100
    truncate to make them 100 together,
    first trimming handled then unused.
    """

    def __init__(self, target, capacity):
        super().__init__(0)
        self.target = target
        self.capacity = capacity
        self.buffer = []
        self.handledbuffer = []
        self.lvl: int = logging.WARNING  # Default loglevel

    def setLevel(self, level):
        self.lvl = int(level)

    def dump(self):
        """Return a list of logging entries"""
        return self.handledbuffer + self.buffer

    def dumps(self, lvl=0):
        """Return all entries of minimum level as list of strings"""
        return [
            self.target.format(record)
            for record in (self.buffer + self.handledbuffer)
            if record.levelno >= lvl
        ]

    def emit(self, record):
        if len(self.buffer) + len(self.handledbuffer) >= self.capacity:
            if self.handledbuffer:
                del self.handledbuffer[0]
            else:
                del self.buffer[0]
        self.buffer.append(record)
        if record.levelno >= self.lvl >= 0:
            self.acquire()
            try:
                for precord in self.buffer:
                    self.target.handle(precord)
                self.handledbuffer = (
                    self.handledbuffer[-(self.capacity - len(self.buffer)) :]
                    + self.buffer
                )
                self.buffer = []
            finally:
                self.release()


_FMT = "%(asctime)s %(levelname).1s %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"

# Loggers that are too chatty at DEBUG/INFO to be useful on stdout but whose
# records we still want in the MemoryHandler buffer for ``.logs DEBUG``.
# Filtering here (on the StreamHandler) instead of via setLevel() on the
# logger keeps the buffer full without spamming the terminal.
_NOISY_PREFIXES = (
    "telethon",
    "asyncio",
    "urllib3",
    "git.cmd",
    "git.util",
)


class _StdoutNoiseFilter(logging.Filter):
    """Suppress sub-WARNING records from chatty libraries on stdout only."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return not any(
            record.name == p or record.name.startswith(p + ".") for p in _NOISY_PREFIXES
        )


def init():
    """Configure logging.

    The MemoryHandler buffers everything (so ``.logs`` command can show
    recent records); its dispatch threshold is set later from the per-user
    DB. The visible **default** is INFO so first-run setup tells the user
    *what is happening* (web URLs, code-request status, restart hints) —
    previously this was WARNING, leaving stdout silent on success paths.
    Override per user via ``loglevel`` config in the database.

    A noise filter is layered on the stdout handler so telethon / asyncio /
    urllib3 / gitpython chatter doesn't drown the userbot's own messages.
    The MemoryHandler buffer is unfiltered, so ``.logs DEBUG`` still shows
    everything.
    """
    formatter = _formatter(_FMT, _DATEFMT)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_StdoutNoiseFilter())
    mem = MemoryHandler(handler, 2500)
    mem.lvl = logging.INFO

    root = logging.getLogger()
    root.handlers = []
    root.addHandler(mem)
    root.setLevel(0)  # let handlers decide what's visible
    logging.captureWarnings(True)
