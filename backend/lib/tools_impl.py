"""Tutor tool implementations. Every call goes: ToolBudget.spend -> guard.validate_tool_call -> here.

Rules (SECURITY.md W2): no destructive tools, everything is read and written through a UserScopedDB view that is
pinned to the authenticated user, only this one class is touched, every write returns a visible action with an
undo recipe that the SERVER keeps (the client only ever sends an action id back).
"""
import time
from datetime import date, datetime, timedelta, timezone

from . import guard, memory, util

ACTION_TTL_SECONDS = 7 * 24 * 3600
MODEL_VIEW_PREFIXES = ("COURSE", "ASG", "ACT", "ACTION", "MEM", "MAT", "CHUNK")
_RESTORABLE = ("title", "dueDate", "dueTime", "done", "notes", "type", "dateSource")


def scoped_view(sub: str, backend) -> "guard.UserScopedDB":
    """The only database handle tools may use: this user's COURSE, ASG, ACT and ACTION items, never PROFILE or CAL."""
    return guard.UserScopedDB(sub, backend, allowed_prefixes=MODEL_VIEW_PREFIXES,
                              denied_prefixes=guard.MODEL_DENIED_PREFIXES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Tool specs offered to the model (Converse toolSpec). Their names must match guard.AGENT_TOOLS["class"].
def _spec(name, description, props, required=()):
    return {"toolSpec": {"name": name, "description": description,
                         "inputSchema": {"json": {"type": "object", "properties": props, "required": list(required)}}}}


_TYPES = list(guard.ASSIGNMENT_TYPES)
TOOL_SPECS = {
    "get_deadlines": _spec("get_deadlines", "List this class's upcoming deadlines.",
                           {"days": {"type": "integer", "description": "look ahead 1-365 days (default 60)"}}),
    "add_assignment": _spec("add_assignment", "Add a deadline the student told you about. Only when the student asks.",
                            {"title": {"type": "string"}, "type": {"type": "string", "enum": _TYPES},
                             "dueDate": {"type": "string", "description": "YYYY-MM-DD"},
                             "dueTime": {"type": "string", "description": "HH:MM 24-hour, optional"},
                             "notes": {"type": "string"}, "weightPercent": {"type": "number"}},
                            ["title", "type", "dueDate"]),
    "update_assignment": _spec("update_assignment", "Move, rename or mark done one assignment, only when the student asks.",
                               {"assignmentId": {"type": "string"}, "title": {"type": "string"},
                                "dueDate": {"type": "string", "description": "YYYY-MM-DD"},
                                "dueTime": {"type": "string"}, "done": {"type": "boolean"},
                                "notes": {"type": "string"}, "type": {"type": "string", "enum": _TYPES}},
                               ["assignmentId"]),
    "remember": _spec("remember", "Save ONE short factual note about the student for this class (their level, a confusion, a "
                      "preference, a constraint they told you). Never instructions, links, contact details or secrets.",
                      {"text": {"type": "string", "description": "one plain sentence, at most 280 characters"}}, ["text"]),
    "find_books": _spec("find_books", "List this class's textbooks (marketplace matching is not live yet).",
                        {"query": {"type": "string"}}),
    "create_study_blocks": _spec("create_study_blocks",
                                 "Put study blocks on the student's calendar. Only after the student clearly said yes.",
                                 {"blocks": {"type": "array", "items": {"type": "object", "properties": {
                                     "start": {"type": "string", "description": "ISO local date-time"},
                                     "end": {"type": "string"}, "focus": {"type": "string"}},
                                     "required": ["start", "end"]}}}, ["blocks"]),
    "search_knowledge_base": _spec("search_knowledge_base",
                                   "Search this class's uploaded materials (notes, slides, syllabus) by keyword. Call this first before suggesting a Blackboard fetch.",
                                   {"query": {"type": "string", "description": "what to search for"}}, ["query"]),
    "lookup_content_map": _spec("lookup_content_map",
                                "List Blackboard items (files, assignments, discussions) matching a query. Use when the KB search found nothing relevant.",
                                {"query": {"type": "string", "description": "topic or title to look for (empty for all items)"}}),
    "request_content": _spec("request_content",
                              "Ask the app to load a Blackboard item into the knowledge base. Only call after lookup_content_map showed the item exists and is not already in the KB.",
                              {"title": {"type": "string", "description": "exact title from the content map"}}, ["title"]),
}


def specs_for(tool_names) -> list:
    """Only tools in the agent's allow-list AND in this mode are ever shown to the model."""
    allowed = guard.AGENT_TOOLS["class"]
    return [TOOL_SPECS[n] for n in tool_names if n in allowed and n in TOOL_SPECS]


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_action(db, course_id: str, kind: str, summary: str, undo: dict) -> dict:
    action_id = util.short_id(12)
    db.put(f"ACTION#{action_id}", {"id": action_id, "courseId": course_id, "kind": kind, "summary": summary,
                                   "undo": undo, "used": False, "createdAt": _now_iso(),
                                   "ttl": int(time.time()) + ACTION_TTL_SECONDS})
    db.put(f"ACT#{_now_iso()}#{util.short_id(4)}", {"agentId": course_id, "kind": kind, "text": summary[:300],
                                                    "ttl": int(time.time()) + 30 * 24 * 3600})
    return {"id": action_id, "kind": kind, "summary": summary, "courseId": course_id, "undoable": True}


def _asg_item(course_id: str, title: str, typ: str, due_date, due_time, notes: str, weight, **extra) -> tuple:
    asg_id = util.short_id()
    item = {"id": asg_id, "courseId": course_id, "title": title, "type": typ, "dueDate": due_date, "dueTime": due_time,
            "weight": util.to_dynamo(weight), "dueText": "", "dateSource": "stated", "notes": notes,
            "done": False, "source": "agent", "createdAt": _now_iso(), **extra}
    return asg_id, item


def _own_asg(db, course_id: str, asg_id: str) -> dict:
    item = db.get(f"ASG#{course_id}#{asg_id}")
    if not item:
        raise guard.ToolRejected("not_found", "No such assignment in this class")
    return item


# ── tools ─────────────────────────────────────────────────────────────────────

def get_deadlines(args: dict, db, ctx: dict) -> tuple:
    today: date = ctx["today"]
    horizon = (today + timedelta(days=args["days"])).isoformat()
    items = db.query(f"ASG#{args['courseId'] or ctx['course_id']}#")
    rows = []
    for a in items:
        d = a.get("dueDate")
        if a.get("done") or (d and not (today.isoformat() <= d <= horizon)):
            continue
        rows.append({"assignmentId": a.get("id"), "title": a.get("title", ""), "type": a.get("type", "other"),
                     "dueDate": d, "dueTime": a.get("dueTime"), "dateSource": a.get("dateSource")})
    rows.sort(key=lambda r: (r["dueDate"] is None, r["dueDate"] or ""))
    return {"deadlines": rows[:40]}, None


def add_assignment(args: dict, db, ctx: dict) -> tuple:
    cid = args["courseId"]
    existing = db.query(f"ASG#{cid}#")
    if len(existing) >= 300:
        raise guard.ToolRejected("limit", "This class already has the maximum number of items")
    asg_id, item = _asg_item(cid, args["title"], args["type"], args["dueDate"], args["dueTime"], args["notes"],
                             args["weightPercent"])
    sk = f"ASG#{cid}#{asg_id}"
    db.put(sk, item)
    summary = f"Added {args['title']} on {args['dueDate']}"
    action = _save_action(db, cid, "assignment_added", summary, {"op": "delete_many", "sks": [sk]})
    return {"ok": True, "assignmentId": asg_id}, action


def update_assignment(args: dict, db, ctx: dict) -> tuple:
    cid, aid = args["courseId"], args["assignmentId"]
    sk = f"ASG#{cid}#{aid}"
    current = _own_asg(db, cid, aid)
    changes = {k: v for k, v in args.items() if k in _RESTORABLE and k != "dateSource"}
    previous = {k: current.get(k) for k in changes}
    if "dueDate" in changes or "dueTime" in changes:
        changes["dateSource"] = "stated"       # the student told us; no longer an estimate
        previous["dateSource"] = current.get("dateSource")
    changes["updatedBy"] = "agent"
    db.update(sk, changes)
    bits = []
    title = changes.get("title") or current.get("title", "assignment")
    if "dueDate" in changes:
        bits.append(f"to {changes['dueDate']}")
    if "done" in changes:
        bits.append("as done" if changes["done"] else "as not done")
    if "title" in changes:
        bits.append("renamed")
    summary = f"Updated {title} " + (" ".join(bits) if bits else "details")
    if "dueDate" in changes:
        summary = f"Moved {title} to {changes['dueDate']}"
    expected = {k: changes[k] for k in changes if k != "updatedBy"}
    action = _save_action(db, cid, "assignment_updated", summary,
                          {"op": "restore", "sk": sk, "set": previous, "expect": expected})
    return {"ok": True}, action


def find_books(args: dict, db, ctx: dict) -> tuple:
    cid = args["courseId"] or ctx["course_id"]
    course = db.get(f"COURSE#{cid}") or {}
    q = (args.get("query") or "").lower()
    books = [{"title": b.get("title", ""), "author": b.get("author", ""), "isbn": b.get("isbn", ""),
              "required": bool(b.get("required"))}
             for b in (course.get("books") or [])[:20]
             if not q or q in (b.get("title", "") + " " + b.get("author", "")).lower()]
    return {"books": books, "marketplaceMatches": "not available yet"}, None


def create_study_blocks(args: dict, db, ctx: dict) -> tuple:
    cid = args["courseId"]
    created, sks = [], []
    for b in args["blocks"]:
        s = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).replace(tzinfo=None)
        e = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).replace(tzinfo=None)
        if s.date() != e.date():
            raise guard.ToolRejected("cross_day", "A study block must start and end on the same day")
        focus = b["focus"] or "Study"
        asg_id, item = _asg_item(cid, f"Study: {focus}"[:160], "study", s.date().isoformat(), s.strftime("%H:%M"),
                                 "", None, endTime=e.strftime("%H:%M"), dateSource="stated")
        sk = f"ASG#{cid}#{asg_id}"
        db.put(sk, item)
        sks.append(sk)
        created.append({"assignmentId": asg_id, "date": item["dueDate"], "start": item["dueTime"], "end": item["endTime"]})
    n = len(sks)
    action = _save_action(db, cid, "study_blocks_created", f"Added {n} study block{'s' if n != 1 else ''} to your calendar",
                          {"op": "delete_many", "sks": sks})
    return {"ok": True, "blocks": created}, action


