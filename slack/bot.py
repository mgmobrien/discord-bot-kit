#!/usr/bin/env python3
"""
Minimal Slack bot for one or more shared channels.

Standard library only — no pip install, no virtualenv, no socket mode, no
daemon, no listener, nothing needing a public URL. Every command makes plain
HTTPS calls to slack.com/api and prints JSON.

Usage:
    python3 bot.py check                 # is the bot token real, and who is it
    python3 bot.py check --user          # is the USER token real, and who is it
    python3 bot.py check --channel C123  # can the bot SEE that channel
    python3 bot.py check --member C123   # is the bot actually IN that channel
    python3 bot.py channels              # list channels, to find your channel id
    python3 bot.py join --channel C123   # add the bot to a PUBLIC channel
    python3 bot.py read [--channel C] [--thread TS] [--limit N]
    python3 bot.py threads [--channel C] [--limit N]  # parents that have replies
    python3 bot.py post [--channel C] "message"       # post
    python3 bot.py post [--channel C] --as "Name" --icon ":robot_face:" "msg"
    python3 bot.py post [--channel C] --file PATH     # upload a file
    python3 bot.py reply --channel C --thread TS "in-thread reply"
    python3 bot.py edit --message TS "corrected"      # edit your own message
    python3 bot.py delete --message TS                # delete your own message
    python3 bot.py react add|remove|list --message TS --emoji thumbsup
    python3 bot.py pin add|remove|list [--message TS]
    python3 bot.py users / user U123                  # look up people
    python3 bot.py invite --channel C --user U123     # invite someone
    python3 bot.py invite --channel C --email you@example.com   # Slack Connect
    python3 bot.py dm send --user U123 "message"      # DM a person
    python3 bot.py dm read --user U123 [--limit N]
    python3 bot.py verify [--channel C]               # end-to-end check

--channel takes a channel ID (C…/G…), never a name: names are ambiguous and
anyone can change them. Without it, SLACK_CHANNEL_ID from .env is the default.

A THREAD IS NOT A CHANNEL on Slack. It is a `thread_ts` on a parent channel, so
it gets its own --thread flag. Code written against the Discord model — where a
thread IS a channel and --channel takes a thread ID — does not port here. This
is the difference most likely to produce a confident wrong answer.

NOTE ON `invite`, because the same word means different things across this kit:
on the Discord side `invite` prints the bot's own install URL. Slack has no such
URL — installation is the manifest flow in SETUP.md — so here `invite` means
inviting PEOPLE to a channel. Same verb, unrelated action.

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

API = "https://slack.com/api/"
UA = "chat-platform-bot-kit slack (https://github.com/mgmobrien/discord-bot-kit, 1.0)"

# Every Slack scope this kit uses, mapped to the command that needs it. SCOPES.md
# is the prose version of this table. Kept here so `check` can name the scope a
# failure is asking for instead of echoing Slack's bare error string, and so the
# two surfaces are visibly the same list rather than two lists that drift.
SCOPE_FOR = {
    "team:read": "check",
    "channels:read": "channels, check --channel",
    "channels:history": "read, threads, verify",
    "channels:join": "join",
    "channels:write.invites": "invite",
    "groups:read": "channels, check --channel",
    "groups:history": "read, threads, verify",
    "groups:write.invites": "invite",
    "chat:write": "post, reply, edit, delete, verify",
    "chat:write.customize": "post --as",
    "reactions:read": "react list",
    "reactions:write": "react add, react remove",
    "pins:read": "pin list",
    "pins:write": "pin add, pin remove",
    "files:read": "read",
    "files:write": "post --file",
    "users:read": "user, users, read",
    "conversations.connect:write": "invite --email",
    "im:read": "dm",
    "im:write": "dm send",
    "im:history": "dm read",
    "identify": "check --user",
}


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
    for key in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN", "SLACK_CHANNEL_ID"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def die(message, code=2, **extra):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    sys.exit(code)


def need(values, key, hint):
    val = values.get(key)
    if not val:
        die(f"{key} is not set. {hint}")
    return val


def bot_token(values):
    return need(values, "SLACK_BOT_TOKEN",
                "Add it to .env. It starts xoxb- and comes from SETUP.md step 2.")


def user_token(values):
    return need(values, "SLACK_USER_TOKEN",
                "Add it to .env. It starts xoxp- and comes from SETUP.md step 3. "
                "It is optional for every command except `check --user`.")


def resolve_channel(values, channel_flag):
    """Which channel this command targets.

    --channel wins; SLACK_CHANNEL_ID in .env is a convenience default for the
    channel you use most. A bot in several channels works them all by passing
    --channel, so the .env value is optional, not required.

    This takes an ID, never a name. `#general` is not accepted: names are
    ambiguous across public/private, and anyone in a workspace can rename a
    channel out from under a script.
    """
    if channel_flag and channel_flag.strip():
        chan = channel_flag.strip()
        if chan.startswith("#"):
            die(f"--channel takes a channel ID, not a name ({chan!r}). Names are "
                "ambiguous and can be changed by anyone. Run: python3 bot.py channels")
        return chan
    from_env = (values.get("SLACK_CHANNEL_ID") or "").strip()
    if from_env:
        return from_env
    die("No channel specified. Pass --channel <id>, or set SLACK_CHANNEL_ID in "
        ".env as your default. Run: python3 bot.py channels")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
#
# THE ONE STRUCTURAL DIFFERENCE FROM THE DISCORD SIDE, and the reason code
# ported from it fails in a way that looks like success:
#
#   Discord signals failure with the HTTP STATUS. 403, 404, 401.
#   Slack answers almost everything with HTTP 200 and puts the failure in the
#   BODY, as {"ok": false, "error": "not_in_channel"}.
#
# So `if 200 <= status < 300` — correct on Discord, and the natural thing to
# write — treats every Slack error as a success and hands the caller a payload
# with no data in it. That is precisely the failed-call-reported-as-empty-result
# conflation the root README forbids, arrived at by porting rather than by
# carelessness. call() below returns the parsed `ok` flag, never the status, and
# nothing outside this section looks at an HTTP code.

def call(method, token, params=None, body_json=None):
    """
    One Slack Web API call.

    Returns (ok, payload) where `ok` is Slack's own body flag, not the HTTP
    status. `payload` is always a dict.

    Raises RuntimeError on transport failure. That distinction matters: a call
    that could not be MADE is not the same as a call that returned nothing, and
    the callers below never treat the first as the second.
    """
    url = API + method

    data = None
    headers = {"Authorization": f"Bearer {token}", "User-Agent": UA}
    if body_json is not None:
        data = json.dumps(body_json).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    elif params:
        # GET-style methods take form encoding. Slack accepts params in the
        # query string for read methods; keeping them there leaves the body
        # empty so a proxy or log never sees them as a POST payload.
        url += "?" + urllib.parse.urlencode(params)

    for attempt in range(5):
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data is not None else "GET")
        for key, val in headers.items():
            req.add_header(key, val)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                if not isinstance(parsed, dict):
                    parsed = {"ok": False, "error": "malformed_response",
                              "raw": str(parsed)[:400]}
                # Slack rate limits with a body flag too, on some methods.
                if parsed.get("error") == "ratelimited" and attempt < 4:
                    time.sleep(min(1.0 * (attempt + 1), 30))
                    continue
                return bool(parsed.get("ok")), parsed
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}

            # 429 is the documented rate-limit signal and Slack states the wait
            # in Retry-After. Rate limits are PER METHOD, so backing off here
            # does not mean the token is globally throttled.
            if err.code == 429 and attempt < 4:
                wait = 1.0
                try:
                    wait = float(err.headers.get("Retry-After") or 1.0)
                except (TypeError, ValueError):
                    wait = 1.0
                time.sleep(min(wait + 0.25, 60))
                continue

            parsed.setdefault("ok", False)
            parsed.setdefault("error", f"http_{err.code}")
            return False, parsed
        except urllib.error.URLError as err:
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"could not reach slack.com: {err.reason}") from err

    raise RuntimeError("gave up after repeated rate limiting")


def explain(payload, context=""):
    """Turn a Slack error into something a human or an agent can act on."""
    err = (payload or {}).get("error") or "unknown_error"

    if err == "not_in_channel":
        return ("not_in_channel — the bot is not a MEMBER of that channel. This is "
                "not a scope problem and no scope will fix it. Being able to see a "
                "channel is not the same as being in it. For a PUBLIC channel: run "
                "`python3 bot.py join --channel <id>`. For a PRIVATE channel there is "
                "no self-join — a human must run `/invite @yourname-bot` in it. "
                "This is the failure Slack is quietest about; see SETUP.md.")
    if err == "channel_not_found":
        return ("channel_not_found — either the ID is wrong, or it is a private "
                "channel this bot cannot see at all. Those two are INDISTINGUISHABLE "
                "from outside: Slack will not confirm that a private channel exists. "
                "Check the ID with `python3 bot.py channels`; if it is private, a "
                "human has to invite the bot before it can see anything.")
    if err == "missing_scope":
        wanted = (payload or {}).get("needed")
        have = (payload or {}).get("provided")
        hint = f" Slack says it needed: {wanted}." if wanted else ""
        if wanted and wanted in SCOPE_FOR:
            hint += f" (this kit uses it for: {SCOPE_FOR[wanted]})"
        if have:
            hint += f" The token currently carries: {have}."
        return ("missing_scope — the token does not carry a scope this call needs." +
                hint + " Add it to manifest.json and REINSTALL the app. Editing "
                "scopes does nothing to an already-installed app until it is "
                "installed again, and that is almost always the missed step.")
    if err in ("invalid_auth", "not_authed", "token_revoked", "account_inactive"):
        return (f"{err} — the token was rejected. Check it in .env: wrong, truncated, "
                "revoked, or the app was uninstalled. Bot tokens start xoxb-, user "
                "tokens start xoxp-. Copy it again from Install App in the portal.")
    if err == "not_allowed_token_type":
        return ("not_allowed_token_type — the wrong KIND of token for this call. You "
                "used the bot token (xoxb-) where the user token (xoxp-) was needed, "
                "or the reverse. In this kit only `check --user` uses the user token.")
    if err == "is_archived":
        return "is_archived — that channel is archived. Unarchive it in Slack first."
    if err == "already_in_channel":
        return "already_in_channel — the bot is already a member. Nothing to do."
    if err == "method_not_supported_for_channel_type":
        return ("method_not_supported_for_channel_type — this action does not apply to "
                "that kind of conversation. Self-join works on PUBLIC channels only: a "
                "private channel needs a human to invite the bot.")
    if err == "cant_invite_self":
        return "cant_invite_self — use `join` to add the bot itself to a public channel."
    if err == "ratelimited":
        return ("ratelimited — Slack is throttling this method. Rate limits are per "
                "method, so this does not mean the token is globally throttled. "
                "The kit already honours Retry-After; retry in a moment.")
    if err == "no_permission" or err == "restricted_action":
        return (f"{err} — the workspace forbids this action for this app, independently "
                "of scopes. A workspace admin controls it; adding scopes will not help.")
    if err == "message_not_found":
        return ("message_not_found — no message with that timestamp in that channel. A "
                "Slack message ID is a `ts` like 1699999999.000100 and it is scoped to "
                "its channel: the same ts in the wrong channel is simply not found. "
                "Copy it from `read` output, and pass it as-is.")
    if err == "cant_update_message" or err == "cant_delete_message":
        return (f"{err} — this bot may only edit or delete messages it sent ITSELF. "
                "Slack does not grant apps a way to modify other people's messages, "
                "and this kit requests no scope that would change that.")
    if err.startswith("http_"):
        return (f"Slack returned {err.replace('http_', 'HTTP ')}" +
                (f" ({context})" if context else "") +
                ". This is a transport-level failure, not a Slack API error.")
    detail = (payload or {}).get("detail") or (payload or {}).get("needed")
    return f"Slack returned error '{err}'" + (f": {detail}" if detail else "") + \
           (f" ({context})" if context else "")


# --------------------------------------------------------------------------
# outbound text safety
# --------------------------------------------------------------------------

def defang_broadcasts(text):
    """Neutralise @channel / @here / @everyone in outbound text.

    Returns (safe_text, list_of_defanged_names).

    This mirrors the deliberate ceiling on the Discord side, where every post
    sets allowed_mentions parse:[] so a relayed message can never fire an
    @everyone. The MECHANISM is different and the difference matters: on Slack,
    typing the plain words "@channel" does nothing at all — a broadcast ping
    requires the literal control sequence <!channel>. So ordinary relayed prose
    is already harmless and needs no defusing.

    What is NOT harmless is relaying text that already contains the control
    sequence — which happens whenever a message is copied out of Slack and back
    in again, since that is exactly how Slack renders it on the way out. A bot
    that relays text it did not write must not be able to notify a whole
    workspace on the sender's say-so, so the sequence is rewritten to its plain
    form, and the output says which ones were changed rather than silently
    editing someone's message.
    """
    defanged = []
    out = text
    for name in ("channel", "here", "everyone"):
        for form in (f"<!{name}>", f"<!{name}|@{name}>", f"<!{name}|{name}>"):
            if form in out:
                out = out.replace(form, f"@{name}")
                if name not in defanged:
                    defanged.append(name)
    return out, defanged


def read_message_text(args):
    """Message text from an argument, or from stdin when no argument is given.

    Stdin exists so long or awkward messages never have to survive a trip
    through the shell: backticks, quotes and newlines in a command argument get
    mangled or executed. `bot.py post < note.txt` and `... | bot.py post` both
    land here.

    If there is no argument AND stdin is a terminal, there is nothing to read
    and waiting would look like a hang, so that case returns empty immediately
    and the caller refuses.
    """
    if args and args[0].strip():
        return args[0]
    if args and not args[0].strip():
        return ""  # explicit empty argument -> caller refuses
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


# --------------------------------------------------------------------------
# shaping
# --------------------------------------------------------------------------

def describe_message(msg, names=None, self_id=None):
    """One message, in the shape every command reports.

    `files` and `reactions` are ALWAYS present. An empty list means
    checked-and-none-there, never did-not-look. A read that silently drops
    attachments makes a message whose whole substance is a file look like an
    empty one, with nothing in the output saying anything was omitted.

    `self_id` is this bot's own user ID, needed only to answer "did I react to
    this" — the one reaction it is able to remove. When it is not known the
    field is None, meaning DID NOT LOOK, and never False, which would mean
    checked-and-no. That distinction is the whole contract of this kit and it
    is as easy to break in a boolean as in a list.
    """
    names = names or {}
    user_id = msg.get("user") or msg.get("bot_id")
    return {
        # Slack's message ID is `ts`, and it is a STRING. It looks like a float
        # and must never be parsed as one: 1699999999.000100 through a float
        # loses the trailing precision that distinguishes two messages posted in
        # the same second, and the corrupted value then fails as message_not_found.
        "ts": msg.get("ts"),
        "author": names.get(user_id) or user_id,
        "authorId": user_id,
        "bot": bool(msg.get("bot_id")) or msg.get("subtype") == "bot_message",
        "text": msg.get("text"),
        "threadTs": msg.get("thread_ts"),
        "replyCount": msg.get("reply_count", 0),
        "isThreadParent": bool(msg.get("thread_ts")) and
                          msg.get("thread_ts") == msg.get("ts"),
        "edited": bool(msg.get("edited")),
        "files": [
            {"id": f.get("id"), "name": f.get("name"),
             "size": f.get("size"), "mimetype": f.get("mimetype"),
             "urlPrivate": f.get("url_private")}
            for f in (msg.get("files") or [])
        ],
        "reactions": [
            {"emoji": r.get("name"), "count": r.get("count"),
             "users": r.get("users") or [],
             "me": (self_id in (r.get("users") or [])) if self_id else None}
            for r in (msg.get("reactions") or [])
        ],
    }


_SELF_ID_CACHE = {}


def self_id(token):
    """This bot's own user ID, or None if it cannot be determined.

    Cached for the life of the process because several commands need it and it
    never changes mid-run. None is a real answer meaning could-not-ask; callers
    must not turn it into a False.
    """
    if token in _SELF_ID_CACHE:
        return _SELF_ID_CACHE[token]
    ok_flag, payload = call("auth.test", token)
    value = payload.get("user_id") if ok_flag else None
    _SELF_ID_CACHE[token] = value
    return value


def resolve_names(token, messages):
    """user_id -> display name, for the authors present in `messages`.

    Best effort by design. If users:read is missing, every author stays an
    opaque U… ID and the caller says so — it does not invent a name and it does
    not fail the whole read over a cosmetic lookup.
    """
    ids = {m.get("user") for m in messages if m.get("user")}
    names = {}
    for uid in ids:
        ok_flag, payload = call("users.info", token, params={"user": uid})
        if ok_flag:
            user = payload.get("user") or {}
            profile = user.get("profile") or {}
            names[uid] = (profile.get("display_name")
                          or profile.get("real_name")
                          or user.get("name") or uid)
    return names


def paged_conversations(token, types):
    """Every conversation of `types` the token can see, following cursors.

    Slack pages this endpoint and a single call returns a partial list with no
    indication that more exist. Stopping at the first page produces a channel
    list that is quietly incomplete — the channel you want is simply absent, and
    it looks identical to not having access to it.
    """
    out, cursor = [], None
    for _ in range(20):  # 20 * 200 = 4000 conversations; far past this kit's scale
        params = {"types": types, "limit": 200, "exclude_archived": "true"}
        if cursor:
            params["cursor"] = cursor
        ok_flag, payload = call("conversations.list", token, params=params)
        if not ok_flag:
            return None, payload
        out.extend(payload.get("channels") or [])
        cursor = ((payload.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break
    return out, None


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_check(values, stage, channel_flag):
    """Staged check. Slack fails in stages and each stage has a different fix.

    One aggregate check would report that something is wrong without saying
    which — on the platform whose most common failure (not being a member of the
    channel) is invisible to every scope you could add.
    """
    # --- stage: user token -------------------------------------------------
    if stage == "user":
        token = user_token(values)
        ok_flag, payload = call("auth.test", token)
        if not ok_flag:
            die(explain(payload, "auth.test with the user token"))
        print(json.dumps({
            "ok": True,
            "stage": "user",
            "user": {"name": payload.get("user"), "id": payload.get("user_id")},
            "workspace": {"name": payload.get("team"), "id": payload.get("team_id")},
            "note": ("This token acts as YOU, with your access to every channel you "
                     "are in. This kit uses it only where Slack offers no bot "
                     "equivalent. If you are reaching for it to work around a "
                     "permission problem, the answer is a scope or an invite."),
        }, indent=2))
        return

    token = bot_token(values)

    # --- stage: can the bot SEE the channel --------------------------------
    if stage == "channel":
        channel = resolve_channel(values, channel_flag)
        ok_flag, payload = call("conversations.info", token,
                                params={"channel": channel})
        if not ok_flag:
            die(explain(payload, f"conversations.info for {channel}"),
                stage="channel", channel=channel)
        info = payload.get("channel") or {}
        out = {
            "ok": True,
            "stage": "channel",
            "channel": {"id": info.get("id"), "name": info.get("name"),
                        "private": bool(info.get("is_private")),
                        "archived": bool(info.get("is_archived")),
                        "isDefault": bool(info.get("is_general"))},
            "note": ("The bot can SEE this channel. That is not the same as being IN "
                     "it, and only membership permits reading a word. Run: "
                     f"python3 bot.py check --member {channel}"),
        }
        if info.get("is_general"):
            # is_general is Slack's own marker for the workspace default channel
            # (#all-<workspace> on a new workspace). Detected mechanically rather
            # than by matching the name, because the name is workspace-specific
            # and renameable, and a string match would miss a renamed default and
            # falsely flag a channel that merely looks like one.
            out["note"] += (" NOTE: this is the workspace DEFAULT channel — everyone "
                            "is in it automatically. SETUP.md step 5 says to create a "
                            "real channel and use that instead, particularly before "
                            "doing external invites.")
        print(json.dumps(out, indent=2))
        return

    # --- stage: is the bot IN the channel ----------------------------------
    #
    # The stage that matters most. `is_member` is the whole answer and it is a
    # different axis from every scope: a correctly-scoped bot lists #general
    # happily and then returns not_in_channel when asked to read it.
    if stage == "member":
        channel = resolve_channel(values, channel_flag)
        ok_flag, payload = call("conversations.info", token,
                                params={"channel": channel})
        if not ok_flag:
            die(explain(payload, f"conversations.info for {channel}"),
                stage="member", channel=channel)
        info = payload.get("channel") or {}

        # is_member is absent for conversation types where membership is not a
        # concept (a DM). Absent is NOT false — reporting "unknown" keeps a
        # cannot-tell distinct from a no, which is the same rule the rest of
        # this kit follows for empty-vs-could-not-look.
        if "is_member" not in info:
            print(json.dumps({
                "ok": True, "stage": "member", "member": "unknown",
                "channel": {"id": info.get("id"), "name": info.get("name")},
                "note": ("Slack did not report membership for this conversation type, "
                         "so this is undetermined — not a no. Direct messages have no "
                         "membership axis."),
            }, indent=2))
            return

        is_member = bool(info.get("is_member"))
        private = bool(info.get("is_private"))
        is_default = bool(info.get("is_general"))
        if is_member:
            note = "The bot is a member and can read this channel."
        elif private:
            note = ("NOT A MEMBER, and this is a PRIVATE channel — there is no "
                    "self-join. A human must run `/invite @yourname-bot` in it. "
                    "No scope substitutes for this.")
        else:
            note = ("NOT A MEMBER. Every read will return not_in_channel and no scope "
                    "will fix it. This channel is public, so the bot can add itself: "
                    f"python3 bot.py join --channel {channel}")
        if is_default:
            note += (" This is also the workspace DEFAULT channel; SETUP.md step 5 "
                     "says to use a real channel instead.")
        print(json.dumps({
            "ok": True, "stage": "member", "member": is_member,
            "channel": {"id": info.get("id"), "name": info.get("name"),
                        "private": private, "isDefault": is_default},
            "note": note,
        }, indent=2))
        sys.exit(0 if is_member else 1)

    # --- stage: default, the bot token -------------------------------------
    ok_flag, auth = call("auth.test", token)
    if not ok_flag:
        die(explain(auth, "auth.test with the bot token"))

    out = {
        "ok": True,
        "stage": "bot",
        "bot": {"name": auth.get("user"), "id": auth.get("user_id"),
                "botId": auth.get("bot_id")},
        "workspace": {"name": auth.get("team"), "id": auth.get("team_id"),
                      "url": auth.get("url")},
    }

    # team.info is the only reason team:read is requested: a token that works is
    # not the same as a token that works HERE, and auth.test's team name is the
    # one the token was issued for either way. Its failure is not fatal.
    ok_team, team = call("team.info", token)
    if ok_team:
        info = team.get("team") or {}
        out["workspace"]["name"] = info.get("name") or out["workspace"]["name"]
        out["workspace"]["domain"] = info.get("domain")
    else:
        out["workspace"]["detail"] = (
            "Could not read team.info (" + str(team.get("error")) + "). The workspace "
            "name above comes from auth.test instead. This is not evidence of a bad "
            "token.")

    out["note"] = ("Bot token is valid. Next, the two questions scopes cannot answer: "
                   "`check --channel <id>` (can it see the channel) then "
                   "`check --member <id>` (is it IN the channel). The second is the "
                   "one that catches the failure Slack is quietest about.")
    print(json.dumps(out, indent=2))


def cmd_channels(values):
    token = bot_token(values)

    channels, err = paged_conversations(token, "public_channel,private_channel")
    if channels is None:
        die(explain(err, "conversations.list"))

    listed = [
        {
            "name": c.get("name"),
            "id": c.get("id"),
            "private": bool(c.get("is_private")),
            # Membership is reported per channel because it is the thing that
            # decides whether reading works, and it is invisible in a bare list.
            # Copying an ID out of a plain list is the trap: the next command
            # fails with not_in_channel and nothing explains why.
            "member": bool(c.get("is_member")),
            # Slack's own marker for the workspace default channel, rather than
            # matching on the #all-<workspace> name, which is renameable.
            "isDefault": bool(c.get("is_general")),
        }
        for c in channels
    ]
    listed.sort(key=lambda c: (not c["member"], c["name"] or ""))

    not_member = [c for c in listed if not c["member"]]
    note = ("Copy the id of the channel you want into SLACK_CHANNEL_ID in .env. "
            "This is an ID, not a name.")
    if not_member:
        note += (f" {len(not_member)} of these show member:false — the bot can see "
                 "them but cannot read a word until it is IN them. Public: "
                 "`join --channel <id>`. Private: a human must /invite it.")
    if not listed:
        note += (" No channels came back at all. Either the bot is in a workspace "
                 "with none visible to it, or channels:read and groups:read are "
                 "missing — a missing groups:read makes private channels not merely "
                 "unreadable but INVISIBLE, indistinguishable from not existing.")

    print(json.dumps({"ok": True, "count": len(listed), "channels": listed,
                      "note": note}, indent=2))


def cmd_join(values, channel_flag):
    """Add the bot to a PUBLIC channel. There is no private equivalent."""
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)

    ok_flag, payload = call("conversations.join", token,
                            body_json={"channel": channel})
    if not ok_flag:
        die(explain(payload, f"conversations.join for {channel}"))

    info = payload.get("channel") or {}
    print(json.dumps({
        "ok": True, "channel": {"id": info.get("id") or channel, "name": info.get("name")},
        "joined": True,
        "warning": payload.get("warning"),
        "note": "The bot is now a member and can read this channel.",
    }, indent=2))


def fetch_history(token, channel, limit, thread_ts=None):
    """Channel history, or one thread's replies. Dies on failure, never returns []."""
    capped = max(1, min(int(limit), 200))
    if thread_ts:
        ok_flag, payload = call("conversations.replies", token,
                                params={"channel": channel, "ts": thread_ts,
                                        "limit": capped})
        context = f"conversations.replies for {channel} thread {thread_ts}"
    else:
        ok_flag, payload = call("conversations.history", token,
                                params={"channel": channel, "limit": capped})
        context = f"conversations.history for {channel}"
    if not ok_flag:
        die(explain(payload, context))
    return payload.get("messages") or []


