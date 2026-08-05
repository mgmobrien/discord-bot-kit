#!/usr/bin/env python3
"""
Minimal Discord bot for one or more shared channels.

Standard library only — no pip install, no virtualenv, no gateway websocket.
Every command makes plain HTTPS calls to discord.com/api/v10 and prints JSON.

Usage:
    python3 bot.py check                 # who am I, which servers can I see
    python3 bot.py channels              # list channels, to find your channel id
    python3 bot.py read [--channel ID] [--limit N]   # read recent messages
    python3 bot.py post [--channel ID] "message"     # post a message
    python3 bot.py post [--channel ID] --file PATH    # upload a file
    python3 bot.py threads [--channel ID]            # list active threads
    python3 bot.py react add|remove|list --message ID --emoji X
    python3 bot.py users [ID] / user ID              # look up members
    python3 bot.py edit --message ID "corrected"      # edit your own message
    python3 bot.py delete --message ID               # delete your own message
    python3 bot.py pin add|remove|list --message ID  # pin / unpin / list pins
    python3 bot.py thread create --name "x"          # start a public thread
    python3 bot.py poll "Q?" --answer A --answer B   # send a poll
    python3 bot.py verify [--channel ID]             # end-to-end check

--channel targets any channel the bot can see, and accepts a thread ID too.
Without it, DISCORD_CHANNEL_ID from .env is used as the default target.

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
from pathlib import Path

API = "https://discord.com/api/v10"
UA = "discord-bot-kit (https://github.com/mgmobrien/discord-bot-kit, 1.0)"


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


def resolve_channel(values, channel_flag):
    """Which channel this command targets.

    --channel wins; DISCORD_CHANNEL_ID in .env is a convenience default for the
    channel you use most. A bot granted access to several channels can work all
    of them by passing --channel, so the .env value is optional, not required.

    A thread ID is accepted anywhere a channel ID is: Discord models threads as
    channels, so no separate flag is needed.
    """
    if channel_flag and channel_flag.strip():
        return channel_flag.strip()
    from_env = (values.get("DISCORD_CHANNEL_ID") or "").strip()
    if from_env:
        return from_env
    die("No channel specified. Pass --channel <id>, or set DISCORD_CHANNEL_ID "
        "in .env as your default. Run: python3 bot.py channels")


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
        return ("Unknown channel. The channel ID is wrong, or the bot is not in the "
                "server that owns it. Check the --channel value or DISCORD_CHANNEL_ID "
                "in .env. Run: python3 bot.py channels")
    if status == 404:
        return ("Not found. Check the channel ID (--channel, or DISCORD_CHANNEL_ID "
                "in .env) — run: python3 bot.py channels")
    msg = payload.get("message") if isinstance(payload, dict) else None
    return f"Discord returned HTTP {status}" + (f": {msg}" if msg else "")


def ok(status):
    return 200 <= status < 300


def encode_emoji(emoji):
    """URL-encode an emoji for the reactions endpoints.

    Unicode emoji go through percent-encoding. A CUSTOM emoji is identified as
    "name:id" (Discord's own form) and must NOT be encoded past that colon, so
    it is passed through with only the unsafe characters escaped.
    """
    return urllib.parse.quote(emoji, safe=":")


def multipart(fields, files):
    """Build a multipart/form-data body without any third-party library.

    Discord takes uploads as a payload_json part plus files[N] parts. Written
    by hand because the whole point of this kit is a zero-dependency install.
    """
    boundary = "----discordbotkit" + str(int(time.time() * 1000))
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{name}"\r\n\r\n').encode()
        body += value.encode("utf-8") + b"\r\n"
    for i, (filename, content) in enumerate(files):
        # The filename lands inside a quoted header value, so a double quote or
        # a line break in it would terminate the header early and malform the
        # request. Sanitise rather than trust: this is local input, but "local"
        # is not the same as "well-formed".
        safe_name = filename.replace("\\", "_").replace('"', "'")
        safe_name = safe_name.replace("\r", " ").replace("\n", " ") or "file"
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="files[{i}]"; '
                 f'filename="{safe_name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n").encode()
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def call_multipart(path, token, body, content_type):
    """POST a prebuilt multipart body. Same contract as call(), retries included.

    Uploads honour 429 exactly like every other call. Without this an upload
    would be the one operation that fails under rate limiting while an
    ordinary post quietly backs off and succeeds.
    """
    for attempt in range(5):
        req = urllib.request.Request(API + path, data=body, method="POST")
        req.add_header("Authorization", f"Bot {token}")
        req.add_header("User-Agent", UA)
        req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = {"raw": raw}
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


def describe_attachments(msg):
    """Attachments and embeds a message carries.

    Reported on every message, always present as a list. A read that silently
    drops attachments makes a message whose substance is a file look like an
    empty one, and nothing in the output says anything was left out.
    """
    return {
        "attachments": [
            {"filename": a.get("filename"), "size": a.get("size"),
             "contentType": a.get("content_type"), "url": a.get("url")}
            for a in (msg.get("attachments") or [])
        ],
        "embeds": [
            {"type": e.get("type"), "title": e.get("title"), "url": e.get("url")}
            for e in (msg.get("embeds") or [])
        ],
        "reactions": [
            {"emoji": (r.get("emoji") or {}).get("name"),
             "emojiId": (r.get("emoji") or {}).get("id"),
             "count": r.get("count"), "me": r.get("me")}
            for r in (msg.get("reactions") or [])
        ],
    }


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


def cmd_read(values, channel_flag, limit):
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)

    msgs = fetch_messages(token, channel, limit)
    print(json.dumps({
        "ok": True,
        "channel": channel,
        "count": len(msgs),
        "messages": [
            {
                "id": m.get("id"),
                "author": (m.get("author") or {}).get("username"),
                "authorId": (m.get("author") or {}).get("id"),
                "bot": bool((m.get("author") or {}).get("bot")),
                "timestamp": m.get("timestamp"),
                "content": m.get("content"),
                "hasThread": bool(m.get("thread")),
                "threadId": (m.get("thread") or {}).get("id"),
                **describe_attachments(m),
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
    if args and args[0].strip():
        return args[0]
    if args and not args[0].strip():
        return ""  # explicit empty argument -> caller refuses
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def cmd_post(values, channel_flag, text, file_paths=None):
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)

    # allowed_mentions parse:[] means this bot can never fire an @everyone or
    # @here ping, even if such text ends up in a message it relays. This is a
    # deliberate ceiling, not an oversight: a bot that relays text it did not
    # write must not be able to notify a whole server on the sender's say-so.
    payload = {"content": text, "allowed_mentions": {"parse": []}}

    if file_paths:
        files = []
        for fp in file_paths:
            path = Path(fp)
            if not path.is_file():
                die(f"File not found: {fp}")
            files.append((path.name, path.read_bytes()))
        body, ctype = multipart({"payload_json": json.dumps(payload)}, files)
        status, msg = call_multipart(f"/channels/{channel}/messages", token, body, ctype)
    else:
        status, msg = call("POST", f"/channels/{channel}/messages", token, body=payload)

    if not ok(status):
        die(explain(status, msg))

    print(json.dumps({"ok": True, "channel": channel,
                      "posted": {"id": msg.get("id"), "content": msg.get("content"),
                                 "attachments": [a.get("filename") for a in (msg.get("attachments") or [])]}},
                     indent=2))


def cmd_threads(values, channel_flag):
    """Active threads. Thread IDs are channel IDs — use them with --channel."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")

    status, guilds = call("GET", "/users/@me/guilds", token)
    if not ok(status):
        die(explain(status, guilds))

    wanted = (channel_flag or "").strip()
    out = []
    for g in (guilds or []):
        status, data = call("GET", f"/guilds/{g['id']}/threads/active", token)
        if not ok(status):
            out.append({"server": g.get("name"), "error": explain(status, data)})
            continue
        threads = data.get("threads", []) if isinstance(data, dict) else []
        if wanted:
            threads = [t for t in threads if t.get("parent_id") == wanted or t.get("id") == wanted]
        out.append({
            "server": g.get("name"),
            "threads": [
                {"id": t.get("id"), "name": t.get("name"),
                 "parentChannel": t.get("parent_id"),
                 "messageCount": t.get("message_count"),
                 "archived": (t.get("thread_metadata") or {}).get("archived")}
                for t in threads
            ],
        })

    print(json.dumps({
        "ok": True, "servers": out,
        "note": ("A thread ID is a channel ID. Read one with "
                 "`read --channel <threadId>`, reply with `post --channel <threadId>`. "
                 "Thread messages do NOT appear when you read the parent channel."),
    }, indent=2))


