"""Device fingerprint passed to Telethon's ``TelegramClient``.

Telegram shows these fields on the user's *Active Sessions* screen and uses
them to route in-app login codes (``SentCodeTypeApp``) — Telegram is more
willing to deliver codes to an "Android" session when an existing Android
session is logged in.

We pin the values to a current real-world flagship: Pixel 10 Pro XL on
Android 16 (API 36). Bumping these is safe; just keep them plausible.
"""

from typing import Any, Dict

# What Active Sessions calls the device.
DEVICE_MODEL = "Google Pixel 10 Pro XL"

# OS / kernel string. Format mirrors what the official Telegram for Android
# client reports.
SYSTEM_VERSION = "Android 16 (SDK 36)"

# Bumped when a new official Telegram for Android stable lands. Matches the
# format "<semver> (<vcode>)" used by the real app.
APP_VERSION = "12.5.1"

# Language reported by the userbot itself.
LANG_CODE = "en"

# System locale.
SYSTEM_LANG_CODE = "en-US"


def telethon_kwargs() -> Dict[str, Any]:
    """Return the kwargs dict to splat into ``TelegramClient(**...)``."""
    return {
        "device_model": DEVICE_MODEL,
        "system_version": SYSTEM_VERSION,
        "app_version": APP_VERSION,
        "lang_code": LANG_CODE,
        "system_lang_code": SYSTEM_LANG_CODE,
    }