def cmd_read(values, channel_flag, thread_ts, limit):
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)

    msgs = fetch_history(token, channel, limit, thread_ts)
    # Slack returns newest-first for history, oldest-first for replies. Normalise
    # to oldest-first so a reader always sees conversation order.
    ordered = msgs if thread_ts else list(reversed(msgs))
    names = resolve_names(token, ordered)
    # Only asked for when something actually carries a reaction, so an ordinary
    # read costs no extra call.
    mine = self_id(token) if any(m.get("reactions") for m in ordered) else None

    out = {
        "ok": True,
        "channel": channel,
        "thread": thread_ts,
        "count": len(ordered),
        "messages": [describe_message(m, names, mine) for m in ordered],
    }
    if not names and ordered:
        out["note"] = ("Author IDs were not resolved to names — users:read is "
                       "probably missing. The messages are complete; only the "
                       "display names are absent.")
    if thread_ts:
        out["note"] = (out.get("note", "") + " Thread replies do NOT appear in a read "
                       "of the parent channel, and vice versa.").strip()
    print(json.dumps(out, indent=2))


def cmd_threads(values, channel_flag, limit):
    """Parent messages in a channel that have replies.

    Slack has no list-threads endpoint — a thread is not an object you can
    enumerate, it is a `thread_ts` on a parent message. So this scans recent
    history for parents carrying a reply count. That is a real limitation and
    it is stated in the output: a thread whose parent has scrolled past `limit`
    will not appear, and its absence is not evidence it does not exist.
    """
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)

    msgs = fetch_history(token, channel, limit)
    parents = [m for m in msgs if m.get("reply_count")]
    names = resolve_names(token, parents)

    print(json.dumps({
        "ok": True,
        "channel": channel,
        "scanned": len(msgs),
        "count": len(parents),
        "threads": [
            {"threadTs": m.get("ts"),
             "author": names.get(m.get("user")) or m.get("user"),
             "text": m.get("text"),
             "replyCount": m.get("reply_count"),
             "lastReply": m.get("latest_reply")}
            for m in parents
        ],
        "note": ("Read one with `read --channel {c} --thread <threadTs>`, reply with "
                 "`reply --channel {c} --thread <threadTs>`. This scanned the most "
                 "recent {n} messages only — a thread whose PARENT is older than that "
                 "will not be listed, and that absence is not evidence it does not "
                 "exist. Raise --limit to look further back."
                 ).format(c=channel, n=len(msgs)),
    }, indent=2))


