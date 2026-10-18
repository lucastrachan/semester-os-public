"""Shared plumbing for the per-class data modules (history, memory, materials): scoped views and deletion.

Every item lives under pk USER#{sub}. Views are built with an allow-list of sort-key heads so a module can only touch
its own item types, and model-facing code never gets these views (tools get tools_impl.scoped_view).
"""
import re

from . import guard

CLASS_ID_RE = re.compile(r"^[a-z0-9]{8}$")
AGENT_ID_RE = re.compile(r"^(master|[a-z0-9]{8})$")


def view(sub: str, backend, *prefixes: str) -> "guard.UserScopedDB":
    return guard.UserScopedDB(sub, backend, allowed_prefixes=tuple(prefixes))


def delete_prefix(sub: str, backend, sk_prefix: str) -> int:
    """Delete every item under USER#{sub} whose sort key starts with sk_prefix (the prefix is built in code)."""
    pk = f"USER#{sub}"
    if hasattr(backend, "delete_prefix"):
        return backend.delete_prefix(pk, sk_prefix)
    items = backend.query_pk(pk, sk_prefix)
    for it in items:
        backend.delete_item(pk, it["sk"])
    return len(items)


def purge_course(sub: str, course_id: str, backend, s3=None, bucket: str | None = None) -> None:
    """Called when a class is deleted: chat history, memory notes, materials (metadata, chunks and S3 objects).
    Materials go first because their S3 keys are read from the metadata items."""
    if not CLASS_ID_RE.match(course_id):
        return
    from . import materials  # late import: avoids a cycle and keeps this module dependency free
    materials.purge_course(sub, course_id, backend, s3, bucket)
    for prefix in (f"CHAT#{course_id}#", f"CHATMETA#{course_id}", f"MEM#{course_id}#", f"MEMMETA#{course_id}"):
        delete_prefix(sub, backend, prefix)
