# Slack scopes — what this kit asks for, and what it refuses

Slack does not have a fixed permission universe the way Discord does. Discord has **53 permission bits** and a bot's invite is an integer, so its kit can enumerate all 53 and account for every one. Slack has **named OAuth scopes**, the list grows, and there is no integer shortcut — so there is no honest equivalent of "11 of 53, here are the other 42."

What this document does instead: every scope in [`manifest.json`](manifest.json) is listed with the command that needs it, and the notable ones this kit **deliberately does not request** are listed with the reason. If a scope is in the manifest and not in this table, that is a defect — report it.

**Requesting is not receiving.** A workspace admin sees the whole list at install, can refuse the app outright, and separately controls which channels the bot is in. Slack enforces the intersection, and channel membership is a separate axis from scopes entirely.

**Changing scopes requires a reinstall.** Editing the manifest does nothing to an already-installed app until it is installed again, and `missing_scope` after a manifest edit almost always means that step was skipped. This is the *only* thing that needs a second install — one install returns both the bot and user tokens, because the manifest requests both.

---

## Bot token scopes (`xoxb-`)

| Scope | Needed by | Why |
|---|---|---|
| `team:read` | `check` | Read the workspace name, so `check` can say *which* workspace the token belongs to. A token that works is not the same as a token that works **here**. |
| `channels:read` | `channels`, `check --channel` | List public channels and their IDs. Listing only — it does not permit reading messages. |
| `channels:history` | `read`, `verify` | Read messages in a public channel. **Not sufficient on its own** — see the membership note below. |
| `channels:join` | `join` | Let the bot add itself to a *public* channel, so a human does not have to. |
| `groups:read` | `channels`, `check --channel` | The private-channel equivalent of `channels:read`. Without it, private channels are not merely unreadable — they are invisible, and indistinguishable from not existing. |
| `groups:history` | `read`, `verify` | Read messages in a private channel the bot has been invited to. There is no self-join equivalent for private channels. |
| `chat:write` | `post`, `reply`, `edit`, `delete`, `verify` | Post messages, and edit or delete the bot's **own**. Slack offers apps no way to modify anyone else's message, and this kit requests no scope that would change that. |
| `chat:write.customize` | `post --as` | Post with a per-message username and icon. **This is the scope that replaces Discord's webhook workaround** — on Discord a bot has exactly one identity everywhere and expressive posting needs a separate send-only webhook; on Slack it is one scope on the normal send. |
| `reactions:read` | `react list` | Read reactions on a message. |
| `reactions:write` | `react add`, `react remove` | Add and remove the bot's **own** reactions. It cannot remove anyone else's. |
| `pins:read` | `pin list` | List pinned messages. |
| `pins:write` | `pin add`, `pin remove` | Pin and unpin. |
| `files:read` | `read` | Resolve file attachments that appear in messages. Without it a message with a file reads as having an unresolvable blob. |
| `files:write` | `post --file` | Upload files. |
| `users:read` | `user`, `users`, `read` | Turn a user ID into a display name. Without it every message author is an opaque `U…` ID. |
| `channels:write.invites` | `invite` | Invite people to a public channel. |
| `groups:write.invites` | `invite` | The same for a private channel. |
| `conversations.connect:write` | `invite --email` | Send a Slack Connect invitation to an **email address** outside the workspace. This is the scope behind `conversations.inviteShared`, and it requires the bot to already be a member of the target channel. |
| `im:read`, `im:write`, `im:history` | `dm` | Open, send to, and read a direct message with a person. Drop all three if you never want the bot in DMs — nothing else depends on them. |

---

## The read-only set

If you are wiring an agent to a channel other people can write in, start here. These scopes let the bot **see** and **report**, and give it no way to say anything:

```
team:read  channels:read  channels:history  groups:read  groups:history
users:read  reactions:read  pins:read  files:read
```

Drop everything else from the manifest and reinstall. Exactly this much keeps working:

**Works:** `check`, `check --channel`, `check --member`, `channels`, `read`, `threads`, `user`, `users`, `react list`, `pin list`. (`check --user` is unaffected either way — it reads the **user** token, whose `identify` scope is a separate axis from this bot-scope list.)
**Fails with `missing_scope`:** `post`, `reply`, `edit`, `delete`, `join`, `react add`, `react remove`, `pin add`, `pin remove`, `invite`, `dm`, and `verify` — which posts, so it cannot run read-only by design.

