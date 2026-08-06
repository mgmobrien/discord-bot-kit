# The human part

**This is the only section a person has to do.** It is six steps in a browser and takes about five minutes. Everything after this is your agent's job.

You need Discord open in a browser and admin rights on the server you were invited to (or a friend there who has them — step 5 says which).

---

### 1. Create the application

Go to **https://discord.com/developers/applications** → **New Application**.

Give it a name — and since the whole point is several people's bots sharing a channel, **name it so everyone instantly knows it's yours and knows it's a bot**: `<yourname>-bot` is the convention that works (`dob-bot`, `matt-bot`, `sarah-bot`). A bot named after just yourself gets confused with you; a bot named something clever gets confused with everyone.

While you're on this screen: **upload an avatar** (the image field is right next to the name). Optional, but in a channel with several bots talking, a distinct face is worth the ten seconds — pick anything that reads as *yours*.

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

  **View Channel**, **Read Message History**, **Send Messages**, **Send Messages in Threads**, **Create Public Threads**, **Add Reactions**, **Embed Links**, **Attach Files**, **Use External Emoji**, **Send Polls**, **Pin Messages**

  (Or paste `permissions=2815059005131840` into the URL — same set.)

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

Every one of Discord's 53 permission bits is listed in **[PERMS.md](PERMS.md)** — the 11 this kit requests, with the command that uses each, and the 41 it does not, each with a reason.

That file exists so you do not have to take the invite link on trust. An admin can read it and decide, instead of guessing from a number.

## A second privileged intent, only if you list members

`users` (listing everyone in a server) needs the **SERVER MEMBERS** intent, enabled the same way as MESSAGE CONTENT in step 2.

You probably don't need it. Looking up one person by ID (`user <id>`) works without it, and the bot tells you so if you try to list without it.

## Done

Your agent now runs the steps in [README.md](README.md). When it finishes, you'll see your bot say hello in the channel.

If it reports that message bodies are coming back empty, that's step 2 — the toggle didn't save. Go back, check it's on, click **Save Changes**, and have your agent re-run its verification.
