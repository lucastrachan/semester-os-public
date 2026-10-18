# In-app chat per listing: contract (Phase 8b) — owner: Admin agent

Status: **coded and tested offline, not deployed, not wired.** Builder wires the routes (bottom). Mobile and Designer: code against these shapes. Errors are `{ "error": code, "message": text }`. JWT (student pool) on every route here. No public routes.

Principles: one conversation per (listing, buyer). Only those two people can read it. Neither side ever receives the other's email or id: only a short display name and the campus. Messages are plain text (no links, no images), at most 1000 characters. Clients must render message text as text only (never HTML, never auto-link). Message text is never sent to a model. No push notifications: clients poll (see "Polling").

## Objects

```
Conversation = {
  id: "ab12cd34",
  role: "buyer" | "seller",                     // what the caller is in this conversation
  listing: { id, title, price?, status? },      // price and status only in GET /conversations/{id} (live values)
  other: { name: "Sam", campus: { id, name, shortName } },
  status: "open" | "closed",
  closedReason: null | "blocked" | "listing_removed" | "listing_flagged" | "campus_unavailable" | "admin" | "banned",
  canSend: true | false,
  lastMessage: { from: "me"|"them"|"system", text: "<=80 chars preview", at } | null,
  unread: 0,                                    // messages from the other side (or system) you have not fetched
  createdAt, lastMessageAt
}
Message = { id: "<opaque cursor>", from: "me" | "them" | "system", text, at }
```
`other.name` for a seller who never set a name is `"Student"`. Nothing in these objects identifies a person beyond the display name and campus. Blocking is silent: the blocked person just sees the conversation closed (`closedReason: "blocked"` is shown to both sides; it does not say who blocked).

## POST /listings/{id}/conversations

Body: `{ message }` (1-1000 chars, no links). The buyer starts the chat with a first message.
- `201 { conversation, messages: [Message], created: true }` for a new conversation.
- `200 { conversation, messages: [Message], created: false }` if you already have an open conversation on this listing (your message is added to it).
- `409 conversation_closed` if your conversation on this listing is closed.
Rules: the listing must be `available`, not flagged, not a demo listing (`400 demo_listing`: there is no seller), visible to you under the campus/network rules (else `404 not_found`), and not yours (`400 own_listing`). If the seller blocked you: `403 cannot_message` (no reason given). Banned account: `403 account_restricted`.
Limits: `429 rate_limited` (per minute), `429 daily_cap` (30 new conversations a day, 200 messages a day), `429 spam` (the same text of 15+ characters more than 3 times a day), `400 validation_error` (empty, too long, links, repeated message).

## GET /conversations

Query: `status=open|closed|all` (default `all`), `limit` (default 30, max 50).
`200 { conversations: Conversation[] (newest activity first), unreadTotal }`. Built from your inbox pointers, so it is cheap; `status` there reflects blocks and admin closes (a listing removed or flagged later is reflected once you open the conversation).

## GET /conversations/unread

`200 { unread: <total across conversations> }`. Cheap; for the tab badge.

## GET /conversations/{id}?after=<cursor>&limit=50

Messages oldest first. Omit `after` for the first fetch (the last 50 messages, oldest first); pass the previous response's `nextCursor` to get only newer messages (this is the polling call). `200 { conversation, messages: Message[], nextCursor: "<cursor>" | null }`. A call marks the conversation read for you (`unread` becomes 0). `nextCursor` is the id of the newest message returned (or the `after` you sent when there is nothing new): always pass it back.
`404 not_found` if you are not one of the two participants or it does not exist (the same answer, so existence is never confirmed). `400 validation_error` for a malformed cursor.

## POST /conversations/{id}/messages

Body: `{ text }`. `201 { message, canSend: true }`.
Errors: `403 conversation_closed` (blocked, listing removed or flagged, campus unavailable, admin closed), `404 not_found`, `409 conversation_full` (500 messages), `400 validation_error` (empty, over 1000, links, same text as your previous message in this conversation), `429 rate_limited | daily_cap | spam`, `403 account_restricted`.
When the seller marks the listing sold, the buyer's open conversations get an automatic `system` message ("The seller marked this item as sold.").

## POST /conversations/{id}/block

No body. Closes the conversation for both sides and remembers the block: the person you blocked can no longer start new conversations with you. `200 { blocked: true }` (idempotent).

## POST /conversations/{id}/report

Body: `{ reason: "spam|harassment|scam|inappropriate|other", note?: <=200 chars }`. Saves a report for the admin queue with the last 10 messages as evidence. One report per person per conversation (repeats accepted, counted once). `200 { reported: true }`. `429` after 10 reports a day.
Listing reports (`POST /listings/{id}/report`, MARKETPLACE_API.md) now also land in the same admin queue.

## Polling (no push notifications)