def upload_file(token, channel, path, thread_ts=None, comment=None):
    """Upload one file using Slack's three-step external flow.

    files.upload was retired, so there is no single-call path any more:
      1. files.getUploadURLExternal — reserve a URL and a file id
      2. POST the bytes to that URL (not a Slack API endpoint)
      3. files.completeUploadExternal — attach it to the channel

    Step 2 is a plain upload to a returned host, so it does not go through
    call() and gets its own error handling.
    """
    blob = path.read_bytes()

    ok_flag, payload = call("files.getUploadURLExternal", token, params={
        "filename": path.name, "length": len(blob)})
    if not ok_flag:
        die(explain(payload, "files.getUploadURLExternal"))
    upload_url = payload.get("upload_url")
    file_id = payload.get("file_id")
    if not upload_url or not file_id:
        die("Slack accepted the upload request but returned no upload URL or file id. "
            "Nothing was uploaded.")

    req = urllib.request.Request(upload_url, data=blob, method="POST")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if not 200 <= resp.status < 300:
                die(f"Uploading the file bytes failed with HTTP {resp.status}. "
                    "The file was reserved but not stored.")
    except urllib.error.HTTPError as err:
        die(f"Uploading the file bytes failed with HTTP {err.code}. "
            "The file was reserved but not stored.")
    except urllib.error.URLError as err:
        raise RuntimeError(f"could not reach the upload host: {err.reason}") from err

    body = {"files": [{"id": file_id, "title": path.name}], "channel_id": channel}
    if thread_ts:
        body["thread_ts"] = thread_ts
    if comment:
        body["initial_comment"] = comment
    ok_flag, payload = call("files.completeUploadExternal", token, body_json=body)
    if not ok_flag:
        die(explain(payload, "files.completeUploadExternal"))
    files = payload.get("files") or []
    return {"id": (files[0].get("id") if files else file_id),
            "name": (files[0].get("title") if files else path.name)}


