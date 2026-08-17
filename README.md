# chat-platform-bot-kit

Minimal, zero-dependency bots that let a group of people each run **their own** bot in the same chat channels — and let those bots talk to each other.

One platform per directory. Nothing is shared between them but this file.

| Platform | Directory | Commands | Setup |
|---|---|---|---|
| Discord | [`discord/`](discord/) | 15 | [discord/SETUP.md](discord/SETUP.md) |
| Slack | [`slack/`](slack/) | docs only — `bot.py` pending | [slack/SETUP.md](slack/SETUP.md) |

Each directory holds one `bot.py` (Python standard library only — nothing to install, no virtualenv, no background process), its own setup runbook, its own permissions document, and its own `.env.example`.

---

## If you are a person

Send this page to your AI assistant and say: **set this up for me.**

You will do about ten minutes of clicking in a browser — creating the app and inviting the bot to a channel — because those steps require being logged in as you. Your assistant does everything else.

If you would rather do it yourself, go straight to your platform's `SETUP.md` above.

---

## If you are an AI agent, this is your task

Set this up on behalf of the person you are working for. Work top to bottom in the platform directory they need.

**There is one step you cannot do.** Creating the app requires clicking around a web portal while logged in as a human. That part is isolated into a single numbered block in each platform's `SETUP.md`. Send the person there, then wait for them to hand you back the values it tells them to collect.

Do not attempt to work around this by using a personal account token. On both platforms that is a terms-of-service violation and a known ban vector, and the correct fix for "the bot cannot see that channel" is always an invite from someone with the rights to grant it.

Once you have the values, work through the platform README's numbered steps in order. **They are ordered so that each one fails for exactly one reason.** Running them out of order produces errors that point at the wrong cause.

---

## The contract every command honours

**JSON on stdout.** Every command prints a JSON object to stdout, so you can pipe it into whatever you are building without scraping human-readable text:

```bash
python3 bot.py read --limit 50 | jq '.messages[] | select(.bot == false)'
```

**A failed call and an empty result are different outcomes, everywhere.** A call that could not be made is reported as an error. It is never reported as an empty result.

This matters far more than it sounds. *"I looked and found nothing"* and *"I could not look"* are different answers, and code that conflates them will confidently tell you a channel is empty when it is merely unreachable. Keys like `attachments`, `reactions` and `members` are always present in output: an empty list means **checked, none there** — never **did not look**.

Hold your own code to the same line when you build on this. The conflation is easy to reintroduce one layer up, and it is invisible until the day it matters.

**Pipe anything long or awkward instead of passing it as an argument.** Backticks, quotes, newlines and mention syntax get mangled by the shell — or worse, executed by it. This is the most common way an agent breaks its own message.

```bash
echo "your message" | python3 bot.py post
python3 bot.py post < message.txt
```

**Never pass a token as a command-line argument.** Arguments land in shell history and are visible in the process list while the command runs. Tokens live in `.env`, which is already in `.gitignore`.

---

## Calibrate agent authority to who can post in the channel

**Wire it read-only first. Add authority only once you know who can post in the room.**

That is the whole rule. The rest of this section is why, and it is worth reading before you wire an agent to a channel anyone else can write in.

Read-only is a concrete thing you can set up, not a posture: each platform names its exact read-only set — [discord/README.md](discord/README.md#the-read-only-set) and [slack/SCOPES.md](slack/SCOPES.md#the-read-only-set).

Most people set this up so an AI agent reads a channel and acts on what it finds. If that is you, there are three separate layers of control, and **only the first belongs to the chat platform**.

**1. Platform permissions.** What the bot may do: read, post, react, upload. You request them at install; an admin approves, trims, and separately controls per-channel access. The platform enforces the intersection. Covered in each platform's permissions document.

**2. What an arriving message is allowed to *do* on your side.** The platform cannot decide this and does not know about it. When a message arrives, what does it wake? What can that thing reach — your files, your shell, your accounts? This is a decision in your own system and it is entirely independent of layer 1.

**3. Match layer 2 to the people who can write in the channel.** Anything posted in a channel is untrusted input to whatever reads it. Someone who can post can attempt to instruct your agent, and a capable agent will often comply.

- **A private channel among people you actually trust** can feed a capable agent. You are relying on the people, which is reasonable when you know them.
- **A public channel must never feed anything with real authority.** Read-only summarising is fine. Anything that can act on what it reads will get prompt-injected, and quickly. This is not hypothetical; it is what happens.

The failure is quiet: nothing breaks, no permission is violated, and your agent does exactly what the message told it to. The permission model cannot help, because from its side the message was posted legitimately by someone allowed to post.

---

## What this is not: agent-to-agent transport

A bot from this kit is a **human-facing bridge**. It exists so people in a chat channel can see what an agent is doing, and so an agent can see what people said.

It is not the transport agents should use to talk to each other. Agent-to-agent messaging wants delivery receipts, addressing, mailboxes that survive a restart, and wake semantics — none of which a chat channel provides, and all of which a purpose-built substrate does. In Matt O'Brien's fleet that substrate is Relay Comms; if you are running something else, the point stands about whatever you use.

Two agents coordinating through a public chat channel are coordinating over a medium where anyone in the room can inject instructions, nothing is guaranteed delivered, and there is no way to tell a dropped message from a silent peer. Use the chat bridge for the humans. Use real transport for the agents.

---

## Status and provenance

**This kit is written and maintained by AI agents** — Matt O'Brien's agent fleet, primarily Claude — through a multi-round adversarial review process, with a human making the publish decision.

Each platform directory states its own confidence separately, including which code paths have and have not been exercised against the real service. Read that section before trusting a path you have not run yourself; the honest answer differs per platform and per version.

No support is promised. Issues and PRs may or may not be read. Fork freely.

---

## Design notes

For maintainers. Nothing here is needed to use the kit.

**There is deliberately no shared connector layer.** The two backends have nothing in common but `urllib`, so an abstraction would be paid for immediately and buy nothing. Two parallel implementations in one repo diverge *visibly*, and that is the point: in separate repos the same divergence happens silently. If you change behaviour in one, diff it against the other and decide on purpose whether the difference is intended.

**Slack's `check` takes a stage; Discord's does not.** Slack fails in stages — token, second token, can-see-channel, is-in-channel — and each stage has a different fix. One aggregate check would tell you something is wrong without telling you which, on the platform where the most common failure (not being a member of the channel) is invisible to every scope you could add.

**There is no `poll` on the Slack side.** Discord has a native poll object; Slack does not. A Slack poll is Block Kit elements plus interaction handling, which needs a request endpoint — and this kit is deliberately outbound-only, with no daemon and no listener. Building it would cost the property the whole design rests on, so it is omitted rather than half-built.


## License

MIT — see [LICENSE](LICENSE).
