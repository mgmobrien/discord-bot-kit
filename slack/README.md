# slack/

A minimal Slack bot for shared channels, in the same shape as [`discord/`](../discord/): Python standard library only, Web API outbound calls only, no daemon, no listener, no socket mode, nothing needing a public URL.

**Read the [root README](../README.md) first** for the agent contract, the JSON/stdout and failed-call-vs-empty-result rules, and the section on calibrating agent authority to who can post. This file covers only what is specific to Slack.

---

## ⚠ Status: docs are here, `bot.py` is not yet

**This directory currently contains the setup path and the scope documentation. It does not yet contain `bot.py`.**

Said plainly because [`SETUP.md`](SETUP.md) ends by telling a human to hand three values to an agent, and [`SCOPES.md`](SCOPES.md) maps scopes to commands that do not exist here yet. If you are following those docs end to end today, **you will complete every human step and then have nothing to run.** That is a real dead end and you should know about it before you start rather than after.

What is usable right now:

- **[SETUP.md](SETUP.md)** — the app creation, two-token two-install sequence, icon, channel invite, and the external-invite recipe. All of it is independent of the client, so a workspace set up today is set up correctly for the client when it lands.
- **[SCOPES.md](SCOPES.md)** — every scope in the manifest justified, and the notable refusals with reasons. Read this before installing if you want to trim.
- **[manifest.json](manifest.json)** — paste-ready after changing three `YOURNAME` placeholders.

`bot.py` follows in a second change, and it will be exercised against a real workspace before it is described as working. The Discord side of this kit carries an explicit note that two of its paths have never run against the real service; the point of holding this one back is to not add a third.

---

## What the commands will be

The verb set mirrors `discord/` where Slack supports the same thing, with three deliberate differences:

**`check` takes a stage**, because Slack's failures are staged and each one has a different fix:

```bash
python3 bot.py check                 # is the bot token real, and who is it
python3 bot.py check --user          # is the user token real, and who is it
python3 bot.py check --channel C123  # can the bot SEE that channel
python3 bot.py check --member C123   # is the bot actually IN that channel
```

The last is the one that matters most, and it is the one Slack is quietest about. See SETUP.md.

**Threads are not channels.** On Discord a thread *is* a channel and `--channel` takes a thread ID. Slack threads are a `thread_ts` on a parent channel, so they need their own parameter:

```bash
python3 bot.py read  --channel C123 --thread 1699999999.000100
python3 bot.py reply --channel C123 --thread 1699999999.000100 "in-thread"
```

Code written against the Discord model does not port here, and this is the difference most likely to produce a confident wrong answer.

**There is no `poll`.** Discord has a native poll object; Slack does not. A Slack poll is Block Kit elements plus interaction handling, which needs a request endpoint this kit deliberately does not have. Adding it would mean giving up the no-daemon property, so it is omitted rather than half-built.

**`post --as`** uses `chat:write.customize` for a per-message name and icon — the thing Discord needs webhooks for.

---

## The Slack-specific trap, stated once more because it is the one that gets people

Being able to **see** a channel is not the same as being **in** it. `channels:read` lists, `channels:history` permits reading, and neither puts the bot in the channel — which it must be, to read a word. The symptom is `not_in_channel`, no scope fixes it, and a private channel that the bot cannot see is indistinguishable from one that does not exist.

Discord's famous silent failure — the MESSAGE CONTENT intent making every message come back blank — has **no Slack equivalent**. Do not go looking for it.
