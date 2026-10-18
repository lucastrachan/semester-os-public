# Class materials with retrieval (the internal planning notes item C)

Owner: Class-agent platform module agent. Code: `backend/materials_api.py` (routes), `backend/lib/materials.py` (chunking, BM25, retrieval, storage), `backend/process_material.py` (async worker), hooks in `lib/tutor.py`, `lib/routing.py`, `master_api.py`, `courses_api.delete_course`. Status: **coded and tested offline, not routed, not deployed.**

Shapes match Designer's assumptions (the internal planning notes, "the internal planning notes milestone 2"): `POST /courses/{id}/materials {filename, contentType}` -> `{upload: {url, fields}}` (plus `material`), `GET -> {materials: [{id, filename, status, summary, pages, addedAt}]}`, `DELETE /courses/{id}/materials/{id}`. **Additive deviations only:** the list items also carry `title`, `kind`, `chars`, `chunkCount`, `error`; there is one extra route for pasted text; the upload response also carries the new `material` (status `processing`).

All routes need the student ID token; student from the token, class from the path (never the body). Errors: `{ "error": "<code>", "message": "<text safe to show>" }`. Render all text as text.

## Copyright and privacy (show this on the upload UI)
"Upload only your own course materials: your notes, and slides or readings your instructor gave you for this class. Don't upload books or other copyrighted material you don't have the right to copy. Files stay private to you and this class, are never shared with other students, and are deleted when you delete the class or the file." The list response carries this text as `notice` so the UI does not have to hard-code it.

## What it does
Each material gets a short summary and is split into searchable chunks (about 800 characters with overlap). On every tutor turn the server ranks this class's chunks against the student's message in code (BM25, pure Python, no vector database), puts the best few into the tutor's prompt as untrusted data with their titles, and the reply carries `sources` so the UI can show "Used: Lecture 4.pdf". The master router also sees material titles and summaries per class so a question about "Lecture 4" routes to the right class.

## Limits
- Types: PDF (`application/pdf`, text layer; scanned PDFs are rejected with a message to paste the text) or plain text (`text/plain`, `.txt` or `.md`), or pasted text.
- Size: PDF up to 10 MB (first 40 pages are read), text file up to 500 KB, pasted text up to 100,000 characters. Text kept per material: 100,000 characters (longer is truncated, `truncated: true`).
- Count: **30 materials per class**, and about 400,000 characters of text per class in total (`409 materials_full` / `409 class_text_full`).
- Rate: 5 per minute and 40 per day per student (bucket `material`, covers upload requests, pasted text and processing).
- Retrieval reads at most that class's chunks (bounded by the caps above), no cross-class and no cross-user access.

## `POST /courses/{id}/materials`  (start an upload)
Body: `{ "filename": "Lecture 4.pdf", "contentType": "application/pdf" | "text/plain", "title": "optional display title" }`.
`201 { "material": {..., "status": "processing"}, "upload": { "url": "...", "fields": {...} } }`
Then the browser POSTs a multipart form to `upload.url` with every `upload.fields` entry first and the `file` last (same as syllabi). The key is `materials/{sub}/{courseId}/{matId}.{pdf|txt}` and is chosen by the server; the form is valid for 5 minutes and size and type limited by S3 conditions. When the file lands, S3 notifies the worker; the material goes `processing -> ready` (or `error` with `error` text). Poll `GET /courses/{id}/materials` every few seconds while any item is `processing`. An upload that never arrived within 10 minutes is reported as `error` ("The upload didn't finish").
Errors: `400 validation_error` (type or filename), `404 not_found`, `409 materials_full`, `429 rate_limited`.

## `POST /courses/{id}/materials/text`  (paste notes)
Body: `{ "title": "My notes, week 4", "text": "..." }` (title 1-100 characters, text 20-100,000 characters). `202 { "material": {..., "status": "processing", "kind": "paste"} }`. Same polling. Errors as above plus `413 too_large`.

## `GET /courses/{id}/materials`
```
200 { "materials": [ { "id": "m1a2b3c4", "title": "Lecture 4", "filename": "Lecture 4.pdf", "kind": "pdf" | "text" | "paste",
                       "status": "processing" | "ready" | "error", "summary": "text or empty", "pages": 12 | null,
                       "chars": 18234, "chunkCount": 24, "truncated": false, "error": "" | "text safe to show",
                       "addedAt": "2026-10-17T21:00:00Z" } ],
      "limit": 30, "notice": "<copyright text above>" }
```
Newest first.

## `DELETE /courses/{id}/materials/{matId}`
`200 { "deleted": "m1a2b3c4" }`. Removes the metadata, every chunk and the stored file. `404 not_found` when the id is not this student's material in this class.

## Tutor and master responses: `sources`, `handoff.materials`
- `POST /courses/{id}/chat` and `POST /chat/master` (when a class agent answers) add `"sources": [ { "materialId": "m1a2b3c4", "title": "Lecture 4" } ]` to the response (empty array when nothing relevant was found). Sources are the materials whose chunks were put in front of the model, decided by code, not by anything the model says. Stored in chat history too.
- `/chat/master` handoff responses add `handoff.materials: [ { "id": "m1a2b3c4", "title": "Lecture 4" } ]` (the same materials) so the banner can show "Using: Lecture 4".
- `Course.knows.materialsCount` is kept equal to the number of `ready` materials.

## Safety rules implemented
- Chunk text, summaries and titles are untrusted: they are cleaned on the way in and wrapped with `guard.wrap_untrusted` and the per-request nonce on the way out; the system prompt says material is data. A document that says "ignore your rules" or contains fake `<<<END_UNTRUSTED>>>` markers stays inside the block.
- All reads and writes go through `guard.UserScopedDB` (partition `USER#{sub}`); ids from the request are validated (`^[a-z0-9]{8}$`) and checked against the class; the S3 key is derived on the server and re-checked against the item in the worker; the worker only accepts the exact key shape and only for a material still waiting for that upload.
- Hostile files: size caps (S3 condition and worker check), PDF page cap and pypdf errors become friendly messages, text files with binary content are rejected, an encrypted PDF is rejected, and nothing in a file is ever executed or fetched (no link following).
- The summary is one model call (main model chain) with the text wrapped; its output is sanitized and capped. If the model fails the material still becomes `ready` with a plain extract as the summary.

## Wiring for Builder
1. `api.py` protected section, before the generic `/courses/{id}` handlers:
```python
import materials_api   # top of file
r = materials_api.handle(event, sub, path, method)
if r is not None:
    return r
```
2. New Lambda `process_material.handler` (same code zip). Timeout 120 s, memory 512 MB, env like `process_syllabus` plus `MODEL_MAIN` and its fallbacks and `BEDROCK_CHAIN_BUDGET_SECONDS=60`. IAM: DynamoDB read/write on the table, `s3:GetObject` on `UPLOAD_BUCKET/materials/*`, Bedrock invoke on the model ids (same as process_syllabus).
3. API Lambda env: `PROCESS_MATERIAL_FN` (name of the function above), `UPLOAD_BUCKET` (exists). API Lambda IAM: `lambda:InvokeFunction` on that function, `s3:PutObject` is needed only by the presigned form (the Lambda role signs it, so it needs `s3:PutObject` on `materials/*`), and `s3:DeleteObject` on `materials/*`.
4. S3 notification on the upload bucket: `OBJECT_CREATED` with prefix `materials/` -> `process_material` (the existing `syllabi/` notification stays). Bucket CORS must allow POST from the web origin (same as syllabi).
5. Optional lifecycle rule: expire `materials/` objects after 400 days as a backstop (class deletion already removes them).
