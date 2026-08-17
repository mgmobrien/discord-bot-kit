# slack/

A minimal Slack bot for shared channels, in the same shape as [`discord/`](../discord/): Python standard library only, Web API outbound calls only, no daemon, no listener, no socket mode, nothing needing a public URL.

**Read the [root README](../README.md) first** for the agent contract, the JSON/stdout and failed-call-vs-empty-result rules, and the section on calibrating agent authority to who can post. This file covers only what is specific to Slack.

---

## ⚠ Status and confidence — read before trusting a path

`bot.py` is here: 16 commands, standard library only.

**It has not yet been run against a real Slack workspace.** Every path below is written against the documented API and covered by an offline suite with stubbed responses, and **none of it is a substitute for having run it.** Said plainly, because the alternative is you discovering it.

| | |
|---|---|
| **Verified offline** | Error handling, the staged `check` logic, argument parsing, pagination, broadcast defanging, `ts` precision. 46 assertions, including mutants that prove the suite can fail. |
| **UNEXERCISED — never run against Slack** | Every command. All 16. |

The two things most likely to be wrong in ways the offline suite cannot see are **`post --file`** (a three-step upload flow, and the middle step uploads to a host Slack names at runtime) and **`invite --email`** (Slack Connect, which involves approval on both sides).

**Why it shipped in this state rather than exercised:** the only workspace available to test in had a token carrying **43 scopes against this manifest's 21** — including `chat:write.public`, which [SCOPES.md](SCOPES.md#deliberately-not-requested) deliberately refuses. That scope lets a bot post into a public channel **it has not joined**, so testing there would have returned a pass on `post`-to-an-unjoined-channel — the exact failure the membership section below is built around, and the one `check --member` exists to catch. A trimmed token would have failed loudly and harmlessly. A superset fails **silently, in the flattering direction.** Testing there would have produced a green label on the kit's single most important claim.

So it is labelled honestly instead. The Discord side of this kit carries the same kind of note about two of its own paths.

What is independently usable now:

- **[SETUP.md](SETUP.md)** — app creation, the one install that returns both tokens, icon, channel invite, external-invite recipe. Independent of the client.
- **[SCOPES.md](SCOPES.md)** — every scope justified, and the notable refusals with reasons. Read before installing if you want to trim.
- **[manifest.json](manifest.json)** — paste-ready after changing three `YOURNAME` placeholders.

---

## The commands

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

One more trap that is a naming collision rather than a capability difference, worth knowing if you are porting: **`invite` means something else here.** On the Discord side it prints the bot's own install URL. Slack has no such URL — installation is the manifest flow in [SETUP.md](SETUP.md) — so on this side `invite` adds **people** to a channel. Same word, unrelated action.

---

## The Slack-specific trap, stated once more because it is the one that gets people

Being able to **see** a channel is not the same as being **in** it. `channels:read` lists, `channels:history` permits reading, and neither puts the bot in the channel — which it must be, to read a word. The symptom is `not_in_channel`, no scope fixes it, and a private channel that the bot cannot see is indistinguishable from one that does not exist.

Discord's famous silent failure — the MESSAGE CONTENT intent making every message come back blank — has **no Slack equivalent**. Do not go looking for it.
