"""``ModuleContext`` — the one bundle of dependencies a module gets.

Today the loader scatters dependencies across four phases (constructor,
``complete_registration``, ``send_config_one``, ``send_ready_one``). New
code should read from a single ``self.ctx`` set by the framework before
``client_ready`` runs.

This is deliberately small and additive: existing attributes
(``self.allmodules``, ``self.inline``, ``self.allclients``, ``self.babel``)
keep working unchanged, so the legacy and new APIs can coexist while
core modules migrate one at a time.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from telethon import TelegramClient

    from ..database.frontend import Database
    from ..inline.manager import InlineManager
    from ..loader import Modules


@dataclass(frozen=True)
class ModuleContext:
    """Everything a module needs to do its job, in one place.

    Frozen so a misbehaving module can't swap the loader's view of the
    world out from under it (e.g. assigning ``ctx.client = …``).
    """

    client: "TelegramClient"
    db: "Database"
    inline: "InlineManager"
    modules: "Modules"
    allclients: Sequence["TelegramClient"]
    log: Callable[..., Any]
    origin: str = "<file>"