def remember(args: dict, db, ctx: dict) -> tuple:
    if ctx.get("remembered", 0) >= 1:
        raise guard.ToolRejected("limit", "Only one note can be saved per message")
    cid = args["courseId"]
    try:
        note = memory.add(db, cid, args["text"], "agent")
    except memory.NoteError as e:
        raise guard.ToolRejected("memory_full" if e.code == "memory_full" else "bad_note", e.message)
    if note.get("duplicate"):
        return {"ok": True, "note": "already remembered"}, None
    ctx["remembered"] = ctx.get("remembered", 0) + 1
    summary = "Remembered: " + note["text"][:80]
    action = _save_action(db, cid, "memory_added", summary,
                          {"op": "delete_note", "sk": f"MEM#{cid}#{note['id']}", "expect": {"text": note["text"]}})
    return {"ok": True, "noteId": note["id"]}, action


def search_knowledge_base(args: dict, db, ctx: dict) -> tuple:
    """BM25 search over uploaded materials; returns up to 4 matching chunks with titles."""
    from . import materials as _mat
    cid = args["courseId"]
    query = args["query"]
    nonce = ctx.get("nonce", "")
    ready, picked, _ = _mat.retrieve(db, cid, query)
    if not ready:
        return {"snippets": [], "note": "No materials uploaded for this class yet."}, None
    snippets = []
    seen: set = set()
    for c in picked:
        mat = ready.get(c.get("materialId") or "")
        if not mat:
            continue
        title = _mat.clean_title(mat.get("title"))
        text = guard.clean_text(c.get("text") or "", 600)
        snippets.append({"title": title, "excerpt": text})
        if c.get("materialId") not in seen:
            seen.add(c.get("materialId"))
            ctx.setdefault("sources", [])
            if len(ctx["sources"]) < 3 and _mat.INDEX_TITLE != title:
                ctx["sources"].append({"materialId": c["materialId"], "title": title})
    return {"snippets": snippets}, None


