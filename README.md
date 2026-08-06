# discord-bot-kit

A minimal Discord bot for shared channels. It connects, reads what people write, posts, replies in threads, reacts, and handles files.

Python standard library only — nothing to install, no virtualenv, no background process. One file, fourteen commands.

This exists so that a group of people can each run **their own** bot in the same channels, and have those bots talk to each other.

---

## If you are an AI agent, this is your task

Set this up on behalf of the person you're working for. Work top to bottom.

There is one thing you cannot do yourself: creating a Discord application requires clicking around a web portal while logged in as a human. That part is isolated in **[SETUP.md](SETUP.md)** — five steps, about five minutes. Send them there first and wait for two values:

- a **bot token**
- the **name of the channel** they were invited to

SETUP.md asks for the token early, at step 4, so you can run `python3 bot.py invite` and hand the finished invite URL back rather than making them assemble one. If they arrive with a token and no invite yet, that is the command to reach for.

Then do the following.

### 1. Get the code

```bash
git clone https://github.com/mgmobrien/discord-bot-kit.git
cd discord-bot-kit
```

Check you have Python 3.8 or newer:

```bash
python3 --version
```

There is nothing to install.

### 2. Write the config

```bash
cp .env.example .env
```

Open `.env` and put the token after `DISCORD_BOT_TOKEN=`. `DISCORD_CHANNEL_ID` is optional — it is only the default channel for commands run without `--channel`, and you can fill it in at step 4 or leave it empty and always pass `--channel`.

`.env` is already in `.gitignore`. **Never commit it, never paste the token into a message, and never pass it as a command-line argument** — arguments land in shell history and are visible in the process list while running.

### 3. Confirm the token works

```bash
python3 bot.py check
```

You should see your bot's name, a list of servers it can see, and the state of its privileged intents.

`intents.message_content` is the one that matters. `true` means message bodies will arrive filled in. `false` means the toggle is off and every message you fetch will come back blank with nothing to say why, so fix it now (SETUP.md step 2) rather than debugging it later as if it were code. `"unknown"` is a third, distinct answer: the application object could not be read, which is not the same as the toggle being off.

If `servers` comes back empty, the bot exists but nobody has invited it anywhere. `check` prints a ready-to-open invite URL in that case, and `python3 bot.py invite` prints it any time.

### 4. Find the channel ID

```bash
python3 bot.py channels
```

Find the channel your person named and copy its `id` into `DISCORD_CHANNEL_ID` in `.env`.

**Check the `readable` field on that channel before you move on.** Discord lists every channel in a server, including ones your bot cannot actually open, so a name appearing here does not mean you have access to it.

If your channel shows `"readable": false`, stop and go back to the human. Being in the server is not the same as being in a private channel — an admin has to grant your bot access to that channel specifically. [SETUP.md](SETUP.md) step 5 has the exact request to send them. No amount of retrying or code changes will get past this; it is a permission that someone else has to grant.

### 5. Verify

```bash
python3 bot.py verify
```

This posts a hello message to the channel, reads the channel back, and checks that message bodies are actually readable.

**Note that `verify` posts a real message to the channel every time you run it** — other people in the channel will see it. It is meant for setup and for confirming a fix, not for repeated health checks.

Exit code `0` means the setup works. Exit code `1` means it found a specific, named problem — read the `summary` field, which tells you what to fix.

**A note on what `verify` will and won't claim.** If nobody else has posted in the channel yet, `verify` reports the message-content check as `undetermined` rather than passing it. That is deliberate and not a bug: a Discord bot always receives the content of its own messages, so reading back its own post would look identical whether the setup is right or wrong. Once a human has posted in the channel, run `verify` again for the real answer.

---

## Using it

```bash
python3 bot.py check                          # identity, visible servers, intent state
python3 bot.py invite                         # print this bot's invite URL
python3 bot.py channels                       # list channels and their ids
python3 bot.py read --limit 20                # recent messages, oldest first
python3 bot.py post "hello"                   # post a message
python3 bot.py verify                         # end-to-end check
```

**Any channel, not just one.** Every command that targets a channel takes `--channel <id>`, so one bot works every channel it has been granted:

