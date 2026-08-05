# Permissions

Every Discord permission bit, and whether this kit asks for it.

The point of this file is that you should not have to take anyone's word for the invite link. Discord has **53** permission bits; this kit requests **11** of them. Each one below is either used by a named command, or refused with a reason.

**Permissions integer for the invite URL: `2815059005131840`**

You can also just tick the boxes in the OAuth2 URL Generator — [SETUP.md](SETUP.md) step 4 lists them by name.

## Two parties, and Discord enforces the intersection

You **request** permissions in the invite. The server's admin **disposes** — they see the request, can trim it on approval, and separately control what your bot can do per channel via roles and channel overwrites. Your bot ends up with what you asked for *and* what they allowed, never more.

That is why this file exists: an admin looking at your invite can read exactly what each bit is for and decide, instead of guessing from a number.

## Requested (11 bits)

| Permission | Bit | Used by | Why |
|---|---|---|---|
| `ADD_REACTIONS` | `1 << 6` | `react add` | Adding a reaction. Removing your own needs nothing extra. |
| `VIEW_CHANNEL` | `1 << 10` | everything | Without it the channel is invisible and nothing else matters. |
| `SEND_MESSAGES` | `1 << 11` | `post`, `poll`, `verify` | Posting. Also required to create threads in a forum channel. |
| `EMBED_LINKS` | `1 << 14` | `post` | Without it, links you post render as bare text with no preview. |
| `ATTACH_FILES` | `1 << 15` | `post --file` | File upload. Drop it if you never upload. |
| `READ_MESSAGE_HISTORY` | `1 << 16` | `read`, `threads`, `pin list`, `react list`, `verify` | Reading past messages. Discord separates seeing a channel from reading its history. |
| `USE_EXTERNAL_EMOJIS` | `1 << 18` | `react` with a custom emoji from another server | Plain unicode emoji work without it. |
| `CREATE_PUBLIC_THREADS` | `1 << 35` | `thread create` | Starting a thread to hold a side conversation. Channel-scoped, not administration. |
| `SEND_MESSAGES_IN_THREADS` | `1 << 38` | `post --channel <threadId>` | Posting inside a thread is a separate permission from posting in its parent. |
| `SEND_POLLS` | `1 << 49` | `poll` | Sending a poll. Reading poll results comes back in `read` and needs nothing extra. |
| `PIN_MESSAGES` | `1 << 51` | `pin add`, `pin remove` | Pinning and unpinning. **Its own permission since 2025** — it no longer requires Manage Messages, so you do not have to grant the power to delete other people's messages just to pin one. |

## Not requested (41 bits)

This is a description of what the code does, not advice about what you should want. It is your bot. But asking for a permission no command can use is clutter in the approval dialog rather than caution, so these are left out.

