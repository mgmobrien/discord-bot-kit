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
- Under **Bot Permissions**, tick **nothing at all**.

That is not a mistake. Leave the permissions empty and you get an invite URL ending in `permissions=0`.

Ticking permissions here grants them **across the whole server** — every channel your bot can see, not just the one you care about. Since you only want one channel, it's both safer and simpler to grant nothing at the server level and grant access to that single channel in step 5. Your bot ends up able to see exactly one channel and nothing else.

Copy the generated URL at the bottom.

### 5. Get invited to the channel

Open that URL and pick the server. If you don't have admin rights there, send the URL to whoever does.

**Then there is a second ask, and this is the step that quietly breaks everything if it's missed.** An invite-only channel is invisible to your bot even after it has joined the server. Being in the server is not access to a private channel. Your bot will join successfully, see nothing, and report a permissions error that looks like a bug in the code.

So send the admin both parts:

> Two things, if you don't mind:
> 1. Open this link to add my bot to the server: `<paste your invite URL>`
> 2. Then right-click the **#channel-name** channel → **Edit Channel** → **Permissions** → **Add member** → pick my bot → allow **View Channel**, **Send Messages**, and **Read Message History**.
>
> That gives it access to that one channel only.

If you're the admin yourself, do part 2 in the Discord app — it takes about fifteen seconds.

### 6. Hand two things to your agent

- the **bot token** from step 3
- the **name of the channel** you were invited to

Your agent takes it from here — it can find the channel's ID itself.

---

## Done

Your agent now runs the steps in [README.md](README.md). When it finishes, you'll see your bot say hello in the channel.

If it reports that message bodies are coming back empty, that's step 2 — the toggle didn't save. Go back, check it's on, click **Save Changes**, and have your agent re-run its verification.