def cmd_post(values, channel_flag, text, thread_ts=None, file_paths=None,
             as_name=None, icon=None):
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)

    safe, defanged = defang_broadcasts(text or "")

    uploaded = []
    if file_paths:
        for fp in file_paths:
            path = Path(fp)
            if not path.is_file():
                die(f"File not found: {fp}")
            uploaded.append(upload_file(token, channel, path, thread_ts,
                                        comment=safe if safe.strip() else None))
        # completeUploadExternal already posted the file into the channel with
        # the text as its comment, so posting the text again would duplicate it.
        print(json.dumps({
            "ok": True, "channel": channel, "thread": thread_ts,
            "posted": {"files": uploaded, "text": safe if safe.strip() else None},
            "defangedBroadcasts": defanged,
        }, indent=2))
        return

    if not safe.strip():
        die("Nothing to post.")

    body = {"channel": channel, "text": safe}
    if thread_ts:
        body["thread_ts"] = thread_ts
    if as_name:
        body["username"] = as_name
    if icon:
        # A URL is an icon_url; anything else is treated as an emoji name and
        # normalised to :name: so both `robot_face` and `:robot_face:` work.
        if icon.startswith("http://") or icon.startswith("https://"):
            body["icon_url"] = icon
        else:
            body["icon_emoji"] = icon if icon.startswith(":") else f":{icon}:"

    ok_flag, payload = call("chat.postMessage", token, body_json=body)
    if not ok_flag:
        die(explain(payload, f"chat.postMessage to {channel}"))

    out = {
        "ok": True, "channel": payload.get("channel") or channel,
        "thread": thread_ts,
        "posted": {"ts": payload.get("ts"),
                   "text": (payload.get("message") or {}).get("text")},
        "defangedBroadcasts": defanged,
    }
    if defanged:
        out["note"] = ("Rewrote " + ", ".join("<!%s>" % d for d in defanged) +
                       " to plain text so this bot cannot notify the workspace on "
                       "behalf of text it did not write.")
    if as_name or icon:
        out["note"] = (out.get("note", "") + " Posted with a custom identity "
                       "(chat:write.customize). The message still comes from this "
                       "app; the name and icon are per-message decoration, and Slack "
                       "shows an APP label next to it.").strip()
    print(json.dumps(out, indent=2))


