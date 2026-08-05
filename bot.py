#!/usr/bin/env python3
"""
Minimal Discord bot for a single shared channel.

Standard library only — no pip install, no virtualenv, no gateway websocket.
Every command makes plain HTTPS calls to discord.com/api/v10 and prints JSON.

Usage:
    python3 bot.py check                 # who am I, which servers can I see
    python3 bot.py channels              # list channels, to find your channel id
    python3 bot.py read [--limit N]      # read recent messages
    python3 bot.py post "your message"   # post a message
    python3 bot.py verify                # end-to-end check, diagnoses the common traps

Configuration comes from a .env file next to this script, or from real
environment variables (which win). See .env.example.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://discord.com/api/v10"
UA = "stack-share-bot (https://github.com/mgmobrien/stack-share-bot, 1.0)"


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

def load_env():
    """Read .env next to this script. Real environment variables take priority."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    values = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                values[key.strip()] = val
    for key in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def need(values, key, hint):
    val = values.get(key)
    if not val:
        die(f"{key} is not set. {hint}")
    return val


def die(message, code=2):
    print(json.dumps({"ok": False, "error": message}, indent=2))
    sys.exit(code)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def call(method, path, token, body=None, params=None):
    """
    One Discord API call.

    Returns (status, parsed_json).

    Raises RuntimeError on transport failure. That distinction matters: a call
    that could not be made is NOT the same as a call that returned nothing, and
    the callers below are careful never to treat the first as the second.
    """
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("User-Agent", UA)
    if data is not None:
        req.add_header("Content-Type", "application/json")

    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = {"raw": raw}

            # Rate limited. Discord tells us how long to wait; respect it.
            if err.code == 429 and attempt < 4:
                wait = 1.0
                if isinstance(parsed, dict) and parsed.get("retry_after"):
                    wait = float(parsed["retry_after"]) + 0.25
                time.sleep(min(wait, 30))
                continue
            return err.code, parsed
        except urllib.error.URLError as err:
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"could not reach discord.com: {err.reason}") from err

    raise RuntimeError("gave up after repeated rate limiting")


def explain(status, payload):
    """Turn a Discord error into something a human or an agent can act on."""
    code = payload.get("code") if isinstance(payload, dict) else None
    if status == 401:
        return ("The bot token was rejected. Check DISCORD_BOT_TOKEN in .env — "
                "copy it again from the Developer Portal (Bot -> Reset Token). "
                "The token is shown only once, so a partial copy is common.")
    if status == 403:
        return ("The bot is authenticated but not allowed to read this channel. "
                "If the channel is private — which is normal for an invite-only one — "
                "being in the server is not enough on its own: an admin has to grant "
                "your bot access to that specific channel. Ask them for the wording in "
                "SETUP.md step 5. This is a permissions setting, not a problem with the "
                "token or this code.")
    if status == 404 and code == 10003:
        return ("Unknown channel. DISCORD_CHANNEL_ID is wrong, or the bot is not in "
                "the server that owns it. Run: python3 bot.py channels")
    if status == 404:
        return "Not found. Check DISCORD_CHANNEL_ID — run: python3 bot.py channels"
    msg = payload.get("message") if isinstance(payload, dict) else None
    return f"Discord returned HTTP {status}" + (f": {msg}" if msg else "")


def ok(status):
    return 200 <= status < 300


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_check(values):
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")

    status, me = call("GET", "/users/@me", token)
    if not ok(status):
        die(explain(status, me))

    status, guilds = call("GET", "/users/@me/guilds", token)
    if not ok(status):
        die(explain(status, guilds))

    print(json.dumps({
        "ok": True,
        "bot": {"username": me.get("username"), "id": me.get("id")},
        "servers": [{"name": g.get("name"), "id": g.get("id")} for g in (guilds or [])],
        "note": ("If 'servers' is empty the bot exists but has not been invited "
                 "anywhere yet. Open the invite URL from SETUP.md step 4."),
    }, indent=2))


