# Security: how command permissions work

Permissions are a **13-bit bitmask** stored on each command function as
`func.security`. Before dispatching the command, `SecurityManager.check()`
([`friendly_telegram/security.py`](../friendly_telegram/security.py))
combines that mask with runtime overrides and decides whether the caller is
allowed.

## The 13 flags

| Flag | Meaning |
| ---- | ------- |
| `OWNER` | The userbot account itself, plus user IDs in the `owner` group. |
| `SUDO` | User IDs in the `sudo` group. |
| `SUPPORT` | User IDs in the `support` group. |
| `GROUP_OWNER` | Creator of the chat/channel where the command was sent. |
| `GROUP_ADMIN_ADD_ADMINS` / `..._CHANGE_INFO` / `..._BAN_USERS` / `..._DELETE_MESSAGES` / `..._PIN_MESSAGES` / `..._INVITE_USERS` | Admin who has the matching Telegram admin right. |
| `GROUP_ADMIN` | Any admin (no specific right required). |
| `GROUP_MEMBER` | Any participant of the current group. |
| `PM` | Private messages only. |

## Decorators

Each decorator just sets a bit on `func.security`. They are additive
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
| `@loader.unrestricted` | All 13 bits |

Stacking is allowed — apply two decorators and their bits OR together:

```python
@loader.group_admin_ban_users
@loader.pm
async def kickcmd(self, message): ...
```

If you don't apply any decorator, the command falls back to
`DEFAULT_PERMISSIONS` = `OWNER | SUDO`.

## Runtime overrides (per-command)

The user can rebind any command's mask without restarting via
`.security <command>` (an inline keyboard from the
[`GeekSecurity`](../friendly_telegram/modules/geek_security.py) module).
The override is stored at `db["security"]["masks"][f"{module}.{func}"]`
and **replaces** the decorator value on every check. Your decorator is
just the default — never assume it's still in effect at runtime.

## Bounding mask (global ceiling)

`db["security"]["bounding_mask"]` (default `OWNER | SUDO`) is AND-ed over
the final mask of every command. If a bit is cleared here, no command
honours it anywhere — useful for "lock everything down to owner-only"
without touching individual commands. Configured via `.security` (with
no argument).

Effective mask:

```text
effective = (override or func.security or DEFAULT_PERMISSIONS) & bounding_mask
```

## User groups: `owner`, `sudo`, `support`

Three lists of Telegram user IDs in the database:

- `db["security"]["owner"]` — extra owners. The userbot account itself is
  *always* treated as owner; this list is for adding co-owners.
- `db["security"]["sudo"]` — sudoers. The userbot account is auto-added
  on every check.
- `db["security"]["support"]` — read-only/support users.

Managed by:

```text
.owneradd / .ownerrm / .ownerlist
.sudoadd  / .sudorm  / .sudolist
.supportadd / .supportrm / .supportlist
```

Adding to any group goes through an inline confirmation prompt because
it grants real access to the userbot.

The lists are re-read from the DB on **every** permission check, so changes
take effect immediately.

## Decision flow

When `SecurityManager.check(message, func)` runs:

1. Compute the effective mask. If `0` → deny.
2. If `OWNER` bit set and `sender_id` is the userbot or in `owner` list →
   **allow**.
3. Same for `SUDO`/`sudo` list and `SUPPORT`/`support` list.
4. If `sender_id` is in `db["main"]["blacklist_users"]` → **deny**
   (overrides everything below).
5. If `PM` bit set and the message is a DM → **allow**.
6. If `GROUP_MEMBER` bit set and the message is in a group → **allow**.
7. Channel/supergroup: query the participant via `GetParticipantRequest`,
   then:
   - `ChannelParticipantCreator` satisfies `GROUP_OWNER`.
   - `ChannelParticipantAdmin` satisfies `GROUP_ADMIN_<RIGHT>` only if
     the participant's `admin_rights.<right>` is true. `GROUP_ADMIN`
     matches any admin.
   - The toggle `db["security"]["any_admin"]` (`False` by default)
     loosens this so any admin satisfies any `GROUP_ADMIN_*` flag.
8. Legacy chat: same idea with `GetFullChatRequest` /
   `ChatParticipantCreator` / `ChatParticipantAdmin`.
9. Otherwise → **deny** (and the dispatcher silently drops the command).

## Picking the right decorator

- **Mutating, sensitive, or account-wide commands** (eval, restart, config,
  account settings): `@loader.owner` or `@loader.sudo`.
- **Group moderation**: the matching `@loader.group_admin_*` so a co-admin
  can use it where they have rights, and only there.
- **Public read-only commands** (`.alive`, `.ping`, fun/info modules):
  `@loader.unrestricted` *unless* you want them limited to your contacts via
  the bounding mask.
- **Anything that takes user input as a target** (e.g. fetch info about
  another user): pair the decorator with `@loader.ratelimit` to make it
  harder to abuse.

## Rate limiting

`@loader.ratelimit` is **orthogonal** to security — it enforces a per-user
cooldown on top of whatever permission check applies. Always apply a
security decorator as well; rate-limit alone does not gate access.