def cmd_reply(values, channel_flag, thread_ts, text):
    """Reply inside a thread. --thread is required and is a parent message ts."""
    if not thread_ts:
        die("reply needs --thread <threadTs>, the ts of the message you are "
            "replying under. Find one with: python3 bot.py threads")
    cmd_post(values, channel_flag, text, thread_ts=thread_ts)


def cmd_edit(values, channel_flag, message_ts, text):
    """Edit a message this bot sent. Slack permits editing only your own."""
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)
    if not message_ts:
        die("edit needs --message <ts>")
    if not text.strip():
        die('edit needs the new text: python3 bot.py edit --message TS "corrected"')

    safe, defanged = defang_broadcasts(text)
    ok_flag, payload = call("chat.update", token, body_json={
        "channel": channel, "ts": message_ts, "text": safe})
    if not ok_flag:
        die(explain(payload, f"chat.update for {message_ts}"))
    print(json.dumps({"ok": True, "channel": channel,
                      "edited": {"ts": payload.get("ts"),
                                 "text": (payload.get("message") or {}).get("text")},
                      "defangedBroadcasts": defanged}, indent=2))


def cmd_delete(values, channel_flag, message_ts):
    """Delete a message this bot sent."""
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)
    if not message_ts:
        die("delete needs --message <ts>")

    ok_flag, payload = call("chat.delete", token, body_json={
        "channel": channel, "ts": message_ts})
    if not ok_flag:
        die(explain(payload, f"chat.delete for {message_ts}"))
    print(json.dumps({"ok": True, "channel": channel,
                      "deleted": payload.get("ts") or message_ts}, indent=2))