def cmd_channels(values):
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")

    status, guilds = call("GET", "/users/@me/guilds", token)
    if not ok(status):
        die(explain(status, guilds))
    if not guilds:
        die("The bot is not in any server yet. Open the invite URL from SETUP.md step 4.")

    # Listing a channel is NOT the same as being able to read it. Discord returns
    # every channel in the server here, including ones this bot has no access to.
    # Copying an id from a bare list is therefore a trap: the next command fails
    # with a 403 and nothing explains why. So each channel is probed, and the
    # answer reported per channel.
    out = []
    blocked_any = False
    for g in guilds:
        status, chans = call("GET", f"/guilds/{g['id']}/channels", token)
        if not ok(status):
            out.append({"server": g.get("name"), "error": explain(status, chans)})
            continue

        listed = []
        candidates = [c for c in (chans or []) if c.get("type") in (0, 5)]
        for index, c in enumerate(candidates, 1):
            # Progress goes to stderr so stdout stays clean JSON for piping.
            print(f"  checking {index}/{len(candidates)}: {c.get('name')}", file=sys.stderr)
            probe, _ = call("GET", f"/channels/{c['id']}/messages", token, params={"limit": 1})
            readable = ok(probe)
            if not readable:
                blocked_any = True
            listed.append({
                "name": c.get("name"),
                "id": c.get("id"),
                "readable": readable,
            })
        out.append({"server": g.get("name"), "channels": listed})

    note = "Copy the id of the channel you were invited to into DISCORD_CHANNEL_ID in .env."
    if blocked_any:
        note += (" Channels marked readable:false are visible by name but this bot cannot "
                 "read them. If the one you want is among them, being in the server is not "
                 "enough — an admin has to grant your bot access to that channel "
                 "specifically. SETUP.md step 5 has the exact wording to send them.")

    print(json.dumps({"ok": True, "servers": out, "note": note}, indent=2))


def fetch_messages(token, channel_id, limit):
    status, msgs = call("GET", f"/channels/{channel_id}/messages", token,
                        params={"limit": max(1, min(int(limit), 100))})
    if not ok(status):
        die(explain(status, msgs))
    return msgs or []


def cmd_read(values, limit):
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = need(values, "DISCORD_CHANNEL_ID", "Run: python3 bot.py channels")

    msgs = fetch_messages(token, channel, limit)
    print(json.dumps({
        "ok": True,
        "count": len(msgs),
        "messages": [
            {
                "id": m.get("id"),
                "author": (m.get("author") or {}).get("username"),
                "bot": bool((m.get("author") or {}).get("bot")),
                "timestamp": m.get("timestamp"),
                "content": m.get("content"),
            }
            for m in reversed(msgs)
        ],
    }, indent=2))


def read_message_text(args):
    """Message text from an argument, or from stdin when no argument is given.

    Stdin exists so long or awkward messages never have to survive a trip
    through the shell: backticks, quotes and newlines in a command argument get
    mangled or executed. `bot.py post < note.txt` and `... | bot.py post` both
    land here.

    If there is no argument AND stdin is a terminal, there is nothing to read
    and waiting would look like a hang, so that case refuses immediately.
    """
    if len(args) >= 2 and args[1].strip():
        return args[1]
    if len(args) >= 2 and not args[1].strip():
        return ""  # explicit empty argument -> caller refuses
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def cmd_post(values, text):
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = need(values, "DISCORD_CHANNEL_ID", "Run: python3 bot.py channels")

    # allowed_mentions parse:[] means this bot can never fire an @everyone or
    # @here ping, even if such text ends up in a message it relays.
    status, msg = call("POST", f"/channels/{channel}/messages", token,
                       body={"content": text, "allowed_mentions": {"parse": []}})
    if not ok(status):
        die(explain(status, msg))

    print(json.dumps({"ok": True, "posted": {"id": msg.get("id"), "content": msg.get("content")}}, indent=2))