Those failures are the correct outcome: a read-only bot that silently keeps the ability to post is not read-only. Note that `react` and `pin` are split across the line — their `list` half is a read and their `add`/`remove` half is a write, so dropping the write scope leaves the verb present but half-disabled.

Note also what the read-only set does **not** protect you from: it stops the bot writing, not the bot reading something it should not. Channel membership is still the axis that decides what it can see.

Add write scopes back one at a time, once you know who is in the room. `chat:write` is the one that changes the risk, because it is the one that lets a prompt-injected agent act.

---

## Deliberately not requested

Each of these is a scope a reasonable person might expect, and each is left out on purpose.

| Scope | Why not |
|---|---|
| `channels:manage`, `groups:write` | Creates, renames, and **archives** channels. This is the largest single refusal and it is a real divergence from the Discord kit's posture: that kit refuses `MANAGE_CHANNELS` and keeps a clean "requests nothing administrative" claim. If you add this scope, that claim no longer holds for your install — say so to whoever approves it. Add it only if you specifically want the bot creating or archiving channels. |
| `chat:write.public` | Lets a bot post into a public channel it has **not joined**. Convenient, and precisely the wrong default for a kit whose whole safety story is that a bot's reach is visible in the member list. If the bot is in the channel, people can see it is in the channel. |
| `users:read.email` | Email addresses are PII and no command here needs one. `invite --email` sends to an address you supply; it does not read addresses out of the workspace. |
| `admin.*` | Workspace administration. Nothing here needs it and it should be very hard to obtain by accident. |
| `search:read` | Workspace-wide search across everything the token can reach. A large read surface for a capability no command uses. |
| `usergroups:write`, `bookmarks:write`, `canvases:write`, `links:write` | Write access to workspace furniture no command touches. |
| `dnd:read`, `emoji:read`, `metadata.message:read`, `usergroups:read`, `bookmarks:read`, `canvases:read`, `app_mentions:read`, `mpim:read`, `mpim:history`, `mpim:write` | Read scopes for objects no command reads. They are cheap and harmless, which is exactly why they accumulate — every one of them widens what a leaked token reaches, for no capability gained. |

---

## User token scopes (`xoxp-`)

The user token acts as **you**, with your access. This kit asks for as little as it can, and every use is one Slack offers no bot equivalent for.

| Scope | Needed by | Why |
|---|---|---|
| `identify` | `check --user` | Confirm the user token is valid and say whose it is. This is the minimum that makes the token verifiable at all. |

If you add user scopes beyond this, understand what you are doing: a `xoxp-` token reaches every channel **you** are in, including ones you never intended to expose to an automation, and anything it posts is posted as a human. The bot token is the one that should grow.

---

## The membership axis, which is not a scope at all

The single most common Slack failure in this kit is not a missing scope.

`channels:history` grants the *ability* to read public-channel messages. It does not put the bot **in** any channel, and a bot must be a member to read one. So a correctly-scoped bot will list `#general` happily and then return `not_in_channel` when asked to read it.

No scope fixes this. Either invite the bot (`/invite @yourname-bot`) or, for a public channel, let it add itself with `join`. For a private channel there is no self-join — a human must invite it.

`check --member <channel>` exists to answer exactly this question before anything else depends on the answer.

---

## Compared to the Discord side

Worth reading if you know the Discord kit, because the differences are not cosmetic:

- **No content intent.** Discord's single biggest documented footgun — the MESSAGE CONTENT intent, off by default, making every message come back blank — has no Slack equivalent. Slack's analogous silent failure is channel membership, above.
- **Named scopes, not bits.** No `permissions=2815059005131840` shortcut, and no fixed universe to enumerate exhaustively.
- **Multi-identity is a scope, not a mechanism.** `chat:write.customize` versus Discord's separate send-only webhooks.
- **Two tokens from one install.** Discord has one bot token; Slack returns a bot token and a user token together, because the manifest requests both scope sets.
- **No poll primitive.** Discord has a native poll object behind `SEND_POLLS`. Slack does not: a poll is Block Kit elements plus interaction handling, which needs a request endpoint this kit deliberately does not have. `poll` therefore does not exist on the Slack side, and adding it would mean abandoning the no-daemon property.