def cmd_react(values, channel_flag, action, message_ts, emoji):
    """Add, remove, or list reactions.

    Slack names an emoji WITHOUT colons — `thumbsup`, not `:thumbsup:`. Both are
    accepted here and normalised, because the colon form is what people copy out
    of Slack and passing it through unchanged fails with an unhelpful error.
    """
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)
    if not message_ts:
        die("react needs --message <ts>")

    if action == "list":
        ok_flag, payload = call("reactions.get", token,
                                params={"channel": channel, "timestamp": message_ts})
        if not ok_flag:
            die(explain(payload, f"reactions.get for {message_ts}"))
        msg = payload.get("message") or {}
        mine = self_id(token)
        print(json.dumps({
            "ok": True, "channel": channel, "message": message_ts,
            # `me` answers "did THIS bot react" — the only reaction it can
            # remove. null means this bot's own ID could not be read, which is
            # not the same as a no.
            "reactions": [
                {"emoji": r.get("name"), "count": r.get("count"),
                 "users": r.get("users") or [],
                 "me": (mine in (r.get("users") or [])) if mine else None}
                for r in (msg.get("reactions") or [])
            ],
        }, indent=2))
        return

    if not emoji:
        die(f"react {action} needs --emoji <name>  (Slack names have no colons: "
            "thumbsup, white_check_mark, eyes)")
    name = emoji.strip().strip(":")

    method = "reactions.add" if action == "add" else "reactions.remove"
    ok_flag, payload = call(method, token, body_json={
        "channel": channel, "timestamp": message_ts, "name": name})
    if not ok_flag:
        err = payload.get("error")
        if err == "already_reacted":
            die("already_reacted — this bot has already added that reaction. Slack "
                "counts one reaction per emoji per user.")
        if err == "no_reaction":
            die("no_reaction — this bot has not added that reaction, so there is "
                "nothing to remove. A bot can only remove its OWN reactions.")
        if err == "invalid_name":
            die(f"invalid_name — Slack does not recognise the emoji {name!r}. Use the "
                "short name without colons, and note that custom emoji exist only in "
                "the workspace that defined them.")
        die(explain(payload, f"{method} for {message_ts}"))
    print(json.dumps({"ok": True, "channel": channel, "message": message_ts,
                      "emoji": name, "action": action}, indent=2))


def cmd_pin(values, channel_flag, action, message_ts):
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)

    if action == "list":
        ok_flag, payload = call("pins.list", token, params={"channel": channel})
        if not ok_flag:
            die(explain(payload, f"pins.list for {channel}"))
        items = payload.get("items") or []
        print(json.dumps({
            "ok": True, "channel": channel,
            "pinned": [
                {"ts": (i.get("message") or {}).get("ts"),
                 "author": (i.get("message") or {}).get("user"),
                 "text": (i.get("message") or {}).get("text"),
                 "type": i.get("type")}
                for i in items
            ],
        }, indent=2))
        return

    if not message_ts:
        die(f"pin {action} needs --message <ts>")
    method = "pins.add" if action == "add" else "pins.remove"
    ok_flag, payload = call(method, token, body_json={
        "channel": channel, "timestamp": message_ts})
    if not ok_flag:
        err = payload.get("error")
        if err == "already_pinned":
            die("already_pinned — that message is already pinned.")
        if err == "no_pin":
            die("no_pin — that message is not pinned, so there is nothing to remove.")
        die(explain(payload, f"{method} for {message_ts}"))
    print(json.dumps({"ok": True, "channel": channel, "message": message_ts,
                      "action": action}, indent=2))