def lookup_content_map(args: dict, db, ctx: dict) -> tuple:
    """Return Blackboard index items matching the query (or all items if query is empty)."""
    from . import materials as _mat
    cid = args["courseId"]
    query = (args.get("query") or "").strip()
    links = _mat._index_links_for_course(db, cid)
    if not links:
        return {"items": [], "note": "No Blackboard content index uploaded for this class."}, None
    if query:
        q_toks, q_nums = _mat._fetch_tokens_norm(query)
        scored = [(l, _mat._link_score_norm(l["title"], q_toks, q_nums)) for l in links]
        items = [l for l, s in scored if s > 0]
        if not items:
            items = links[:10]
    else:
        items = links[:10]
    mats = {i["id"]: i for i in _mat.list_items(db, cid) if i.get("status") == "ready"}
    existing_norm = {_mat._norm_title(_mat.clean_title(m.get("title", ""))) for m in mats.values()}
    out = []
    for link in items[:10]:
        fetched = _mat._title_already_fetched(link["title"], existing_norm)
        out.append({"title": link["title"], "url": link["url"], "path": link.get("path", ""),
                    "already_in_kb": fetched})
    return {"items": out}, None


def request_content(args: dict, db, ctx: dict) -> tuple:
    """Model asks to load a Blackboard item. Server validates via deterministic guardrail.
    On success, sets ctx['pending_content'] so respond() can return fetchSuggestion."""
    from . import materials as _mat
    cid = args["courseId"]
    title = args["title"]
    links = _mat._index_links_for_course(db, cid)
    if not links:
        return {"error": "No Blackboard content index is available for this class.", "code": "no_index"}, None
    mats = {i["id"]: i for i in _mat.list_items(db, cid) if i.get("status") == "ready"}
    existing_norm = {_mat._norm_title(_mat.clean_title(m.get("title", ""))) for m in mats.values()}
    title_norm = _mat._norm_title(title)
    # Find best-matching link by title
    candidate = None
    for link in links:
        if _mat._norm_title(link["title"]) == title_norm:
            candidate = link
            break
    if candidate is None:
        # Fuzzy fallback: find the link whose norm title is most similar
        import difflib
        best, best_score = None, 0.0
        for link in links:
            r = difflib.SequenceMatcher(None, title_norm, _mat._norm_title(link["title"])).ratio()
            if r > best_score:
                best_score, best = r, link
        if best_score >= 0.7:
            candidate = best
    if candidate is None:
        return {"error": f"'{title}' not found in the Blackboard content map.", "code": "not_found"}, None
    if _mat._title_already_fetched(candidate["title"], existing_norm):
        return {"error": f"'{candidate['title']}' is already in your knowledge base.", "code": "already_in_kb"}, None
    # The model may only fetch what the STUDENT asked for: generic tool/container links never qualify, and the
    # item must match the student's own words (score or a distinctive shared word), not just the model's request.
    if _mat.is_generic_link_title(candidate["title"]):
        return {"error": f"'{candidate['title']}' is a generic course link, not the item the student asked for.",
                "code": "generic_item"}, None
    query = ctx.get("query") or ""
    if query:
        q_toks, q_nums = _mat._fetch_tokens_norm(query)
        score = _mat._link_score_norm(candidate["title"], q_toks, q_nums)
        t_set = set(_mat._fetch_tokens(candidate["title"]))
        shares_long = any(len(t) >= 4 and not t.isdigit() and t in t_set for t in q_toks)
        if score < _mat.MIN_FETCH_SCORE and not shares_long:
            return {"error": f"'{candidate['title']}' does not match what the student asked for. Tell the student you "
                             "do not see that item in the content map and ask for its exact title.",
                    "code": "not_relevant"}, None
    ctx["pending_content"] = candidate
    return {"ok": True, "title": candidate["title"], "note": "Say: 'Getting \"<title>\" from Blackboard, one moment.'"}, None