def cmd_react(values, channel_flag, action, message_id, emoji):
    """Add, remove, or list reactions. Unicode emoji or custom "name:id"."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)
    if not message_id:
        die("react needs --message <messageId>")

    if action == "list":
        status, msg = call("GET", f"/channels/{channel}/messages/{message_id}", token)
        if not ok(status):
            die(explain(status, msg))
        print(json.dumps({"ok": True, "channel": channel, "message": message_id,
                          "reactions": describe_attachments(msg)["reactions"]}, indent=2))
        return

    if not emoji:
        die(f"react {action} needs --emoji <emoji>  (unicode, or custom as name:id)")

    enc = encode_emoji(emoji)
    path = f"/channels/{channel}/messages/{message_id}/reactions/{enc}/@me"
    status, payload = call("PUT" if action == "add" else "DELETE", path, token)
    if not ok(status):
        die(explain(status, payload))
    print(json.dumps({"ok": True, "channel": channel, "message": message_id,
                      "emoji": emoji, "action": action}, indent=2))


def cmd_edit(values, channel_flag, message_id, text):
    """Edit a message this bot sent. Discord only permits editing your own."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)
    if not message_id:
        die("edit needs --message <messageId>")
    if not text.strip():
        die('edit needs the new text: python3 bot.py edit --message ID "corrected text"')

    status, msg = call("PATCH", f"/channels/{channel}/messages/{message_id}", token,
                       body={"content": text, "allowed_mentions": {"parse": []}})
    if not ok(status):
        die(explain(status, msg))
    print(json.dumps({"ok": True, "channel": channel,
                      "edited": {"id": msg.get("id"), "content": msg.get("content")}}, indent=2))