def cmd_verify(values):
    """
    End-to-end check: post a message, read the channel back, and diagnose the
    two failures that look like broken code but are actually setup mistakes.
    """
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = need(values, "DISCORD_CHANNEL_ID", "Run: python3 bot.py channels")

    steps = []

    status, me = call("GET", "/users/@me", token)
    if not ok(status):
        die(explain(status, me))
    steps.append({"step": "authenticate", "ok": True, "bot": me.get("username")})

    marker = f"stack-share bot online — {me.get('username')} reporting in."
    status, posted = call("POST", f"/channels/{channel}/messages", token,
                          body={"content": marker, "allowed_mentions": {"parse": []}})
    if not ok(status):
        die(explain(status, posted))
    steps.append({"step": "post", "ok": True, "message_id": posted.get("id")})

    msgs = fetch_messages(token, channel, 50)
    steps.append({"step": "read", "ok": True, "messages_seen": len(msgs)})

    # --- the MESSAGE CONTENT intent check -----------------------------------
    #
    # Without the MESSAGE CONTENT privileged intent, Discord blanks the
    # `content` field -- over plain HTTP too, not just the gateway. Message
    # bodies come back as empty strings and nothing announces why.
    #
    # The check has to be done carefully. A bot ALWAYS receives content for
    # messages it wrote itself, so reading back our own post proves nothing:
    # it would pass with the intent switched off. The only honest discriminator
    # is a message written by SOMEBODY ELSE that has no content, no attachment
    # and no embed -- a message with nothing in it at all, which is not a thing
    # a person sends.
    #
    # And if nobody else has posted in this channel yet, there is nothing to
    # discriminate with. In that case this check reports "undetermined". It
    # does not report success. A check that cannot see must not say yes.

    others = [m for m in msgs if not (m.get("author") or {}).get("bot")
              and (m.get("author") or {}).get("id") != me.get("id")]

    if not others:
        intent = {
            "status": "undetermined",
            "detail": ("No messages from anyone else in this channel yet, so the "
                       "MESSAGE CONTENT intent could not be tested. Reading back this "
                       "bot's own message proves nothing — a bot always sees its own "
                       "content. Once a human has posted here, run verify again."),
        }
    elif all((m.get("content") or "") == "" and not m.get("attachments") and not m.get("embeds")
             for m in others):
        intent = {
            "status": "FAILED",
            "detail": ("Every message from other people came back completely empty. "
                       "That is the signature of the MESSAGE CONTENT privileged intent "
                       "being switched off. Fix it in the Developer Portal: your "
                       "application -> Bot -> Privileged Gateway Intents -> turn on "
                       "MESSAGE CONTENT -> Save. Then run verify again. "
                       "Nothing is wrong with this code."),
        }
    else:
        intent = {
            "status": "ok",
            "detail": "Message bodies from other authors are readable.",
        }

    steps.append({"step": "message_content_intent", **intent})

    healthy = intent["status"] != "FAILED"
    print(json.dumps({
        "ok": healthy,
        "steps": steps,
        "summary": (
            "Setup is working. The bot posted to the channel and read it back."
            if healthy else
            "The bot can post, but it cannot read what other people write. See the "
            "message_content_intent step above — it is a setting, not a bug."
        ),
    }, indent=2))
    sys.exit(0 if healthy else 1)


# --------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return

    values = load_env()
    command = args[0]

    try:
        if command == "check":
            cmd_check(values)
        elif command == "channels":
            cmd_channels(values)
        elif command == "read":
            limit = 20
            if "--limit" in args:
                i = args.index("--limit")
                if i + 1 >= len(args):
                    die("--limit needs a number, e.g. --limit 20")
                raw = args[i + 1]
                try:
                    limit = int(raw)
                except ValueError:
                    die(f"--limit needs a number, got {raw!r}")
                if limit < 1:
                    die(f"--limit must be 1 or greater, got {limit}")
            cmd_read(values, limit)
        elif command == "post":
            text = read_message_text(args)
            if not text.strip():
                die('Nothing to post. Pass text as an argument, or pipe it in:\n'
                    '  python3 bot.py post "your message"\n'
                    '  echo "your message" | python3 bot.py post\n'
                    '  python3 bot.py post < message.txt')
            cmd_post(values, text)
        elif command == "verify":
            cmd_verify(values)
        else:
            die(f"Unknown command '{command}'. Run: python3 bot.py --help")
    except RuntimeError as err:
        die(str(err))


if __name__ == "__main__":
    main()