_IMPL = {
    "remember": remember,
    "get_deadlines": get_deadlines,
    "add_assignment": add_assignment,
    "update_assignment": update_assignment,
    "find_books": find_books,
    "create_study_blocks": create_study_blocks,
    "search_knowledge_base": search_knowledge_base,
    "lookup_content_map": lookup_content_map,
    "request_content": request_content,
}


def run_tool(name: str, raw_args, db, ctx: dict, budget: "guard.ToolBudget", agent: str = "class",
             allowed=None) -> tuple:
    """The whole path for one model tool request. Returns (result_for_model, action_or_None).
    Never raises ToolRejected: a rejection becomes an error result the model can read."""
    try:
        if allowed is not None and name not in allowed:   # this mode never offered the tool, so refuse it
            raise guard.ToolRejected("tool_not_allowed", "That tool is not available")
        budget.spend(name)
        if isinstance(raw_args, dict) and "courseId" not in raw_args and ctx.get("course_id"):
            raw_args = {**raw_args, "courseId": ctx["course_id"]}   # the specs do not ask the model for the class id
        args = guard.validate_tool_call(agent, name, raw_args, {**ctx, "db": db})
        return _IMPL[name](args, db, ctx)
    except guard.ToolRejected as e:
        return {"error": e.message, "code": e.code}, None
    except guard.ScopeError:
        return {"error": "That is not available", "code": "scope"}, None