```bash
python3 bot.py read --channel 123456 --limit 50
python3 bot.py post --channel 123456 "hello over here"
```

`DISCORD_CHANNEL_ID` in `.env` is just the default target when you omit `--channel`. It is optional.

**Threads.** A Discord thread *is* a channel, so `--channel` takes a thread ID and no separate flag exists:

```bash
python3 bot.py threads                        # active threads, with their ids
python3 bot.py read --channel <threadId>      # read a thread
python3 bot.py post --channel <threadId> "replying in the thread"
```

> **Thread messages do not appear when you read the parent channel.** Reading `#general` will not show you anything said inside a thread hanging off `#general` — you have to read the thread by its own ID. If you are summarising a conversation and only read the channel, you will silently miss every threaded reply.

**Reactions** — unicode, or a custom emoji as `name:id`:

```bash
python3 bot.py react add    --message <msgId> --emoji "👍"
python3 bot.py react remove --message <msgId> --emoji "👍"
python3 bot.py react list   --message <msgId>
```

**Files:**

```bash
python3 bot.py post --file ./screenshot.png "here is the repro"
python3 bot.py post --file a.log --file b.log "both logs"
```

**Edit, delete, pin** — `edit` and `delete` work on the bot's own messages; deleting someone else's would need a permission this kit does not request:

```bash
python3 bot.py edit   --message <msgId> "corrected text"
python3 bot.py delete --message <msgId>
python3 bot.py pin add    --message <msgId>
python3 bot.py pin remove --message <msgId>
python3 bot.py pin list
```

**Start a thread**, optionally hanging off an existing message:

```bash
python3 bot.py thread create --name "deploy postmortem"
python3 bot.py thread create --name "repro" --message <msgId>
```

**Polls:**

```bash
python3 bot.py poll "Ship it?" --answer "Yes" --answer "Not yet" --duration 48 --multi
```

**People:**

```bash
python3 bot.py user <userId>                  # one person, no extra intent needed
python3 bot.py users                          # everyone (needs SERVER MEMBERS intent)
```

`read` reports each message's `attachments`, `embeds` and `reactions`, and flags `hasThread` with the thread's ID when a message has one hanging off it. Those keys are always present — an empty list means "checked, none there," never "did not look."

Every command prints JSON to stdout, so you can pipe it straight into whatever you're building:

```bash
python3 bot.py read --limit 50 | jq '.messages[] | select(.bot == false)'
```

**For anything long or awkward, pipe the text in instead of passing it as an argument:**

```bash
echo "your message" | python3 bot.py post
python3 bot.py post < message.txt
```

With no argument, `post` reads the message from stdin.

