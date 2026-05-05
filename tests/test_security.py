"""SecurityManager bitmask logic.

Covers the synchronous bits — flag constants, decorator stacking,
``get_flags`` arithmetic, and DB-driven overrides. The full async
``_check`` flow is deferred to a later wave (it requires faking
``GetParticipantRequest``/``GetFullChatRequest``).
"""

import pytest

from friendly_telegram import security
from friendly_telegram.security import (
    OWNER, SUDO, SUPPORT, GROUP_OWNER, GROUP_ADMIN, GROUP_MEMBER, PM,
    GROUP_ADMIN_BAN_USERS, GROUP_ADMIN_PIN_MESSAGES,
    DEFAULT_PERMISSIONS, ALL, BITMAP, SecurityManager,
)


class TestFlagConstants:
    def test_disjoint_bits(self):
        # Each flag is a distinct power-of-2; collectively they tile [0, ALL].
        flags = [OWNER, SUDO, SUPPORT, GROUP_OWNER,
                 1 << 4, 1 << 5, 1 << 6, 1 << 7, 1 << 8, 1 << 9,
                 GROUP_ADMIN, GROUP_MEMBER, PM]
        assert len(set(flags)) == 13
        assert sum(flags) == ALL

    def test_default_is_owner_plus_sudo(self):
        assert DEFAULT_PERMISSIONS == OWNER | SUDO

    def test_bitmap_round_trip(self):
        # BITMAP is the name→bit lookup used by ``.security`` UI
        for name, bit in BITMAP.items():
            assert isinstance(bit, int) and bit & ALL == bit
        assert BITMAP["OWNER"] == OWNER
        assert BITMAP["GROUP_ADMIN_BAN_USERS"] == GROUP_ADMIN_BAN_USERS


class TestDecorators:
    def _flags(self, fn):
        return getattr(fn, "security", 0)

    def test_owner_sets_only_owner(self):
        @security.owner
        def f(): pass
        assert self._flags(f) == OWNER

    def test_sudo_includes_owner(self):
        @security.sudo
        def f(): pass
        assert self._flags(f) == OWNER | SUDO

    def test_support_includes_sudo_and_owner(self):
        @security.support
        def f(): pass
        assert self._flags(f) == OWNER | SUDO | SUPPORT

    def test_pm_includes_default(self):
        @security.pm
        def f(): pass
        assert self._flags(f) == OWNER | SUDO | PM

    def test_group_admin_pin_messages(self):
        @security.group_admin_pin_messages
        def f(): pass
        assert self._flags(f) == OWNER | SUDO | GROUP_ADMIN_PIN_MESSAGES

    def test_unrestricted_is_all_bits(self):
        @security.unrestricted
        def f(): pass
        assert self._flags(f) == ALL

    def test_decorator_stacking_unions_bits(self):
        @security.pm
        @security.group_admin
        def f(): pass
        # pm = OWNER|SUDO|PM, group_admin = OWNER|SUDO|GROUP_ADMIN; union:
        assert self._flags(f) == OWNER | SUDO | PM | GROUP_ADMIN


class TestGetFlags:
    def _mgr(self, fake_db):
        # SecurityManager._reload_rights touches owner/sudo/support lists at
        # ctor time — make sure the DB returns plain lists, not None.
        m = SecurityManager(fake_db)
        return m

    def test_int_input_passes_through(self, fake_db):
        m = self._mgr(fake_db)
        assert m.get_flags(OWNER | SUDO) == OWNER | SUDO

    def test_function_default_is_decorator_value(self, fake_db):
        @security.sudo
        def f(): pass
        f.__module__ = "mymod"
        f.__name__ = "fcmd"
        m = self._mgr(fake_db)
        assert m.get_flags(f) == OWNER | SUDO

    def test_function_without_decorator_falls_back_to_default(self, fake_db):
        def f(): pass
        f.__module__ = "mymod"
        f.__name__ = "fcmd"
        m = self._mgr(fake_db)
        assert m.get_flags(f) == DEFAULT_PERMISSIONS

    def test_per_command_override_replaces_decorator(self, fake_db):
        @security.owner
        def f(): pass
        f.__module__ = "mymod"
        f.__name__ = "fcmd"
        fake_db.set("friendly_telegram.security", "masks",
                    {"mymod.fcmd": ALL})
        m = self._mgr(fake_db)
        # Override is gated by the bounding mask; default bm == DEFAULT_PERMISSIONS,
        # so even though override is ALL, only the bounding bits survive
        assert m.get_flags(f) == DEFAULT_PERMISSIONS

    def test_bounding_mask_caps_effective(self, fake_db):
        @security.unrestricted
        def f(): pass
        f.__module__ = "mymod"
        f.__name__ = "fcmd"
        fake_db.set("friendly_telegram.security", "bounding_mask", OWNER)
        m = self._mgr(fake_db)
        # ALL & OWNER → OWNER
        assert m.get_flags(f) == OWNER

    def test_invalid_bits_rejected(self, fake_db):
        # Mask with bit 13 (out of range) → returns False to drop the command.
        m = self._mgr(fake_db)
        assert m.get_flags(1 << 14) is False