# ── undo (called by chat_api with a server-held recipe, never a client-supplied one) ──

class UndoError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def undo_action(db, course_id: str, action_id: str) -> None:
    if not isinstance(action_id, str) or not action_id.isalnum() or len(action_id) > 24:
        raise UndoError(404, "not_found", "Nothing to undo")
    act = db.get(f"ACTION#{action_id}")
    if not act or act.get("courseId") != course_id:
        raise UndoError(404, "not_found", "Nothing to undo")
    if act.get("used"):
        raise UndoError(409, "already_undone", "That change was already undone")
    undo = act.get("undo") or {}
    prefix = f"ASG#{course_id}#"
    if undo.get("op") == "delete_many":
        sks = list(undo.get("sks") or [])
        for sk in sks:
            if not str(sk).startswith(prefix):
                raise UndoError(404, "not_found", "Nothing to undo")
            item = db.get(sk)
            if item and item.get("source") != "agent":
                raise UndoError(409, "changed_since", "That item was edited since, so it was left alone")
        for sk in sks:
            db.delete(sk)
    elif undo.get("op") == "restore":
        sk = undo.get("sk", "")
        if not str(sk).startswith(prefix):
            raise UndoError(404, "not_found", "Nothing to undo")
        item = db.get(sk)
        if not item:
            raise UndoError(409, "changed_since", "That item no longer exists")
        if any(item.get(k) != v for k, v in (undo.get("expect") or {}).items()):
            raise UndoError(409, "changed_since", "That item was edited since, so it was left alone")
        restore = {k: v for k, v in (undo.get("set") or {}).items() if k in _RESTORABLE}
        db.update(sk, {**restore, "updatedBy": "undo"})
    elif undo.get("op") == "delete_note":
        sk = undo.get("sk", "")
        if not str(sk).startswith(f"MEM#{course_id}#"):
            raise UndoError(404, "not_found", "Nothing to undo")
        item = db.get(sk)
        if not item or any(item.get(k) != v for k, v in (undo.get("expect") or {}).items()):
            raise UndoError(409, "changed_since", "That note was edited or removed since, so it was left alone")
        db.delete(sk)
    else:
        raise UndoError(404, "not_found", "Nothing to undo")
    db.update(f"ACTION#{action_id}", {"used": True})
    db.put(f"ACT#{_now_iso()}#{util.short_id(4)}", {"agentId": course_id, "kind": "undo",
                                                    "text": f"Undid: {act.get('summary', '')}"[:300],
                                                    "ttl": int(time.time()) + 30 * 24 * 3600})