def cmd_delete(values, channel_flag, message_id):
    """Delete a message. Own messages need no permission; other people's need
    Manage Messages, which this kit deliberately does not request — so deleting
    someone else's message returns a permissions error, by design."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)
    if not message_id:
        die("delete needs --message <messageId>")

    status, payload = call("DELETE", f"/channels/{channel}/messages/{message_id}", token)
    if not ok(status):
        die(explain(status, payload))
    print(json.dumps({"ok": True, "channel": channel, "deleted": message_id}, indent=2))


def cmd_pin(values, channel_flag, action, message_id):
    """Pin, unpin, or list pins. Uses the current /messages/pins routes; the
    older /channels/{id}/pins endpoints are deprecated."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)

    if action == "list":
        status, data = call("GET", f"/channels/{channel}/messages/pins", token)
        if not ok(status):
            die(explain(status, data))
        items = data.get("items", data) if isinstance(data, dict) else data
        print(json.dumps({"ok": True, "channel": channel, "pinned": [
            {"id": (i.get("message") or i).get("id"),
             "author": ((i.get("message") or i).get("author") or {}).get("username"),
             "content": (i.get("message") or i).get("content"),
             "pinnedAt": i.get("pinned_at")}
            for i in (items or [])
        ]}, indent=2))
        return

    if not message_id:
        die(f"pin {action} needs --message <messageId>")
    method = "PUT" if action == "add" else "DELETE"
    status, payload = call(method, f"/channels/{channel}/messages/pins/{message_id}", token)
    if not ok(status):
        die(explain(status, payload))
    print(json.dumps({"ok": True, "channel": channel, "message": message_id,
                      "action": action}, indent=2))