- Open thread: `GET /conversations/{id}?after=<nextCursor>` every **5 seconds** while the thread is on screen and the app is in the foreground; back off to 15 seconds after 2 minutes without new messages; stop when the app is backgrounded; fetch once immediately after sending and when returning to the foreground.
- Inbox screen: `GET /conversations` every **30 seconds** while shown.
- Tab badge: `GET /conversations/unread` every **60 seconds** in the foreground.
Reads are not rate limited per request, but a client that polls faster than this wastes the shared Lambda concurrency (the account limit is small).

## Item layout (DynamoDB single table)

| Item | pk | sk | Notes |
|---|---|---|---|
| Conversation | `CONVO#{cid}` | `META` | `id, listingId, listingTitle, listingTenantId, sellerSub, buyerSub (internal), sellerName, buyerName, sellerCampus{id,name,shortName}, buyerCampus, status, closedReason, blockedBy?, msgCount, createdAt, lastMessageAt, ttl` |
| Message | `CONVO#{cid}` | `MSG#{iso}#{rand4}` | `from (buyer|seller|system), text, at, ttl`. The sort key without `MSG#` is the cursor |
| Inbox pointer | `USER#{sub}` | `CONV#{cid}` | `id, role, listingId, listingTitle, otherName, otherCampus, status, closedReason, lastAt, lastPreview, lastFrom, unread, createdAt, ttl`. `unread` is changed with `ADD` and conditional writes |
| One chat per listing and buyer | `USER#{buyerSub}` | `CVLK#{listingId}` | `cid`; created with `attribute_not_exists`, so two simultaneous starts cannot make two conversations |
| Listing to chats | `LISTING#{listingId}` | `CONV#{cid}` | `cid`; used for the "sold" notice |
| Block | `USER#{blocker}` | `BLOCK#{sha256(other)[:16]}` | `at` |
| Report queue | `REPORTS` | `R#{kind}#{targetId}#{reporterHash}` | `id, kind (listing|conversation), targetId, reason, note, evidence[] (conversation reports), reportedSub/reporterRole (admin only), status, createdAt, ttl 180 days` |
| Ban | `BANNED_USERS` | `U#{sub}` | `reason, by, at`. Checked by listings and messages routes; Builder: `/me` should also return 403 `account_restricted` |
| Counters | `USER#{sub}` | `CAP#convs#{day}`, `CAP#msgs#{day}`, `CAP#msgreports#{day}`, `SPAM#{hash}#{day}` | counters with `ttl` |

Retention: every message has `ttl` = 90 days after it was sent; the conversation, both pointers and the listing link are pushed to 90 days after the last message each time. Reports keep 180 days.

Delete-my-data (`lib/convos.delete_user_data(sub)` does all of this; call it from the account-deletion path): for every `USER#{sub}/CONV#` pointer delete the conversation (`CONVO#{cid}` META and MSG# items, the `LISTING#{lid}/CONV#{cid}` link, the other person's pointer), then the user's own `CONV#`, `CVLK#`, `BLOCK#` and counter items. The other participant loses that chat; this is deliberate (no orphan messages). Also delete their listings as described in MARKETPLACE_API.md.

## Admin site additions (in `admin/` and `backend/admin_api.py`)

A **Reports** view lists the queue (open first) with the evidence; actions: hide or unhide a listing, close a conversation, ban or unban a user, mark a report resolved. Every list and action is audited. Routes (staff token only): `GET /admin/reports?status=open|resolved|all`, `POST /admin/reports/{id}/resolve`, `POST /admin/listings/{id}/hide|unhide`, `POST /admin/conversations/{id}/close`, `POST /admin/users/{sub}/ban|unban`. A ban also removes the user's active listings and closes their conversations.

## Wiring for Builder (Admin did not touch api.py or stack.py)

`backend/api.py`:
```python
import messages_api
...
# protected section, after `sub = _get_sub(event)`:
m = re.fullmatch(r"/listings/([a-z0-9]{8})/conversations", path)
if m and method == "POST":
    return messages_api.start_conversation(event, sub, m.group(1))
if path == "/conversations" and method == "GET":
    return messages_api.list_conversations(event, sub)
if path == "/conversations/unread" and method == "GET":
    return messages_api.unread_count(event, sub)
m = re.fullmatch(r"/conversations/([a-z0-9]{8})", path)
if m and method == "GET":
    return messages_api.get_conversation(event, sub, m.group(1))
m = re.fullmatch(r"/conversations/([a-z0-9]{8})/(messages|block|report)", path)
if m and method == "POST":
    return {"messages": messages_api.send_message, "block": messages_api.block_conversation,
            "report": messages_api.report_conversation}[m.group(2)](event, sub, m.group(1))
```
`/{proxy+}` (JWT) already covers all of these; the existing table role is enough (no new IAM). Account deletion: call `convos.delete_user_data(sub)`. `/me`: optionally return 403 `account_restricted` when `BANNED_USERS/U#{sub}` exists. The admin routes need no wiring (they go through `admin_api.handle`).

Tests: `python -I -m unittest discover -s backend/tests` from the repo root (`test_convos.py`, `test_messages_api.py`) and `python -I scripts/test_admin_api.py`.
