# Security: как работают права команд

Права — это **13-битная битмаска**, лежащая на функции команды как
`func.security`. Перед dispatch'ем команды
`SecurityManager.check()`
([`friendly_telegram/security.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/security.py))
комбинирует эту маску с runtime-override'ами и решает, разрешено ли
вызывающему.

Тот же механизм используется для прав inline-обработчиков через
docstring-директиву `@allow:` — см. **[inline.md → @allow директива](inline.md)**.

---

## 13 флагов (с битовыми значениями)

| Флаг | Бит | Значение |
| ---- | --- | ------- |
| `OWNER` | `1 << 0` (1) | Сам аккаунт юзербота плюс ID из `db["friendly_telegram.security"]["owner"]`. |
| `SUDO` | `1 << 1` (2) | Аккаунт юзербота (всегда) плюс ID из `db["friendly_telegram.security"]["sudo"]`. |
| `SUPPORT` | `1 << 2` (4) | ID из `db["friendly_telegram.security"]["support"]`. |
| `GROUP_OWNER` | `1 << 3` (8) | Создатель чата/канала, где послана команда. |
| `GROUP_ADMIN_ADD_ADMINS` | `1 << 4` (16) | Админ с правом `add_admins`. |
| `GROUP_ADMIN_CHANGE_INFO` | `1 << 5` (32) | Админ с правом `change_info`. |
| `GROUP_ADMIN_BAN_USERS` | `1 << 6` (64) | Админ с правом `ban_users`. |
| `GROUP_ADMIN_DELETE_MESSAGES` | `1 << 7` (128) | Админ с правом `delete_messages`. |
| `GROUP_ADMIN_PIN_MESSAGES` | `1 << 8` (256) | Админ с правом `pin_messages`. |
| `GROUP_ADMIN_INVITE_USERS` | `1 << 9` (512) | Админ с правом `invite_users`. |
| `GROUP_ADMIN` | `1 << 10` (1024) | Любой админ (без специфичных прав). |
| `GROUP_MEMBER` | `1 << 11` (2048) | Любой участник текущей группы. |
| `PM` | `1 << 12` (4096) | Только в личке. |

Convenience-алиасы:

- `DEFAULT_PERMISSIONS = OWNER | SUDO` — применяется к командам без
  декоратора.
- `GROUP_ADMIN_ANY` — bitwise OR всех шести специфичных admin-прав.
- `PUBLIC_PERMISSIONS = GROUP_OWNER | GROUP_ADMIN_ANY | GROUP_MEMBER | PM`.

---

## Декораторы

Каждый декоратор просто выставляет биты на `func.security`. Они
аддитивные (`@loader.sudo` это `OWNER | SUDO`, не просто `SUDO`).

| Декоратор | Биты |
| --------- | -------- |
| `@loader.owner` | `OWNER` |
| `@loader.sudo` | `OWNER \| SUDO` |
| `@loader.support` | `OWNER \| SUDO \| SUPPORT` |
| `@loader.group_owner` | `OWNER \| SUDO \| GROUP_OWNER` |
| `@loader.group_admin` | `OWNER \| SUDO \| GROUP_ADMIN` |
| `@loader.group_admin_<right>` | `OWNER \| SUDO \| GROUP_ADMIN_<RIGHT>` |
| `@loader.group_member` | `OWNER \| SUDO \| GROUP_MEMBER` |
| `@loader.pm` | `OWNER \| SUDO \| PM` |
| `@loader.unrestricted` | Все 13 бит (фактически без проверок). |

Стэкать можно — два декоратора OR'ят биты:

```python
@loader.group_admin_ban_users
@loader.pm
async def kickcmd(self, message): ...
```

Если декоратор не приложен, команда падает на
`DEFAULT_PERMISSIONS = OWNER | SUDO`.

`@loader.ratelimit` **ортогонален** — он выставляет
`func.ratelimit = True` и просит dispatcher троттлить команду
per-user. Применяй сверху security-декоратора; в одиночку он не
гейтит доступ.

---

## Runtime-override'ы (per-command)

Пользователь может перепривязать маску любой команды без рестарта через
`.security <command>` (inline-клавиатура из модуля
[`GeekSecurity`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/modules/geek_security.py)).
Override хранится в
`db["friendly_telegram.security"]["masks"][f"{module}.{func}"]` и
**заменяет** значение декоратора при каждой проверке. Декоратор —
дефолт; не предполагай, что в рантайме ещё актуален.

`get_flags(func)` возвращает
`(override_or_func.security_or_DEFAULT) & bounding_mask`.

---

## Bounding mask (глобальный потолок)

`db["friendly_telegram.security"]["bounding_mask"]` (дефолт
`OWNER | SUDO`) AND'ится с финальной маской каждой команды и каждого
inline-обработчика. Сброс бита здесь выключает его везде — полезно для
"запереть всё под owner-only" без правки отдельных команд.
Конфигурится через `.security` (без аргументов).

```text
effective = (override or func.security or DEFAULT_PERMISSIONS) & bounding_mask
```

---

## Группы пользователей: `owner`, `sudo`, `support`

Три списка Telegram-ID в БД под namespace'ом
`friendly_telegram.security`:

- `owner` — extra-владельцы. Сам аккаунт юзербота *всегда* трактуется
  как owner; этот список — для добавления co-owner'ов.
- `sudo` — sudoers. Аккаунт юзербота автодобавляется на каждой проверке.
- `support` — read-only / support-юзеры.

Управляются через:

```text
.owneradd / .ownerrm / .ownerlist
.sudoadd  / .sudorm  / .sudolist
.supportadd / .supportrm / .supportlist
```

Добавление в любую группу проходит через inline-confirmation, потому что
даёт реальный доступ к юзерботу.

Списки перечитываются из БД на **каждой** проверке (`_reload_rights()`),
так что изменения вступают мгновенно без рестарта.

---

## Decision flow

Когда вызывается `SecurityManager.check(message, func)`:

1. Считается effective-маска (`get_flags(func)`). Если `0` → deny.
2. Если бит `OWNER` стоит и `sender_id` — юзербот или в `owner`-списке →
   **allow**.
3. Если бит `SUDO` стоит и `sender_id` — юзербот или в `sudo`-списке →
   **allow**.
4. Если бит `SUPPORT` стоит и `sender_id` в `support`-списке → **allow**.
5. Если `sender_id` в
   `db["friendly_telegram.main"]["blacklist_users"]` → **deny**
   (override'ит всё ниже — но не выше; owner/sudo/support уже прошли).
6. Если бит `PM` стоит и сообщение в DM → **allow**.
7. Если бит `GROUP_MEMBER` стоит и сообщение в группе → **allow**.
8. **Канал/супергруппа**: запрос участника через
   `GetParticipantRequest`, дальше:
   - `ChannelParticipantCreator` удовлетворяет `GROUP_OWNER`.
   - `ChannelParticipantAdmin` удовлетворяет `GROUP_ADMIN_<RIGHT>`,
     только если `admin_rights.<right>` участника = true. `GROUP_ADMIN`
     матчится с любым админом.
   - Toggle `db["friendly_telegram.security"]["any_admin"]` (`False`
     по дефолту) ослабляет это: любой админ удовлетворяет любому
     `GROUP_ADMIN_*`.
9. **Legacy chat**: `GetFullChatRequest` →
   `ChatParticipantCreator` / `ChatParticipantAdmin` с теми же
   семантиками.
10. Outgoing-сообщения от самого юзербота (`message.out`) обходят
    sender-проверки для owner/sudo-битов — это даёт юзерботу
    `.delete`'ить свои сообщения в restrictive-чатах без weirdness'а
    с правами.
11. Иначе → **deny** (dispatcher молча дропает команду).

---

## Подбор декоратора

- **Мутирующие, чувствительные или account-wide-команды** (eval,
  restart, config, account-настройки): `@loader.owner` или
  `@loader.sudo`.
- **Group-модерация**: подходящий `@loader.group_admin_*`, чтобы co-admin
  мог использовать там, где у него есть права, и только там.
- **Public read-only-команды** (`.alive`, `.ping`, fun/info-модули):
  `@loader.unrestricted`, *если только* не хочешь ограничить контактами
  через bounding mask.
- **Что-то, принимающее юзера на вход** (например, fetch info про
  другого юзера): сочетай декоратор с `@loader.ratelimit`, чтобы было
  сложнее заабузить.

---

## Rate limiting

`@loader.ratelimit` ортогонален security — он энфорсит per-user-cooldown
поверх любой permission-проверки. Всегда применяй security-декоратор
тоже; rate-limit в одиночку не гейтит доступ.

Окно cooldown'а и per-user-state живут в dispatcher'е; дефолтное
поведение — молча дропать второй вызов в окне, а не отвечать
rate-limit-сообщением (чтобы это нельзя было использовать для спама).