| Permission | Bit | Why not |
|---|---|---|
| `CREATE_INSTANT_INVITE` | `1 << 0` | No command creates invites. The human does that once in the developer portal. |
| `KICK_MEMBERS` | `1 << 1` | Moderation. Nothing here moderates. |
| `BAN_MEMBERS` | `1 << 2` | Moderation. Nothing here moderates. |
| `ADMINISTRATOR` | `1 << 3` | Bypasses every per-channel permission at once. Also worth knowing as a diagnostic: an admin bot can read channels you believed were restricted from it, so it tells you nothing when you are testing whether a permission setup works. |
| `MANAGE_CHANNELS` | `1 << 4` | Server administration — creating, editing, deleting channels. |
| `MANAGE_GUILD` | `1 << 5` | Server administration. |
| `VIEW_AUDIT_LOG` | `1 << 7` | No command reads the audit log. |
| `PRIORITY_SPEAKER` | `1 << 8` | Voice. This kit is text-only. |
| `STREAM` | `1 << 9` | Voice/video. This kit is text-only. |
| `SEND_TTS_MESSAGES` | `1 << 12` | Would read messages aloud in voice channels. No command sends TTS. |
| `MANAGE_MESSAGES` | `1 << 13` | Deletes **other people's** messages and strips their reactions. `delete` only removes the bot's own message, which needs no permission at all — so this bit buys nothing this kit uses, and grants a lot it does not. |
| `MENTION_EVERYONE` | `1 << 17` | A deliberate choice by this kit rather than a limitation: no command mass-pings, and every message carries `allowed_mentions: {"parse": []}` so relayed text containing `@everyone` cannot fire one either. It is your bot — change it here and in `cmd_post` if you want that. |
| `VIEW_GUILD_INSIGHTS` | `1 << 19` | Server analytics. Nothing reads it. |
| `CONNECT` | `1 << 20` | Voice. |
| `SPEAK` | `1 << 21` | Voice. |
| `MUTE_MEMBERS` | `1 << 22` | Voice moderation. |
| `DEAFEN_MEMBERS` | `1 << 23` | Voice moderation. |
| `MOVE_MEMBERS` | `1 << 24` | Voice moderation. |
| `USE_VAD` | `1 << 25` | Voice. |
| `CHANGE_NICKNAME` | `1 << 26` | Would let the bot rename itself per server. No command does, and its name is set once in the developer portal. |
| `MANAGE_NICKNAMES` | `1 << 27` | Renames other people. |
| `MANAGE_ROLES` | `1 << 28` | Server administration, and a privilege-escalation surface. |
| `MANAGE_WEBHOOKS` | `1 << 29` | **Considered carefully because this README points at webhooks** as the way to post under several names. It only points — the kit never creates or manages one. Requesting a permission for a feature you do not have is clutter in the approval dialog, not caution. If you build webhook posting, take this bit then. |
| `MANAGE_GUILD_EXPRESSIONS` | `1 << 30` | Edits and deletes server emojis, stickers, sounds. |
| `USE_APPLICATION_COMMANDS` | `1 << 31` | For slash commands. This kit has none. |
| `REQUEST_TO_SPEAK` | `1 << 32` | Stage channels. Text-only kit. |
| `MANAGE_EVENTS` | `1 << 33` | Edits and deletes *everyone's* scheduled events. |
| `MANAGE_THREADS` | `1 << 34` | Archives, renames, deletes threads and reveals all private ones. `thread create` needs none of that. |
| `CREATE_PRIVATE_THREADS` | `1 << 36` | A bot creating threads other members cannot see is a surprising capability with no use case here. Public threads only. |
| `USE_EXTERNAL_STICKERS` | `1 << 37` | No command sends stickers. |
| `USE_EMBEDDED_ACTIVITIES` | `1 << 39` | Launches embedded Activities. Not applicable. |
| `MODERATE_MEMBERS` | `1 << 40` | Timeouts. Moderation. |
| `VIEW_CREATOR_MONETIZATION_ANALYTICS` | `1 << 41` | Monetization analytics. |
| `USE_SOUNDBOARD` | `1 << 42` | Voice. |
| `CREATE_GUILD_EXPRESSIONS` | `1 << 43` | Creates server-wide emojis and stickers. |
| `CREATE_EVENTS` | `1 << 44` | Scheduled events. Nothing here schedules. |
| `USE_EXTERNAL_SOUNDS` | `1 << 45` | Voice. |
| `SEND_VOICE_MESSAGES` | `1 << 46` | No command sends voice messages. |
| `SET_VOICE_CHANNEL_STATUS` | `1 << 48` | Voice. |
| `USE_EXTERNAL_APPS` | `1 << 50` | Governs user-installed apps sending public responses. This is a bot-token app, so it does not apply. |
| `BYPASS_SLOWMODE` | `1 << 52` | Lets the bot ignore a channel's rate limit. If an admin set slowmode, a bot posting through it is precisely what they were preventing. It backs off on 429 instead. |

## Capabilities that need no permission bit

Not everything is a permission. These work regardless of the bits above:

| Capability | Command | Note |
|---|---|---|
| Edit your own message | `edit` | Discord only ever lets you edit your own; there is no permission that grants editing someone else's. |
| Delete your own message | `delete` | Needs nothing. Deleting *someone else's* needs Manage Messages, which is refused above — so that returns a permissions error by design. |
| Remove your own reaction | `react remove` | Only removing *other people's* reactions needs Manage Messages. |
| Read poll results | `read` | Poll state arrives with the message. |
| Look up one user by ID | `user <id>` | Needs no permission and no privileged intent. |

## Two privileged intents (not permissions — toggles in the developer portal)

| Intent | Needed for | Note |
|---|---|---|
| **MESSAGE CONTENT** | everything that reads text | Without it every message body comes back **empty**, over plain HTTP too. It looks exactly like broken code. [SETUP.md](SETUP.md) step 2. |
| **SERVER MEMBERS** | `users` (listing a whole server) | Optional. `user <id>` looks people up individually without it, and the kit says so rather than failing opaquely. |

## Sources

Bit values and names were taken from Discord's own permissions reference rather than from memory, and the pin, thread, message and poll routes from their resource documentation. `1 << 47` is absent from Discord's table; it is not skipped here by oversight.

Checked against the live documentation on 2026-08-06.
