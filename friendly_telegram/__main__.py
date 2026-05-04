#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2022 The Authors
#    Modded by GeekTG Team
#
#    Licensed under GNU AGPL v3 (see LICENSE).

"""Initial entrypoint."""

import getpass
import os
import sys


_ROOT_OVERRIDE_FLAGS = {"--root", "--allow-root", "-R"}


def _root_guard():
    argv_set = set(sys.argv)
    if getpass.getuser() == "root" and not (argv_set & _ROOT_OVERRIDE_FLAGS):
        print("!" * 30)
        print("NEVER EVER RUN USERBOT FROM ROOT")
        print("THIS IS THE THREAD FOR NOT ONLY YOUR DATA, ")
        print("BUT ALSO FOR YOUR DEVICE ITSELF!")
        print("!" * 30)
        print()
        print("TYPE force_insecure TO IGNORE THIS WARNING")
        print("TYPE ANYTHING ELSE TO EXIT:")
        if input("> ").lower() != "force_insecure":
            sys.exit(1)


def _cli():
    """Console entry point exposed via ``[project.scripts]`` (``gtg``)."""
    _root_guard()
    if sys.version_info < (3, 8, 0):
        print("Error: you must use at least Python version 3.8.0")
        sys.exit(1)

    from . import log
    log.init()
    from . import main
    main.main()


if __name__ == "__main__":
    # Accept both ``python -m friendly_telegram`` and the legacy
    # ``python -m friendly-telegram`` (resolved via the alias finder).
    if __package__ not in ("friendly_telegram", "friendly-telegram"):
        print("Error: you cannot run this as a script; you must execute as a package")
        sys.exit(1)
    _cli()
