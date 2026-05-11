# Security: how command permissions work

Permissions are a **13-bit bitmask** stored on each command function as
`func.security`. Before dispatching the command,
`SecurityManager.check()`
([`friendly_telegram/security.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/security.py))
combines that mask with runtime overrides and decides whether the caller
is allowed.

The exact same mechanism is used for inline-handler permissions via the
`@allow:` docstring directive — see
**[inline.md → @allow directive](inline.md)**.

---

## The 13 flags (with bit values)

| Flag | Bit | Meaning |
| ---- | --- | ------- |
| `OWNER` | `1 << 0` (1) | The userbot account itself, plus user IDs in `db["friendly_telegram.security"]["owner"]`. |
| `SUDO` | `1 << 1` (2) | Userbot account (always) plus IDs in `db["friendly_telegram.security"]["sudo"]`. |
| `SUPPORT` | `1 << 2` (4) | IDs in `db["friendly_telegram.security"]["support"]`. |
| `GROUP_OWNER` | `1 << 3` (8) | Creator of the chat/channel where the command was sent. |
| `GROUP_ADMIN_ADD_ADMINS` | `1 << 4` (16) | Admin with `add_admins` right. |
| `GROUP_ADMIN_CHANGE_INFO` | `1 << 5` (32) | Admin with `change_info` right. |
| `GROUP_ADMIN_BAN_USERS` | `1 << 6` (64) | Admin with `ban_users` right. |
| `GROUP_ADMIN_DELETE_MESSAGES` | `1 << 7` (128) | Admin with `delete_messages` right. |
| `GROUP_ADMIN_PIN_MESSAGES` | `1 << 8` (256) | Admin with `pin_messages` right. |
| `GROUP_ADMIN_INVITE_USERS` | `1 << 9` (512) | Admin with `invite_users` right. |
| `GROUP_ADMIN` | `1 << 10` (1024) | Any admin (no specific right required). |
| `GROUP_MEMBER` | `1 << 11` (2048) | Any participant of the current group. |
| `PM` | `1 << 12` (4096) | Private messages only. |

Convenience aliases:

- `DEFAULT_PERMISSIONS = OWNER | SUDO` — applied to commands without a
  decorator.
- `GROUP_ADMIN_ANY` — bitwise OR of all six specific admin-right bits.
- `PUBLIC_PERMISSIONS = GROUP_OWNER | GROUP_ADMIN_ANY | GROUP_MEMBER | PM`.

---

## Decorators

Each decorator just sets bits on `func.security`. They are additive
(`@loader.sudo` is `OWNER | SUDO`, not just `SUDO`).

| Decorator | Bits set |
| --------- | -------- |
| `@loader.owner` | `OWNER` |
| `@loader.sudo` | `OWNER \| SUDO` |
| `@loader.support` | `OWNER \| SUDO \| SUPPORT` |
| `@loader.group_owner` | `OWNER \| SUDO \| GROUP_OWNER` |
| `@loader.group_admin` | `OWNER \| SUDO \| GROUP_ADMIN` |
| `@loader.group_admin_<right>` | `OWNER \| SUDO \| GROUP_ADMIN_<RIGHT>` |
| `@loader.group_member` | `OWNER \| SUDO \| GROUP_MEMBER` |
| `@loader.pm` | `OWNER \| SUDO \| PM` |
| `@loader.unrestricted` | All 13 bits (effectively no check). |

Stacking is allowed — apply two decorators and their bits OR together:

```python
@loader.group_admin_ban_users
@loader.pm
async def kickcmd(self, message): ...
```

If you don't apply any decorator, the command falls back to
`DEFAULT_PERMISSIONS = OWNER | SUDO`.

`@loader.ratelimit` is **orthogonal** — it sets `func.ratelimit = True`
and asks the dispatcher to throttle the command per-user. Apply it on
top of a security decorator; alone, it does not gate access.

---

## Runtime overrides (per-command)

The user can rebind any command's mask without restarting via
`.security <command>` (an inline keyboard from the
[`GeekSecurity`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/modules/geek_security.py) module).
The override is stored at
`db["friendly_telegram.security"]["masks"][f"{module}.{func}"]` and
**replaces** the decorator value on every check. Your decorator is
just the default — never assume it's still in effect at runtime.

`get_flags(func)` returns
`(override_or_func.security_or_DEFAULT) & bounding_mask`.

---

## Bounding mask (global ceiling)

`db["friendly_telegram.security"]["bounding_mask"]` (default
`OWNER | SUDO`) is AND-ed over the final mask of every command and
every inline handler. Clearing a bit here disables it everywhere —
useful for "lock everything down to owner-only" without touching
individual commands. Configured via `.security` (no argument).

```text
effective = (override or func.security or DEFAULT_PERMISSIONS) & bounding_mask
```

---

## User groups: `owner`, `sudo`, `support`

Three lists of Telegram user IDs in the database under the
`friendly_telegram.security` namespace:

- `owner` — extra owners. The userbot account itself is *always*
  treated as owner; this list is for adding co-owners.
- `sudo` — sudoers. The userbot account is auto-added on every check.
- `support` — read-only/support users.

Managed by:

```text
.owneradd / .ownerrm / .ownerlist
.sudoadd  / .sudorm  / .sudolist
.supportadd / .supportrm / .supportlist
```

Adding to any group goes through an inline confirmation prompt because
it grants real access to the userbot.

The lists are re-read from the DB on **every** permission check
(`_reload_rights()`), so changes take effect immediately without restart.

---

## Decision flow

When `SecurityManager.check(message, func)` runs:

1. Compute the effective mask (`get_flags(func)`). If `0` → deny.
2. If `OWNER` bit set and `sender_id` is the userbot or in `owner` list →
   **allow**.
3. If `SUDO` bit set and `sender_id` is the userbot or in `sudo` list →
   **allow**.
4. If `SUPPORT` bit set and `sender_id` is in `support` list → **allow**.
5. If `sender_id` is in
   `db["friendly_telegram.main"]["blacklist_users"]` → **deny**
   (overrides everything below — not above; owner/sudo/support already
   passed).
6. If `PM` bit set and the message is a DM → **allow**.
7. If `GROUP_MEMBER` bit set and the message is in a group → **allow**.
8. **Channel/supergroup**: query the participant via
   `GetParticipantRequest`, then:
   - `ChannelParticipantCreator` satisfies `GROUP_OWNER`.
   - `ChannelParticipantAdmin` satisfies `GROUP_ADMIN_<RIGHT>` only if
     the participant's `admin_rights.<right>` is true. `GROUP_ADMIN`
     matches any admin.
   - The toggle
     `db["friendly_telegram.security"]["any_admin"]` (`False` by
     default) loosens this so any admin satisfies any `GROUP_ADMIN_*`
     flag.
9. **Legacy chat**: `GetFullChatRequest` →
   `ChatParticipantCreator` / `ChatParticipantAdmin` with the same
   semantics.
10. Outgoing messages from the userbot itself (`message.out`) bypass
    sender checks for owner/sudo bits — this lets the userbot `.delete`
    its own messages in restrictive chats without permissions
    weirdness.
11. Otherwise → **deny** (the dispatcher silently drops the command).

---

## Picking the right decorator

- **Mutating, sensitive, or account-wide commands** (eval, restart,
  config, account settings): `@loader.owner` or `@loader.sudo`.
- **Group moderation**: the matching `@loader.group_admin_*` so a
  co-admin can use it where they have rights, and only there.
- **Public read-only commands** (`.alive`, `.ping`, fun/info modules):
  `@loader.unrestricted` *unless* you want them limited to your contacts
  via the bounding mask.
- **Anything that takes user input as a target** (e.g. fetch info about
  another user): pair the decorator with `@loader.ratelimit` to make it
  harder to abuse.

---

## Rate limiting

`@loader.ratelimit` is orthogonal to security — it enforces a per-user
cooldown on top of whatever permission check applies. Always apply a
security decorator as well; rate-limit alone does not gate access.

The cooldown window and per-user state live in the dispatcher; the
default behaviour is to silently drop the second invocation within the
window rather than send a rate-limit message (so it can't be used to
spam).