def cmd_thread_create(values, channel_flag, message_id, name):
    """Start a public thread, optionally hanging off an existing message."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)
    if not name:
        die('thread create needs --name "thread name"')

    if message_id:
        path = f"/channels/{channel}/messages/{message_id}/threads"
        body = {"name": name}
    else:
        path = f"/channels/{channel}/threads"
        body = {"name": name, "type": 11}  # 11 = public thread

    status, thread = call("POST", path, token, body=body)
    if not ok(status):
        die(explain(status, thread))
    print(json.dumps({"ok": True, "channel": channel, "thread": {
        "id": thread.get("id"), "name": thread.get("name"),
    }, "note": "Post into it with: post --channel " + str(thread.get("id"))}, indent=2))


def cmd_poll(values, channel_flag, question, answers, duration, multi):
    """Send a poll. Discord takes it as a field on an ordinary message."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)
    if not question.strip():
        die('poll needs a question: python3 bot.py poll "Which one?" --answer A --answer B')
    if len(answers) < 2:
        die("poll needs at least two --answer values")
    if len(answers) > 10:
        die(f"poll allows at most 10 answers, got {len(answers)}")

    hours = 24
    if duration is not None:
        try:
            hours = int(duration)
        except ValueError:
            die(f"--duration needs a number of hours, got {duration!r}")
        if not 1 <= hours <= 768:
            die(f"--duration must be between 1 and 768 hours (32 days), got {hours}")

    status, msg = call("POST", f"/channels/{channel}/messages", token, body={
        "poll": {
            "question": {"text": question},
            "answers": [{"poll_media": {"text": a}} for a in answers],
            "duration": hours,
            "allow_multiselect": bool(multi),
        },
        "allowed_mentions": {"parse": []},
    })
    if not ok(status):
        die(explain(status, msg))
    print(json.dumps({"ok": True, "channel": channel, "poll": {
        "messageId": msg.get("id"), "question": question,
        "answers": answers, "durationHours": hours,
        "allowMultiselect": bool(multi),
    }}, indent=2))


def cmd_users(values, user_id):
    """Look up one user, or list members of each visible server."""
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")

    if user_id:
        status, u = call("GET", f"/users/{user_id}", token)
        if not ok(status):
            die(explain(status, u))
        print(json.dumps({"ok": True, "user": {
            "id": u.get("id"), "username": u.get("username"),
            "globalName": u.get("global_name"), "bot": bool(u.get("bot")),
        }}, indent=2))
        return

    status, guilds = call("GET", "/users/@me/guilds", token)
    if not ok(status):
        die(explain(status, guilds))
    out = []
    for g in (guilds or []):
        status, members = call("GET", f"/guilds/{g['id']}/members", token,
                               params={"limit": 100})
        if not ok(status):
            out.append({"server": g.get("name"), "error": explain(status, members),
                        "hint": ("Listing members needs the SERVER MEMBERS privileged "
                                 "intent. Look users up individually with "
                                 "`user <id>` instead — that needs no intent.")})
            continue
        out.append({"server": g.get("name"), "members": [
            {"id": (m.get("user") or {}).get("id"),
             "username": (m.get("user") or {}).get("username"),
             "nick": m.get("nick"),
             "bot": bool((m.get("user") or {}).get("bot"))}
            for m in (members or [])
        ]})
    print(json.dumps({"ok": True, "servers": out}, indent=2))


def cmd_verify(values, channel_flag=None):
    """
    End-to-end check: post a message, read the channel back, and diagnose the
    two failures that look like broken code but are actually setup mistakes.
    """
    token = need(values, "DISCORD_BOT_TOKEN", "Add it to .env. See SETUP.md step 3.")
    channel = resolve_channel(values, channel_flag)

    steps = []

    status, me = call("GET", "/users/@me", token)
    if not ok(status):
        die(explain(status, me))
    steps.append({"step": "authenticate", "ok": True, "bot": me.get("username")})

    marker = f"discord-bot-kit online — {me.get('username')} reporting in."
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