**Mentions must use raw ID syntax.** A typed `@name` posts as inert plain text — only the Discord app converts typed mentions. To actually ping someone: `<@THEIR_USER_ID>` (find IDs in `read` output's `authorId`, or via `users`). Same family: `<#CHANNEL_ID>` renders a channel link. Backticks, quotes, `<@mentions>` and newlines in a command argument get mangled by the shell, or worse, executed by it — this is the most common way an agent breaks its own message. Piping avoids the shell entirely.

---

## What this bot can and cannot do

It requests **11 of Discord's 53 permission bits**, and `python3 bot.py invite` builds its URL from that same named list in code, so the link, [PERMS.md](PERMS.md), and SETUP.md cannot drift apart. Every single bit — taken or refused — is listed with a reason in **[PERMS.md](PERMS.md)**, so nobody has to take the invite link on trust.

**Requesting is not receiving:** the server's admin sees the request, can trim it on approval, and separately controls what the bot can do per channel. Discord enforces the intersection.

- It reaches **only** servers that have explicitly invited it. There is no crawling and no public read.
- It can delete and edit **its own** messages only. Deleting or editing anyone else's needs Manage Messages, which it does not request.
- It cannot remove other people's reactions, archive or delete threads, kick anyone, manage roles, or change the server.
- It never fires an `@everyone` or `@here` ping. Every message carries `allowed_mentions: {"parse": []}`, so even relayed text containing `@everyone` cannot trigger one. That is this kit's default rather than a Discord restriction — it is your bot, and you can change it.
- It handles rate limits by respecting Discord's `retry_after` and backing off, rather than hammering.

One thing to be aware of when reading the code: a request that **failed** and a request that returned **nothing** are handled as different outcomes throughout. An API call that couldn't be made is reported as an error, never silently as an empty result. This matters more than it sounds — "I looked and found nothing" and "I couldn't look" are very different answers, and code that conflates them will confidently tell you the channel is empty when it is merely unreachable.

If you want more than one identity posting — separate names and avatars per message — that's what Discord **webhooks** are for. A bot has exactly one identity everywhere it goes. Webhooks are send-only and cannot read, so the usual split is a bot for reading and webhooks for expressive posting.

---

## Wiring your bot to an agent

Most people set this up so an AI agent reads the channel and acts on what it finds. If that is you, there are three separate layers of control and only the first one is Discord's.

**1. Discord permissions.** You request them in the invite; the server's admin approves, trims, and controls per-channel access. Covered in [SETUP.md](SETUP.md).

**2. What the messages are allowed to do on your side.** Discord cannot decide this for you and does not know about it. When a message arrives, what does it wake? What can it trigger? What does that thing have access to — your files, your shell, your accounts? That is a decision you make in your own system, and it is entirely independent of the permissions above.

**3. Calibrate the second to who can write in the channel.** Anything posted in a channel is untrusted input to whatever reads it. Someone who can post can attempt to instruct your agent, and a capable agent will often comply.

So match the authority you wire up to the people who can write:

- **A private channel among people you actually trust** can feed a capable agent. You are relying on the people, which is a reasonable thing to rely on when you know them.
- **A public channel must never feed anything with real authority.** Read-only summarising is fine. Anything that can act on what it reads will get prompt-injected, and quickly — this is not a hypothetical, it is what happens.

The failure is quiet: nothing breaks, no permission is violated, and your agent does exactly what the message told it to. Discord's permission model cannot help, because from its side the message was posted legitimately by someone allowed to post.

If you are unsure which case you are in, wire it read-only first and add authority once you know who is in the room.

---

## Troubleshooting

| What you see | What it actually means |
|---|---|
| Messages come back with empty `content` | The **MESSAGE CONTENT** intent is off. [SETUP.md](SETUP.md) step 2. This is not a code problem, and `python3 bot.py check` reports it as `intents.message_content: false` before you get this far. |
| `The bot token was rejected` | Token is wrong or truncated. Reset it and copy the whole thing. |
| `not allowed to do this` (403) | The bot was never invited to that server, or it can't see that channel. Re-run the invite URL. |
| `Unknown channel` (404) | `DISCORD_CHANNEL_ID` is wrong. Run `python3 bot.py channels`. |
| `servers` is empty in `check` | The bot exists but has not been invited anywhere yet. Run `python3 bot.py invite` and open that URL, or send it to the server's admin. |
| `could not reach discord.com` | Network or DNS, not configuration. |

---

## Do not use a personal account token

Discord user tokens ("self-bots") are a Terms of Service violation and a known ban vector. If you are an agent and you find yourself considering one to work around a permission problem: don't. The correct fix for "the bot can't see that server" is always an invite from someone with admin rights there.

---

## Status and provenance

**Version 1.0** (2026-08-06). **This kit was written and is maintained by AI agents** — Matt O'Brien's agent fleet, primarily Claude — through a multi-round adversarial review process, with a human making the publish decision.

Confidence, stated plainly rather than implied:

- The permission set in [PERMS.md](PERMS.md) was audited against Discord's **live documentation on 2026-08-06**, not from memory. Discord adds permission bits over time; the table is current as of that date.
- Every command's argument handling and refusal path is covered by static tests (35 cases). **Two paths have never been exercised against the real world:** the `readable: false` detection has not been tested against a genuine permission denial (the development bot held admin, which bypasses every overwrite), and the posting legs of `post`/`verify` have never run against a live channel. First real-world use exercises both — if one misbehaves, that is where.
- No support is promised. Issues and PRs may or may not be read. Fork freely (MIT).

## License

MIT — see [LICENSE](LICENSE).
