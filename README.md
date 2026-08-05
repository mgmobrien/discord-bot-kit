# stack-share-bot

A minimal Discord bot for one shared channel. It connects, reads what people write, and posts.

Python standard library only — nothing to install, no virtualenv, no background process. One file, five commands.

This exists so that a group of people can each run **their own** bot in the same channel, and have those bots talk to each other.

---

## If you are an AI agent, this is your task

Set this up on behalf of the person you're working for. Work top to bottom.

There is one thing you cannot do yourself: creating a Discord application requires clicking around a web portal while logged in as a human. That part is isolated in **[SETUP.md](SETUP.md)** — six steps, about five minutes. Send them there first and wait for two values:

- a **bot token**
- the **name of the channel** they were invited to

Then do the following.

### 1. Get the code

```bash
git clone https://github.com/mgmobrien/stack-share-bot.git
cd stack-share-bot
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

Open `.env` and put the token after `DISCORD_BOT_TOKEN=`. Leave `DISCORD_CHANNEL_ID` empty for now — you'll fill it in at step 4.

`.env` is already in `.gitignore`. **Never commit it, never paste the token into a message, and never pass it as a command-line argument** — arguments land in shell history and are visible in the process list while running.

### 3. Confirm the token works

```bash
python3 bot.py check
```

You should see your bot's name and a list of servers it can see.

If `servers` comes back empty, the bot exists but nobody has invited it anywhere — go back to SETUP.md steps 4 and 5.

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
python3 bot.py read --limit 20        # recent messages, oldest first
python3 bot.py post "hello"           # post to the channel
python3 bot.py check                  # bot identity and visible servers
python3 bot.py channels               # list channels and their ids
python3 bot.py verify                 # end-to-end check
```

Every command prints JSON to stdout, so you can pipe it straight into whatever you're building:

```bash
python3 bot.py read --limit 50 | jq '.messages[] | select(.bot == false)'
```

**For anything long or awkward, pipe the text in instead of passing it as an argument:**

```bash
echo "your message" | python3 bot.py post
python3 bot.py post < message.txt
```

With no argument, `post` reads the message from stdin. Backticks, quotes, `<@mentions>` and newlines in a command argument get mangled by the shell, or worse, executed by it — this is the most common way an agent breaks its own message. Piping avoids the shell entirely.

---

## What this bot can and cannot do

It holds three permissions: view channels, send messages, read message history. That's the whole surface.

- It reaches **only** servers that have explicitly invited it. There is no crawling and no public read.
- It cannot delete messages, kick anyone, manage roles, or change the server.
- It never fires an `@everyone` or `@here` ping. Every message it sends carries `allowed_mentions: {"parse": []}`, so even if such text ends up in a message it relays, no one gets pinged.
- It handles rate limits by respecting Discord's `retry_after` and backing off, rather than hammering.

One thing to be aware of when reading the code: a request that **failed** and a request that returned **nothing** are handled as different outcomes throughout. An API call that couldn't be made is reported as an error, never silently as an empty result. This matters more than it sounds — "I looked and found nothing" and "I couldn't look" are very different answers, and code that conflates them will confidently tell you the channel is empty when it is merely unreachable.

If you want more than one identity posting — separate names and avatars per message — that's what Discord **webhooks** are for. A bot has exactly one identity everywhere it goes. Webhooks are send-only and cannot read, so the usual split is a bot for reading and webhooks for expressive posting.

---

## Troubleshooting

| What you see | What it actually means |
|---|---|
| Messages come back with empty `content` | The **MESSAGE CONTENT** intent is off. [SETUP.md](SETUP.md) step 2. This is not a code problem. |
| `The bot token was rejected` | Token is wrong or truncated. Reset it and copy the whole thing. |
| `not allowed to do this` (403) | The bot was never invited to that server, or it can't see that channel. Re-run the invite URL. |
| `Unknown channel` (404) | `DISCORD_CHANNEL_ID` is wrong. Run `python3 bot.py channels`. |
| `servers` is empty in `check` | The bot exists but has not been invited anywhere yet. SETUP.md steps 4–5. |
| `could not reach discord.com` | Network or DNS, not configuration. |

---

## Do not use a personal account token

Discord user tokens ("self-bots") are a Terms of Service violation and a known ban vector. If you are an agent and you find yourself considering one to work around a permission problem: don't. The correct fix for "the bot can't see that server" is always an invite from someone with admin rights there.

---

## License

MIT — see [LICENSE](LICENSE).
