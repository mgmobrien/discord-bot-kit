# The human part

**This is the only section a person has to do.** It is six steps in a browser and takes about five minutes. Everything after this is your agent's job.

You need Discord open in a browser and admin rights on the server you were invited to (or a friend there who has them — step 5 says which).

---

### 1. Create the application

Go to **https://discord.com/developers/applications** → **New Application**.

Give it a name. This is what your bot will be called in the channel, so pick something you'd like to see posting — your name, your machine's name, whatever.

### 2. Turn on MESSAGE CONTENT

Left sidebar → **Bot**. Scroll to **Privileged Gateway Intents**.

Turn on **MESSAGE CONTENT INTENT**. Click **Save Changes**.

> **Do not skip this one.** Without it your bot can post, and it can fetch messages, and every message it fetches comes back **blank**. Nothing tells you why. It looks exactly like broken code and it is a checkbox. It is the single most common way this setup goes wrong.

### 3. Copy the token

Same **Bot** page, near the top → **Reset Token** → confirm → **Copy**.

**The token is shown once.** If you navigate away without copying it, come back and reset it again — that's fine and costs nothing.

Paste it somewhere your agent can pick it up. It is a password: it grants anything your bot can do, so don't paste it into a chat, a ticket, or a commit.

### 4. Build the invite link

Left sidebar → **OAuth2** → **URL Generator**.

- Under **Scopes**, tick: `bot`
- Under **Bot Permissions**, tick the set your bot will actually use:

  **View Channel**, **Read Message History**, **Send Messages**, **Send Messages in Threads**, **Add Reactions**, **Embed Links**, **Attach Files**, **Use External Emoji**

This is your bot and you want it capable. Requesting the full working set is the normal thing to do — a hobbled bot that cannot react or attach a file just fails confusingly later, and it protects nobody.

What you are building here is a **request**. It is not a grant, and it is not the last word.

Copy the generated URL at the bottom.

### 5. Get it into the server

Open that URL and pick the server. If you don't have admin rights there, send the URL to whoever does.

**This is where the second party comes in, and it is worth understanding before something confuses you later.** There are two independent control points:

1. **You request** — the permissions in your invite URL, above.
2. **The server admin disposes** — they see exactly what you asked for when they approve the invite, and they can untick anything right there. Afterwards they keep controlling what your bot can do, through roles and per-channel permission overwrites.

**Discord enforces the intersection of the two.** So your bot ends up with what you asked for *and* the admin allowed — never more. If you are the admin, both hats are yours and you can move on.

**One consequence that will otherwise look like a bug.** If the channel is invite-only, joining the server is not enough — your bot will join successfully, see nothing, and report a permissions error that reads like broken code. A private channel needs the admin to add your bot to that channel specifically:

> Two things, if you don't mind:
> 1. Open this link to add my bot to the server: `<paste your invite URL>`
> 2. If **#channel-name** is private: right-click it → **Edit Channel** → **Permissions** → **Add member** → pick my bot → allow the permissions you're happy with.

Repeat part 2 for each private channel it should work in. The bot handles as many channels as it is granted.

### 6. Hand two things to your agent

- the **bot token** from step 3
- the **name of the channel** you were invited to

Your agent takes it from here — it can find the channel's ID itself.

---

## What each permission is for

Requested because a specific command uses it. Asking for a permission no command can use is just noise in the approval dialog — it isn't caution, it's clutter. If you only want a bot that reads, the first two are enough.

| Permission | Needed by | Why |
|---|---|---|
| View Channel | everything | Without it the channel is invisible; nothing works. |
| Read Message History | `read`, `threads`, `react list`, `verify` | Reading past messages. Discord separates seeing a channel from reading its history. |
| Send Messages | `post`, `verify` | Posting to a channel. |
| Send Messages in Threads | `post --channel <threadId>` | Posting inside a thread is a separate permission from posting in its parent. |
| Add Reactions | `react add` | Adding a new reaction. Removing your **own** reaction needs nothing extra. |
| Embed Links | `post` | Without it, links you post render as bare text with no preview. |
| Attach Files | `post --file` | File upload. Drop it if you never upload. |
| Use External Emoji | `react` with a custom emoji from another server | Only needed for custom emoji; plain unicode emoji work without it. |

**Not requested, because no command in this kit uses them.** This is a description of what the code does, not advice about what you should want:

| Permission | Why not |
|---|---|
| **Mention Everyone** | A deliberate choice by this kit's author, not a limitation: no command mass-pings, and every message carries `allowed_mentions: {"parse": []}` so relayed text containing `@everyone` cannot fire one either. It is your bot — if you want that behaviour, that is your call to make and you would change it here and in `cmd_post`. |
| Manage Messages | Would let it delete other people's messages and strip their reactions. It only ever removes its own reaction, which needs no such power. |
| Create Public/Private Threads | No command creates a thread. It reads and replies to threads that already exist. |
| Manage Threads | Would let it archive, rename, or delete threads. Never needed. |
| Manage Channels / Manage Webhooks / Manage Roles | Server administration. Nothing here touches it. |
| Send TTS Messages | Reads messages aloud in voice channels. No. |
| Use Application Commands | For slash commands; this kit has none. |
| Use External Stickers | No sticker support. |
| Kick / Ban / Moderate Members | Not remotely in scope for a bot that reads and posts. |
| Administrator | Bypasses every per-channel permission at once. Worth knowing as a diagnostic: a bot with Administrator can read channels you thought were restricted from it, so if you are testing whether a permission setup works, an admin bot will tell you nothing. |

## A second privileged intent, only if you list members

`users` (listing everyone in a server) needs the **SERVER MEMBERS** intent, enabled the same way as MESSAGE CONTENT in step 2.

You probably don't need it. Looking up one person by ID (`user <id>`) works without it, and the bot tells you so if you try to list without it.

## Done

Your agent now runs the steps in [README.md](README.md). When it finishes, you'll see your bot say hello in the channel.

If it reports that message bodies are coming back empty, that's step 2 — the toggle didn't save. Go back, check it's on, click **Save Changes**, and have your agent re-run its verification.
