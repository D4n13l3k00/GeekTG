"""Inline manager package.

Re-exports ``InlineManager`` and the helper types/functions so the
historical ``from friendly_telegram.inline import InlineManager``
(and any third-party ``from friendly_telegram.inline import edit``)
keeps working after the move from a single-file module to a package.
"""

from .manager import InlineManager
from .types import (
    BotMessage,
    GeekInlineQuery,
    InlineCall,
    _load_avatar,
    answer,
    array_sum,
    custom_next_handler,
    delete,
    edit,
    rand,
    unload,
)

__all__ = [
    "InlineManager",
    "InlineCall",
    "BotMessage",
    "GeekInlineQuery",
    "edit",
    "delete",
    "unload",
    "answer",
    "custom_next_handler",
    "rand",
    "array_sum",
    "_load_avatar",
]