def take_flag(args, name):
    """Remove '--name value' from args in place and return the value, or None.

    Flags are stripped BEFORE positionals are read, so `post --channel 123 "hi"`
    cannot mistake --channel for the message text. Doing this the other way
    round is how a flag ends up posted to a channel as a message.
    """
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        die(f"{name} needs a value")
    value = args[i + 1]
    del args[i:i + 2]
    return value


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return

    values = load_env()
    command = argv[0]
    args = list(argv[1:])

    try:
        channel_flag = take_flag(args, "--channel")
        limit_flag = take_flag(args, "--limit")
        message_flag = take_flag(args, "--message")
        emoji_flag = take_flag(args, "--emoji")
        name_flag = take_flag(args, "--name")
        duration_flag = take_flag(args, "--duration")
        file_flags = []
        while "--file" in args:
            file_flags.append(take_flag(args, "--file"))
        answer_flags = []
        while "--answer" in args:
            answer_flags.append(take_flag(args, "--answer"))
        multi = "--multi" in args
        if multi:
            args.remove("--multi")

        if command == "check":
            cmd_check(values)
        elif command == "channels":
            cmd_channels(values)
        elif command == "read":
            limit = 20
            if limit_flag is not None:
                try:
                    limit = int(limit_flag)
                except ValueError:
                    die(f"--limit needs a number, got {limit_flag!r}")
                if limit < 1:
                    die(f"--limit must be 1 or greater, got {limit}")
            cmd_read(values, channel_flag, limit)
        elif command == "post":
            text = read_message_text(args)
            if not text.strip() and not file_flags:
                die('Nothing to post. Pass text as an argument, or pipe it in:\n'
                    '  python3 bot.py post "your message"\n'
                    '  echo "your message" | python3 bot.py post\n'
                    '  python3 bot.py post < message.txt')
            cmd_post(values, channel_flag, text, file_flags)
        elif command == "threads":
            cmd_threads(values, channel_flag)
        elif command == "react":
            action = args[0] if args else ""
            if action not in ("add", "remove", "list"):
                die("react needs an action: add | remove | list\n"
                    '  python3 bot.py react add --channel ID --message ID --emoji "👍"')
            cmd_react(values, channel_flag, action, message_flag, emoji_flag)
        elif command == "edit":
            cmd_edit(values, channel_flag, message_flag, read_message_text(args))
        elif command == "delete":
            cmd_delete(values, channel_flag, message_flag)
        elif command == "pin":
            action = args[0] if args else ""
            if action not in ("add", "remove", "list"):
                die("pin needs an action: add | remove | list\n"
                    "  python3 bot.py pin add --message <messageId>")
            cmd_pin(values, channel_flag, action, message_flag)
        elif command == "thread":
            action = args[0] if args else ""
            if action != "create":
                die('thread needs an action: create\n'
                    '  python3 bot.py thread create --name "name" [--message <messageId>]\n'
                    "  (to LIST threads use: python3 bot.py threads)")
            cmd_thread_create(values, channel_flag, message_flag, name_flag)
        elif command == "poll":
            cmd_poll(values, channel_flag, read_message_text(args[1:] if args and args[0] == "create" else args),
                     answer_flags, duration_flag, multi)
        elif command == "users":
            cmd_users(values, args[0] if args else None)
        elif command == "user":
            if not args:
                die("user needs an id: python3 bot.py user <userId>")
            cmd_users(values, args[0])
        elif command == "verify":
            cmd_verify(values, channel_flag)
        else:
            die(f"Unknown command '{command}'. Run: python3 bot.py --help")
    except RuntimeError as err:
        die(str(err))


if __name__ == "__main__":
    main()