def cmd_users(values, user_id):
    """Look up one person, or list the workspace's members."""
    token = bot_token(values)

    if user_id:
        ok_flag, payload = call("users.info", token, params={"user": user_id})
        if not ok_flag:
            die(explain(payload, f"users.info for {user_id}"))
        user = payload.get("user") or {}
        profile = user.get("profile") or {}
        print(json.dumps({"ok": True, "user": {
            "id": user.get("id"), "name": user.get("name"),
            "displayName": profile.get("display_name"),
            "realName": profile.get("real_name"),
            "bot": bool(user.get("is_bot")),
            "deleted": bool(user.get("deleted")),
        }}, indent=2))
        return

    members, cursor = [], None
    for _ in range(20):
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        ok_flag, payload = call("users.list", token, params=params)
        if not ok_flag:
            die(explain(payload, "users.list"))
        members.extend(payload.get("members") or [])
        cursor = ((payload.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break

    print(json.dumps({"ok": True, "count": len(members), "members": [
        {"id": m.get("id"), "name": m.get("name"),
         "displayName": (m.get("profile") or {}).get("display_name"),
         "realName": (m.get("profile") or {}).get("real_name"),
         "bot": bool(m.get("is_bot")), "deleted": bool(m.get("deleted"))}
        for m in members
    ]}, indent=2))


def cmd_invite(values, channel_flag, user_ids, emails):
    """Invite people to a channel.

    Two different Slack calls behind one verb, because they are the same
    intention: conversations.invite for people already in the workspace, and
    conversations.inviteShared for an email address outside it. Both require the
    bot to already be a member of the target channel.
    """
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)
    if not user_ids and not emails:
        die("invite needs --user <U…> (someone in this workspace) or --email "
            "<address> (Slack Connect, for someone outside it). Repeat either "
            "flag for several people.")

    results = {"invited": [], "invitedByEmail": []}

    if user_ids:
        ok_flag, payload = call("conversations.invite", token, body_json={
            "channel": channel, "users": ",".join(user_ids)})
        if not ok_flag:
            err = payload.get("error")
            if err == "already_in_channel":
                die("already_in_channel — at least one of those people is already in "
                    "the channel. Slack refuses the whole call, so nobody was added.")
            die(explain(payload, "conversations.invite"))
        results["invited"] = user_ids

    if emails:
        for email in emails:
            ok_flag, payload = call("conversations.inviteShared", token, body_json={
                "channel": channel, "emails": [email]})
            if not ok_flag:
                err = payload.get("error")
                if err == "recipients_not_specified":
                    die("recipients_not_specified — no email address reached Slack. "
                        "Pass one per person: --email one@example.com --email two@example.com")
                die(explain(payload, f"conversations.inviteShared for {email}"))
            results["invitedByEmail"].append(email)

    print(json.dumps({
        "ok": True, "channel": channel, **results,
        "note": ("An invitation is a request, not a membership. People appear in the "
                 "channel once they accept. Slack Connect invitations may also need "
                 "approval from an admin on either side."),
    }, indent=2))


def cmd_dm(values, action, user_id, text, limit):
    """Send or read a direct message with one person.

    conversations.open turns a user ID into a DM channel ID. It is called every
    time rather than cached: the DM channel is stable, but caching it here would
    mean a stale file could send a message to the wrong person.
    """
    token = bot_token(values)
    if not user_id:
        die("dm needs --user <U…>. Find the ID with: python3 bot.py users")

    ok_flag, payload = call("conversations.open", token,
                            body_json={"users": user_id})
    if not ok_flag:
        die(explain(payload, f"conversations.open with {user_id}"))
    dm_channel = ((payload.get("channel") or {}).get("id"))
    if not dm_channel:
        die("Slack opened no DM channel for that user and reported no error.")

    if action == "send":
        if not text.strip():
            die('dm send needs text: python3 bot.py dm send --user U123 "message"')
        safe, defanged = defang_broadcasts(text)
        ok_flag, payload = call("chat.postMessage", token, body_json={
            "channel": dm_channel, "text": safe})
        if not ok_flag:
            die(explain(payload, "chat.postMessage to a DM"))
        print(json.dumps({"ok": True, "dmChannel": dm_channel, "to": user_id,
                          "posted": {"ts": payload.get("ts"), "text": safe},
                          "defangedBroadcasts": defanged}, indent=2))
        return

    msgs = fetch_history(token, dm_channel, limit)
    ordered = list(reversed(msgs))
    names = resolve_names(token, ordered)
    print(json.dumps({"ok": True, "dmChannel": dm_channel, "with": user_id,
                      "count": len(ordered),
                      "messages": [describe_message(m, names) for m in ordered]},
                     indent=2))


def cmd_verify(values, channel_flag):
    """
    End-to-end check: authenticate, confirm membership, post, read it back.

    The stages are ordered so each one fails for exactly one reason, and the
    membership stage comes BEFORE the post so a not_in_channel failure is
    reported as what it is rather than as a mysterious posting error.

    A NOTE ON WHAT THIS DOES NOT CHECK, because the Discord side of this kit
    spends its verify doing it: Discord's MESSAGE CONTENT intent silently blanks
    every message body, so its verify has to find a message written by somebody
    else and inspect it. Slack has NO privileged content intent and no
    equivalent failure. Do not port that check here and do not go looking for
    the symptom — Slack's analogous silent failure is channel membership, which
    is stage 2 below.

    This POSTS A REAL MESSAGE to the channel. That is visible to everyone in it.
    """
    token = bot_token(values)
    channel = resolve_channel(values, channel_flag)
    steps = []

    ok_flag, auth = call("auth.test", token)
    if not ok_flag:
        die(explain(auth, "auth.test"))
    me = auth.get("user_id")
    steps.append({"step": "authenticate", "ok": True, "bot": auth.get("user"),
                  "workspace": auth.get("team")})

    ok_flag, info = call("conversations.info", token, params={"channel": channel})
    if not ok_flag:
        steps.append({"step": "membership", "ok": False,
                      "detail": explain(info, f"conversations.info for {channel}")})
        print(json.dumps({"ok": False, "steps": steps, "summary":
                          "Could not inspect the channel. Nothing was posted."},
                         indent=2))
        sys.exit(1)

    chan = info.get("channel") or {}
    is_member = bool(chan.get("is_member"))
    steps.append({"step": "membership", "ok": is_member,
                  "channel": chan.get("name"), "private": bool(chan.get("is_private")),
                  "detail": ("The bot is a member." if is_member else
                             "NOT A MEMBER. Nothing was posted, because posting would "
                             "have failed for this reason and reported something less "
                             "specific. " + ("A human must /invite it — private "
                             "channels have no self-join." if chan.get("is_private")
                             else "Run: python3 bot.py join --channel " + channel))})
    if not is_member:
        print(json.dumps({"ok": False, "steps": steps, "summary":
                          "The bot can see the channel but is not in it. This is the "
                          "failure Slack is quietest about, and it is a membership "
                          "problem, not a scope or a code problem."}, indent=2))
        sys.exit(1)

    marker = f"chat-platform-bot-kit online — {auth.get('user')} reporting in."
    ok_flag, posted = call("chat.postMessage", token,
                           body_json={"channel": channel, "text": marker})
    if not ok_flag:
        steps.append({"step": "post", "ok": False,
                      "detail": explain(posted, "chat.postMessage")})
        print(json.dumps({"ok": False, "steps": steps,
                          "summary": "The bot is in the channel but could not post."},
                         indent=2))
        sys.exit(1)
    posted_ts = posted.get("ts")
    steps.append({"step": "post", "ok": True, "ts": posted_ts})

    msgs = fetch_history(token, channel, 50)
    seen = any(m.get("ts") == posted_ts for m in msgs)
    steps.append({"step": "read", "ok": seen, "messagesSeen": len(msgs),
                  "detail": ("Read the channel back and found the message just "
                             "posted." if seen else
                             "Posted successfully, but the message was not in the "
                             "next 50 messages of history. That is unexpected; "
                             "history may be lagging, or the channel is very busy.")})

    healthy = seen
    print(json.dumps({
        "ok": healthy,
        "steps": steps,
        "posted": {"ts": posted_ts, "text": marker,
                   "note": "A real message was posted to the channel and left there. "
                           "Delete it with: python3 bot.py delete --channel "
                           f"{channel} --message {posted_ts}"},
        "summary": ("Setup is working. The bot authenticated, is a member, posted, "
                    "and read the channel back." if healthy else
                    "The bot posted but could not confirm the message by reading "
                    "back. See the read step."),
    }, indent=2))
    sys.exit(0 if healthy else 1)


# --------------------------------------------------------------------------

def take_flag(args, name):
    """Remove '--name value' from args in place and return the value, or None.

    Flags are stripped BEFORE positionals are read, so `post --channel C123 "hi"`
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


def take_switch(args, name):
    """Remove a valueless '--name' from args in place. True if it was there."""
    if name in args:
        args.remove(name)
        return True
    return False


def positive_int(raw, flag, default):
    if raw is None:
        return default
    try:
        val = int(raw)
    except ValueError:
        die(f"{flag} needs a number, got {raw!r}")
    if val < 1:
        die(f"{flag} must be 1 or greater, got {val}")
    return val


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return

    values = load_env()
    command = argv[0]
    args = list(argv[1:])

    try:
        # --channel is special: `check --channel C` and `check --member C` use it
        # as a stage selector AND a value, so it is read before anything else.
        channel_flag = take_flag(args, "--channel")
        member_flag = take_flag(args, "--member")
        thread_flag = take_flag(args, "--thread")
        message_flag = take_flag(args, "--message")
        emoji_flag = take_flag(args, "--emoji")
        limit_flag = take_flag(args, "--limit")
        as_flag = take_flag(args, "--as")
        icon_flag = take_flag(args, "--icon")
        user_flags = []
        while "--user" in args:
            user_flags.append(take_flag(args, "--user"))
        email_flags = []
        while "--email" in args:
            email_flags.append(take_flag(args, "--email"))
        file_flags = []
        while "--file" in args:
            file_flags.append(take_flag(args, "--file"))
        # `check --user` is a bare switch, while `invite --user U123` takes a
        # value. The loop above consumes the valued form; a bare trailing --user
        # would have died there, so it is handled as a switch first.
        user_switch = take_switch(args, "--user")

        if command == "check":
            if member_flag:
                cmd_check(values, "member", member_flag)
            elif channel_flag:
                cmd_check(values, "channel", channel_flag)
            elif user_switch or (user_flags and not user_flags[0]):
                cmd_check(values, "user", None)
            else:
                cmd_check(values, "bot", None)
        elif command == "channels":
            cmd_channels(values)
        elif command == "join":
            cmd_join(values, channel_flag)
        elif command == "read":
            cmd_read(values, channel_flag, thread_flag,
                     positive_int(limit_flag, "--limit", 20))
        elif command == "threads":
            cmd_threads(values, channel_flag,
                        positive_int(limit_flag, "--limit", 100))
        elif command == "post":
            text = read_message_text(args)
            if not text.strip() and not file_flags:
                die('Nothing to post. Pass text as an argument, or pipe it in:\n'
                    '  python3 bot.py post "your message"\n'
                    '  echo "your message" | python3 bot.py post\n'
                    '  python3 bot.py post < message.txt')
            cmd_post(values, channel_flag, text, thread_flag, file_flags,
                     as_flag, icon_flag)
        elif command == "reply":
            text = read_message_text(args)
            if not text.strip():
                die('Nothing to reply with. Pass text as an argument, or pipe it in.')
            cmd_reply(values, channel_flag, thread_flag, text)
        elif command == "edit":
            cmd_edit(values, channel_flag, message_flag, read_message_text(args))
        elif command == "delete":
            cmd_delete(values, channel_flag, message_flag)
        elif command == "react":
            action = args[0] if args else ""
            if action not in ("add", "remove", "list"):
                die("react needs an action: add | remove | list\n"
                    "  python3 bot.py react add --message TS --emoji thumbsup")
            cmd_react(values, channel_flag, action, message_flag, emoji_flag)
        elif command == "pin":
            action = args[0] if args else ""
            if action not in ("add", "remove", "list"):
                die("pin needs an action: add | remove | list\n"
                    "  python3 bot.py pin add --message <ts>")
            cmd_pin(values, channel_flag, action, message_flag)
        elif command == "users":
            cmd_users(values, args[0] if args else None)
        elif command == "user":
            target = user_flags[0] if user_flags else (args[0] if args else None)
            if not target:
                die("user needs an id: python3 bot.py user <U…>")
            cmd_users(values, target)
        elif command == "invite":
            cmd_invite(values, channel_flag, user_flags, email_flags)
        elif command == "dm":
            action = args[0] if args else ""
            if action not in ("send", "read"):
                die("dm needs an action: send | read\n"
                    '  python3 bot.py dm send --user U123 "message"\n'
                    "  python3 bot.py dm read --user U123")
            rest = args[1:]
            cmd_dm(values, action, user_flags[0] if user_flags else None,
                   read_message_text(rest) if action == "send" else "",
                   positive_int(limit_flag, "--limit", 20))
        elif command == "verify":
            cmd_verify(values, channel_flag)
        else:
            die(f"Unknown command '{command}'. Run: python3 bot.py --help")
    except RuntimeError as err:
        die(str(err))


if __name__ == "__main__":
    main()
