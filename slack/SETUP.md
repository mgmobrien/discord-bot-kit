# Slack setup — the part a human has to do

**Name your bot after yourself, not after the team.** `<yourname>-bot` for the app, `<Name> Bot` for the display name — `alex-bot` / `Alex Bot`, `sam-bot` / `Sam Bot`.

This matters more than it sounds, and getting it wrong costs a rebuild: **renaming the app afterwards does not rename the bot user** — to actually change it you delete the app and create it again. The point of this kit is that **each person runs their own bot in the same channels**. A bot named after the company or the team — "Acme Bot", "Team Assistant" — claims the whole workspace: the second person to set one up has no name left, and nobody reading a channel can tell whose agent said what. In a channel with three bots, the name is the only thing distinguishing them.

---

## What you are about to do

Slack gives you **two tokens**, and they are not interchangeable:

| Token | Starts with | Acts as | You need it for |
|---|---|---|---|
| **Bot token** | `xoxb-` | the bot itself | posting, reading, reacting — almost everything |
| **User token** | `xoxp-` | *you*, the human | the few actions Slack will not let a bot do on its own |

**One install gives you both**, because [`manifest.json`](manifest.json) requests user scopes alongside the bot scopes. You do not install twice. Both tokens appear on the same page after you click Allow.

This kit uses the Slack **Web API only** — outbound calls, no daemon, no listener, no socket mode, nothing that needs a public URL or that keeps running in the background. You run a command, it makes an HTTPS request, it prints JSON, it exits.

---

## The human steps

Everything below needs a person logged into Slack in a browser. It is about ten minutes. Nothing after this section needs you.

**1. Create the app from the manifest.**

Go to <https://api.slack.com/apps> → **Create New App** → **From an app manifest**. Pick the workspace, then paste the contents of [`manifest.json`](manifest.json) from this directory.

Before pasting, change the three placeholder strings — they appear on lines you cannot miss:

- `"name": "YOURNAME Bot"` → `"Alex Bot"` — **name it after yourself, not the team** (`<yourname>-bot` / `<Name> Bot`)
- `"display_name": "YOURNAME Bot"` → the same
- `"description"` → whatever you want people to read in the app directory

The manifest carries the scope list, so you are not ticking forty checkboxes by hand. [`SCOPES.md`](SCOPES.md) explains every scope in it and why it is there — read that if you want to trim before installing, which is a reasonable thing to want.

**2. Install it to the workspace (this gives you the BOT token).**

**Install App** in the left sidebar → **Install to Workspace** → review the permission screen → **Allow**.

You land on a page showing a **Bot User OAuth Token** starting `xoxb-`. Copy it. If you are doing this for someone's agent, this is one of the two values to hand over.

> If your workspace requires admin approval for apps, this is where it stops and waits for an admin. That is normal and not a failure.

**3. Copy the USER token from the same page.**

Still on **Install App**: a **User OAuth Token** starting `xoxp-` is shown below the bot token. Copy it too.

If it is missing, the `user` block did not survive your manifest edit. Put it back and reinstall — a scope CHANGE is the one thing that genuinely requires reinstalling.

**4. Upload an icon.**

**Basic Information** → **Display Information** → App icon. Any square image; a distinct colour per person is enough. This is the single highest-value cosmetic step in the whole setup: in a channel with several bots it is what people actually read.

**5. Create a real channel, then put the bot in it.**

**If this is a new workspace, make a channel first.** A new Slack workspace starts with only its default `#all-<workspace>` channel, and that is not the one to use — create the channel the work will actually happen in, then invite the bot there. Doing external invites out of the workspace default is the shape to avoid.

In Slack, go to that channel and type:

```
/invite @alex-bot
```

**Use the real channel you actually intend it to work in, on the first try.** A bot that works perfectly in `#bot-testing` tells you nothing about `#general`: private channels need different scopes than public ones, and channel membership is per channel. Testing somewhere else and moving later means doing the diagnosis twice, and the second time you will believe the first result.

**6. (Only if you need outside people.)** To invite someone from outside the workspace, do it per email address, and only after the channel exists and the bot is in it:

- Slack → the channel → **Add people** → enter the email address
- Or hand the agent the addresses and let it use `invite` (see the README) — it calls `conversations.inviteShared`, which takes **one email per person** and requires the bot to already be a member of that channel

The two failure modes here are both silent-looking and both mean exactly what they say: `not_in_channel` (do step 5 first) and `recipients_not_specified` (you passed no email).

**7. Hand the agent three values** and stop:

- the **bot token** (`xoxb-…`)
- the **user token** (`xoxp-…`)
- the **channel name** you invited it to

---

## After that, hand off

The agent takes it from here. It will run `check` at each stage, and each stage answers one question:

```bash
python3 bot.py check                 # is the bot token real, and who is it
python3 bot.py check --user          # is the user token real, and who is it
python3 bot.py check --channel C123  # can the bot SEE that channel
python3 bot.py check --member C123   # is the bot actually IN that channel
```

The last one is the one that catches the failure Slack is quietest about.

---

## The failure that will actually get you

**Being able to see a channel is not the same as being in it.**

On Discord the classic silent failure is a missing MESSAGE CONTENT intent — messages come back blank. **Slack has no equivalent, and no privileged content intent at all.** Slack's version of the same trap is different and it catches people who have done this before:

`channels:read` lets your bot **list** a channel. `channels:history` lets it **read** one. Neither puts it **in** the channel — and for a public channel it must be a member to read history. So the bot can cheerfully list `#general`, report it exists, and then fail to read a word of it.

The symptom is `not_in_channel`. It is not a scope problem, and adding scopes will not fix it. Either invite the bot (step 5) or let it join a public channel itself with `join`.

For a **private** channel, self-joining is not possible at all — a human has to invite it, and the scopes are the `groups:*` family rather than `channels:*`.

---

## Which token does what, when something fails

| Symptom | Cause |
|---|---|
| `not_in_channel` | Bot is not a member. Invite it, or `join` for a public channel. |
| `channel_not_found` | Wrong ID, **or** a private channel the bot cannot see at all. These are indistinguishable from outside — Slack will not tell you a private channel exists. |
| `missing_scope` | The response names the scope it wanted. Add it to the manifest and **reinstall** — editing scopes does not take effect until reinstall. |
| `invalid_auth` | Token wrong, truncated, or revoked. |
| `not_allowed_token_type` | You used the bot token where the user token was needed, or the reverse. Check which one the command wants. |
| `ratelimited` | Slack returns `Retry-After`; the kit honours it. Rate limits are per method, so one slow method does not mean you are globally throttled. |

---

## Do not use a personal account token as a bot token

A `xoxp-` user token acts as **you**, with your access to every channel you are in. Wiring one into an automation that posts on its own is how a bot ends up reading channels nobody meant to give it, and posting as a human who did not write the message.

This kit uses the user token only where Slack genuinely offers no bot equivalent, and says so at each call site. If you find yourself reaching for `xoxp-` to work around a permission problem, the answer is a scope or an invite, not a bigger token.
