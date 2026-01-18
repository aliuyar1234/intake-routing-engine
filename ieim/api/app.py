from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from http import HTTPStatus
import html
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs, urlparse

from ieim.auth.config import AuthConfig, load_auth_config
from ieim.auth.oidc import AuthenticatedActor, OIDCTokenValidationError, OidcJwtValidator
from ieim.auth.rbac import RbacConfig, RolePermissions, load_rbac_config
from ieim.audit.file_audit_log import FileAuditLogger
from ieim.hitl.review_store import FileReviewStore
from ieim.hitl.service import HitlService
from ieim.runtime.config import validate_config_file
from ieim.runtime.health import ok
from ieim.runtime.paths import discover_repo_root
from ieim.raw_store import sha256_prefixed


def _stable_etag(data: bytes) -> str:
    return sha256_prefixed(data)


def _safe_cookie_value(value: str) -> str:
    # Minimal: prevent obvious header injection.
    return value.replace("\r", "").replace("\n", "")


def _cookie_kv(*, name: str, value: str, http_only: bool = True, same_site: str = "Lax") -> str:
    parts = [f"{name}={_safe_cookie_value(value)}", "Path=/", f"SameSite={same_site}"]
    if http_only:
        parts.append("HttpOnly")
    return "; ".join(parts)


def _cookie_clear(*, name: str) -> str:
    return f"{name}=; Path=/; Max-Age=0; SameSite=Lax; HttpOnly"


def _html_page(*, title: str, body_html: str) -> str:
    css = """
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; }
    a { color: #0b5fff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    pre { background: #0b1020; color: #e8eefc; padding: 12px; border-radius: 8px; overflow: auto; }
    .muted { color: #666; }
    .card { border: 1px solid #e6e6e6; border-radius: 10px; padding: 12px; margin: 12px 0; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; }
    .row > div { flex: 1; min-width: 280px; }
    input, textarea, select { width: 100%; padding: 8px; border: 1px solid #d7d7d7; border-radius: 8px; }
    textarea { min-height: 120px; }
    button { padding: 8px 12px; border-radius: 8px; border: 1px solid #d7d7d7; background: #fff; cursor: pointer; }
    button.primary { background: #0b5fff; border-color: #0b5fff; color: #fff; }
    .danger { color: #b42318; }
    """
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        f"<title>{html.escape(title)}</title>"
        f"<style>{css}</style>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"{body_html}"
        "</body></html>"
    )


@dataclass(frozen=True)
class ApiContext:
    repo_root: Path
    config_path: Path
    auth: AuthConfig
    rbac: RbacConfig
    oidc: OidcJwtValidator
    hitl_dir: Path
    artifact_roots: Sequence[Path]
    session_cookie_name: str = "ieim_access_token"


def _resolve_unique_artifact_path(*, roots: Sequence[Path], uri: str) -> Optional[Path]:
    if not uri:
        return None

    def safe_under(root: Path, rel: str) -> Optional[Path]:
        base = root.resolve()
        candidate = (base / rel).resolve()
        if candidate == base or base not in candidate.parents:
            return None
        if candidate.exists():
            return candidate
        return None

    matches: list[Path] = []
    if "/" in uri or "\\" in uri:
        rel = uri.replace("\\", "/").lstrip("/")
        for r in roots:
            p = safe_under(r, rel)
            if p is not None:
                matches.append(p)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous artifact uri (multiple roots): {uri}")
        return None

    for r in roots:
        base = r
        if not base.exists():
            continue
        for p in base.rglob(uri):
            matches.append(p)
            if len(matches) > 1:
                break
        if len(matches) > 1:
            break

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous artifact name (multiple matches): {uri}")
    return None


def _parse_if_match(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        v = v[1:-1]
    return v or None


def _idempotency_correction_id(*, review_item_id: str, actor_id: str, key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"http_correction:{review_item_id}:{actor_id}:{key}"))


def _make_handler(ctx: ApiContext):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_json(self, *, status: int, obj: Any, extra_headers: Optional[dict[str, str]] = None) -> None:
            payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        def _send_text(self, *, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
            payload = (text or "").encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_html(self, *, status: int, html_text: str, extra_headers: Optional[dict[str, str]] = None) -> None:
            payload = (html_text or "").encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        def _redirect(self, *, location: str, extra_headers: Optional[dict[str, str]] = None) -> None:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()

        def _read_json_body(self, *, max_bytes: int = 512 * 1024) -> dict[str, Any]:
            length_raw = self.headers.get("Content-Length")
            if length_raw is None:
                raise ValueError("missing Content-Length")
            try:
                length = int(length_raw)
            except Exception as e:
                raise ValueError("invalid Content-Length") from e
            if length < 0 or length > max_bytes:
                raise ValueError("request body too large")
            raw = self.rfile.read(length)
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception as e:
                raise ValueError("invalid JSON body") from e
            if not isinstance(obj, dict):
                raise ValueError("JSON body must be an object")
            return obj

        def _read_form_body(self, *, max_bytes: int = 64 * 1024) -> dict[str, str]:
            ctype = str(self.headers.get("Content-Type") or "")
            if "application/x-www-form-urlencoded" not in ctype:
                raise ValueError("unsupported content type")
            length_raw = self.headers.get("Content-Length")
            if length_raw is None:
                raise ValueError("missing Content-Length")
            try:
                length = int(length_raw)
            except Exception as e:
                raise ValueError("invalid Content-Length") from e
            if length < 0 or length > max_bytes:
                raise ValueError("request body too large")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            parsed = parse_qs(raw, keep_blank_values=True)
            out: dict[str, str] = {}
            for k, v in parsed.items():
                if not v:
                    continue
                out[str(k)] = str(v[0])
            return out

        def _extract_token(self) -> Optional[str]:
            auth = self.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                return auth.split(" ", 1)[1].strip()

            cookie = self.headers.get("Cookie") or ""
            if not cookie:
                return None
            parts = [p.strip() for p in cookie.split(";") if p.strip()]
            for p in parts:
                if "=" not in p:
                    continue
                k, v = p.split("=", 1)
                if k.strip() == ctx.session_cookie_name:
                    return v.strip()
            return None

        def _require_actor(self) -> tuple[AuthenticatedActor, RolePermissions]:
            if not ctx.auth.oidc.enabled:
                raise OIDCTokenValidationError("OIDC disabled")

            token = self._extract_token()
            if token is None:
                raise OIDCTokenValidationError("missing bearer token")

            actor = ctx.oidc.validate_bearer_token(token=token)
            perms = ctx.rbac.permissions_for_roles(actor.roles)
            return actor, perms

        def _require_permission(self, *, perms: RolePermissions, perm_name: str) -> None:
            if not perms.has(perm_name):
                raise PermissionError(f"missing permission: {perm_name}")

        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed = urlparse(self.path)
            path = parsed.path

            if path in ("/", "/ui"):
                self._redirect(location="/ui/queues")
                return

            if path in ("/healthz", "/readyz"):
                report = ok(component="ieim-api")
                self._send_json(
                    status=HTTPStatus.OK,
                    obj={"status": report.status, "details": report.details},
                )
                return

            if path == "/ui/login":
                if not ctx.auth.oidc.enabled:
                    body = "<p class='danger'>OIDC is disabled in the runtime config.</p>"
                    self._send_html(status=HTTPStatus.OK, html_text=_html_page(title="IEIM Login", body_html=body))
                    return

                if not ctx.auth.oidc.direct_grant.enabled:
                    body = "<p class='danger'>Direct grant login is disabled in the runtime config.</p>"
                    self._send_html(status=HTTPStatus.OK, html_text=_html_page(title="IEIM Login", body_html=body))
                    return

                body = """
                <div class='card'>
                  <form method='post' action='/ui/login'>
                    <div class='row'>
                      <div><label>Username<input name='username' autocomplete='username'/></label></div>
                      <div><label>Password<input type='password' name='password' autocomplete='current-password'/></label></div>
                    </div>
                    <p class='muted'>This uses the OIDC token endpoint (direct grant) and stores the access token in an HttpOnly cookie.</p>
                    <button class='primary' type='submit'>Login</button>
                  </form>
                </div>
                """
                self._send_html(status=HTTPStatus.OK, html_text=_html_page(title="IEIM Login", body_html=body))
                return

            if path == "/ui/logout":
                self._redirect(location="/ui/login", extra_headers={"Set-Cookie": _cookie_clear(name=ctx.session_cookie_name)})
                return

            if path == "/api/me":
                try:
                    actor, perms = self._require_actor()
                except OIDCTokenValidationError:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return
                self._send_json(
                    status=HTTPStatus.OK,
                    obj={
                        "actor_id": actor.actor_id,
                        "roles": list(actor.roles),
                        "permissions": {
                            "can_view_raw": perms.can_view_raw,
                            "can_view_audit": perms.can_view_audit,
                            "can_approve_drafts": perms.can_approve_drafts,
                        },
                    },
                )
                return

            if path == "/ui/queues":
                try:
                    actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except Exception:
                    self._redirect(location="/ui/login")
                    return

                review_root = ctx.hitl_dir / "review_items"
                rows = []
                if review_root.exists():
                    for qdir in sorted([p for p in review_root.iterdir() if p.is_dir()]):
                        count = len(list(qdir.glob("*.review.json")))
                        q = html.escape(qdir.name)
                        rows.append(f"<li><a href='/ui/queues/{q}'>{q}</a> <span class='muted'>({count})</span></li>")

                body = (
                    f"<p class='muted'>Signed in as <code>{html.escape(actor.actor_id)}</code></p>"
                    "<p><a href='/ui/logout'>Logout</a></p>"
                    "<div class='card'><h2>Queues</h2>"
                    + ("<ul>" + "".join(rows) + "</ul>" if rows else "<p class='muted'>No review items found.</p>")
                    + "</div>"
                )
                self._send_html(status=HTTPStatus.OK, html_text=_html_page(title="IEIM Queues", body_html=body))
                return

            if path.startswith("/ui/queues/"):
                queue_id = path[len("/ui/queues/") :]
                if not queue_id or "/" in queue_id:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                try:
                    _actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except Exception:
                    self._redirect(location="/ui/login")
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                items = store.list_queue(queue_id=queue_id)
                li = []
                for it in items:
                    rid = html.escape(str(it.get("review_item_id") or ""))
                    mid = html.escape(str(it.get("message_id") or ""))
                    status = html.escape(str(it.get("status") or ""))
                    li.append(f"<li><a href='/ui/items/{rid}'>{rid}</a> <span class='muted'>{mid} {status}</span></li>")

                q = html.escape(queue_id)
                body = (
                    f"<p><a href='/ui/queues'>&larr; Back to queues</a></p>"
                    f"<div class='card'><h2>Queue: <code>{q}</code></h2>"
                    + ("<ul>" + "".join(li) + "</ul>" if li else "<p class='muted'>No items.</p>")
                    + "</div>"
                )
                self._send_html(status=HTTPStatus.OK, html_text=_html_page(title=f"IEIM Queue {queue_id}", body_html=body))
                return

            if path.startswith("/ui/items/"):
                review_item_id = path[len("/ui/items/") :]
                if not review_item_id or "/" in review_item_id:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                try:
                    actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except Exception:
                    self._redirect(location="/ui/login")
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                p = store.find_path(review_item_id=review_item_id)
                if p is None:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                raw = p.read_bytes()
                etag = _stable_etag(raw)
                review_item = json.loads(raw.decode("utf-8"))

                artifacts: list[dict[str, Any]] = []
                for ref in list(review_item.get("artifact_refs") or []):
                    if not isinstance(ref, dict):
                        continue
                    schema_id = ref.get("schema_id")
                    uri = ref.get("uri")
                    if not isinstance(schema_id, str) or not isinstance(uri, str):
                        continue
                    if schema_id == "RAW_MIME":
                        continue
                    if not uri.endswith(".json"):
                        continue
                    try:
                        ap = _resolve_unique_artifact_path(roots=ctx.artifact_roots, uri=uri)
                    except Exception:
                        continue
                    if ap is None:
                        continue
                    try:
                        artifacts.append({"schema_id": schema_id, "uri": uri, "data": json.loads(ap.read_text(encoding="utf-8"))})
                    except Exception:
                        continue

                drafts = []
                for ref in list(review_item.get("draft_refs") or []):
                    if not isinstance(ref, dict):
                        continue
                    schema_id = ref.get("schema_id")
                    uri = ref.get("uri")
                    sha = ref.get("sha256")
                    if not isinstance(schema_id, str) or not isinstance(uri, str) or not isinstance(sha, str):
                        continue
                    drafts.append({"schema_id": schema_id, "uri": uri, "sha256": sha})

                rid = html.escape(review_item_id)
                body = (
                    f"<p><a href='/ui/queues/{html.escape(str(review_item.get('queue_id') or ''))}'>&larr; Back to queue</a></p>"
                    f"<p class='muted'>Signed in as <code>{html.escape(actor.actor_id)}</code></p>"
                    f"<div class='card'><h2>Review Item <code>{rid}</code></h2>"
                    f"<pre>{html.escape(json.dumps(review_item, indent=2, ensure_ascii=False))}</pre></div>"
                )

                for art in artifacts:
                    body += (
                        "<div class='card'>"
                        f"<h3>Artifact: <code>{html.escape(str(art.get('schema_id') or ''))}</code></h3>"
                        f"<p class='muted'><code>{html.escape(str(art.get('uri') or ''))}</code></p>"
                        f"<pre>{html.escape(json.dumps(art.get('data'), indent=2, ensure_ascii=False))}</pre>"
                        "</div>"
                    )

                body += "<div class='card'><h3>Submit correction</h3>"
                body += (
                    f"<form method='post' action='/ui/items/{rid}/corrections'>"
                    f"<input type='hidden' name='if_match' value='{html.escape(etag)}'/>"
                    f"<input type='hidden' name='idempotency_key' value='{html.escape(str(uuid.uuid4()))}'/>"
                    "<label>Note (optional)<input name='note'/></label>"
                    "<label>Corrections JSON (list[object])<textarea name='corrections_json'></textarea></label>"
                    "<button class='primary' type='submit'>Submit</button>"
                    "</form>"
                )
                body += "</div>"

                if drafts:
                    body += "<div class='card'><h3>Draft approvals</h3>"
                    for d in drafts:
                        kind = None
                        if d["schema_id"] == "DRAFT_REQUEST_INFO":
                            kind = "request_info"
                        if d["schema_id"] == "DRAFT_REPLY":
                            kind = "reply"
                        if kind is None:
                            continue
                        body += (
                            f"<p><code>{html.escape(d['schema_id'])}</code> <span class='muted'>{html.escape(d['uri'])}</span></p>"
                            f"<form method='post' action='/ui/items/{rid}/drafts/{kind}/approve'>"
                            f"<input type='hidden' name='if_match' value='{html.escape(etag)}'/>"
                            f"<input type='hidden' name='idempotency_key' value='{html.escape(str(uuid.uuid4()))}'/>"
                            "<button class='primary' type='submit'>Approve</button>"
                            "</form>"
                            f"<form method='post' action='/ui/items/{rid}/drafts/{kind}/reject'>"
                            f"<input type='hidden' name='if_match' value='{html.escape(etag)}'/>"
                            f"<input type='hidden' name='idempotency_key' value='{html.escape(str(uuid.uuid4()))}'/>"
                            "<button type='submit'>Reject</button>"
                            "</form>"
                        )
                    body += "</div>"

                self._send_html(status=HTTPStatus.OK, html_text=_html_page(title=f"IEIM Item {review_item_id}", body_html=body))
                return

            if path == "/api/review/queues":
                try:
                    _actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except OIDCTokenValidationError:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return
                except PermissionError:
                    self._send_json(status=HTTPStatus.FORBIDDEN, obj={"error": "FORBIDDEN"})
                    return

                review_root = ctx.hitl_dir / "review_items"
                queues = []
                if review_root.exists():
                    for qdir in sorted([p for p in review_root.iterdir() if p.is_dir()]):
                        count = len(list(qdir.glob("*.review.json")))
                        queues.append({"queue_id": qdir.name, "open_count": count})
                self._send_json(status=HTTPStatus.OK, obj={"queues": queues})
                return

            if path.startswith("/api/review/queues/") and path.endswith("/items"):
                try:
                    _actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except OIDCTokenValidationError:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return
                except PermissionError:
                    self._send_json(status=HTTPStatus.FORBIDDEN, obj={"error": "FORBIDDEN"})
                    return

                queue_id = path[len("/api/review/queues/") : -len("/items")]
                store = FileReviewStore(base_dir=ctx.hitl_dir)
                items = store.list_queue(queue_id=queue_id)
                self._send_json(status=HTTPStatus.OK, obj={"queue_id": queue_id, "items": items})
                return

            if path.startswith("/api/review/items/"):
                review_item_id = path[len("/api/review/items/") :]
                if "/" in review_item_id or not review_item_id:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                try:
                    _actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except OIDCTokenValidationError:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return
                except PermissionError:
                    self._send_json(status=HTTPStatus.FORBIDDEN, obj={"error": "FORBIDDEN"})
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                p = store.find_path(review_item_id=review_item_id)
                if p is None:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                raw = p.read_bytes()
                etag = _stable_etag(raw)
                review_item = json.loads(raw.decode("utf-8"))

                artifacts: list[dict[str, Any]] = []
                for ref in list(review_item.get("artifact_refs") or []):
                    if not isinstance(ref, dict):
                        continue
                    schema_id = ref.get("schema_id")
                    uri = ref.get("uri")
                    if not isinstance(schema_id, str) or not isinstance(uri, str):
                        continue
                    if schema_id == "RAW_MIME":
                        continue
                    if not uri.endswith(".json"):
                        continue
                    try:
                        ap = _resolve_unique_artifact_path(roots=ctx.artifact_roots, uri=uri)
                    except Exception as e:
                        self._send_json(status=HTTPStatus.CONFLICT, obj={"error": "ARTIFACT_AMBIGUOUS", "detail": str(e)})
                        return
                    if ap is None:
                        continue
                    try:
                        artifacts.append(
                            {
                                "schema_id": schema_id,
                                "uri": uri,
                                "data": json.loads(ap.read_text(encoding="utf-8")),
                            }
                        )
                    except Exception:
                        continue

                self._send_json(
                    status=HTTPStatus.OK,
                    obj={"review_item": review_item, "artifacts": artifacts},
                    extra_headers={"ETag": f"\"{etag}\""},
                )
                return

            self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/ui/login":
                if not ctx.auth.oidc.enabled or not ctx.auth.oidc.direct_grant.enabled:
                    self._redirect(location="/ui/login")
                    return

                try:
                    form = self._read_form_body()
                    username = (form.get("username") or "").strip()
                    password = form.get("password") or ""
                    token = ctx.oidc.direct_grant_password(username=username, password=password)
                    _ = ctx.oidc.validate_bearer_token(token=token)
                except Exception:
                    self._redirect(location="/ui/login")
                    return

                cookie = _cookie_kv(name=ctx.session_cookie_name, value=token)
                self._redirect(location="/ui/queues", extra_headers={"Set-Cookie": cookie})
                return

            if path.startswith("/ui/items/") and path.endswith("/corrections"):
                review_item_id = path[len("/ui/items/") : -len("/corrections")]
                if not review_item_id or "/" in review_item_id:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                try:
                    actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except Exception:
                    self._redirect(location="/ui/login")
                    return

                try:
                    form = self._read_form_body()
                    if_match = str(form.get("if_match") or "")
                    idempotency_key = str(form.get("idempotency_key") or "")
                    note = form.get("note")
                    corrections_json = str(form.get("corrections_json") or "")
                    corrections_raw = json.loads(corrections_json)
                    if not isinstance(corrections_raw, list) or not all(isinstance(x, dict) for x in corrections_raw):
                        raise ValueError("corrections_json must be a JSON list of objects")
                except Exception:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                review_item_path = store.find_path(review_item_id=review_item_id)
                if review_item_path is None:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                etag = _stable_etag(review_item_path.read_bytes())
                if if_match != etag:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                correction_id = _idempotency_correction_id(
                    review_item_id=review_item_id, actor_id=actor.actor_id, key=idempotency_key or str(uuid.uuid4())
                )
                audit_logger = FileAuditLogger(base_dir=ctx.hitl_dir)
                service = HitlService(repo_root=ctx.repo_root, hitl_dir=ctx.hitl_dir, audit_logger=audit_logger)
                try:
                    service.submit_correction(
                        review_item_path=review_item_path,
                        actor_id=actor.actor_id,
                        corrections=[dict(x) for x in corrections_raw],
                        note=note,
                        correction_id=correction_id,
                    )
                except Exception:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                self._redirect(location=f"/ui/items/{review_item_id}")
                return

            if path.startswith("/ui/items/") and "/drafts/" in path:
                # /ui/items/<id>/drafts/<kind>/<action>
                parts = [p for p in path.split("/") if p]
                if len(parts) != 6 or parts[0] != "ui" or parts[1] != "items" or parts[3] != "drafts":
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                review_item_id = parts[2]
                draft_kind = parts[4]
                action = parts[5]
                if action not in ("approve", "reject"):
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                draft_schema_id = None
                if draft_kind == "request_info":
                    draft_schema_id = "DRAFT_REQUEST_INFO"
                elif draft_kind == "reply":
                    draft_schema_id = "DRAFT_REPLY"
                else:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                try:
                    actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                    self._require_permission(perms=perms, perm_name="can_approve_drafts")
                except Exception:
                    self._redirect(location="/ui/login")
                    return

                try:
                    form = self._read_form_body()
                    if_match = str(form.get("if_match") or "")
                    idempotency_key = str(form.get("idempotency_key") or "")
                except Exception:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                review_item_path = store.find_path(review_item_id=review_item_id)
                if review_item_path is None:
                    self._send_html(status=HTTPStatus.NOT_FOUND, html_text=_html_page(title="Not Found", body_html=""))
                    return

                review_bytes = review_item_path.read_bytes()
                etag = _stable_etag(review_bytes)
                if if_match != etag:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                review_item = json.loads(review_bytes.decode("utf-8"))
                queue_id = str(review_item.get("queue_id") or "")
                if (
                    queue_id == "QUEUE_PRIVACY_DSR"
                    and "privacy_officer" not in actor.roles
                    and "administrator" not in actor.roles
                ):
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                draft_ref = None
                for ref in list(review_item.get("draft_refs") or []):
                    if not isinstance(ref, dict):
                        continue
                    if ref.get("schema_id") == draft_schema_id:
                        draft_ref = dict(ref)
                        break
                if draft_ref is None:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                corr_action = "APPROVE" if action == "approve" else "REJECT"
                corrections = [
                    {
                        "target_stage": "HITL",
                        "patch": [
                            {
                                "op": "add",
                                "path": "/draft_approvals/-",
                                "value": {
                                    "draft_schema_id": draft_ref.get("schema_id"),
                                    "draft_uri": draft_ref.get("uri"),
                                    "draft_sha256": draft_ref.get("sha256"),
                                    "action": corr_action,
                                },
                            }
                        ],
                        "justification": None,
                        "evidence": [],
                    }
                ]

                correction_id = _idempotency_correction_id(
                    review_item_id=review_item_id,
                    actor_id=actor.actor_id,
                    key=f"draft:{draft_kind}:{action}:{idempotency_key or str(uuid.uuid4())}",
                )

                audit_logger = FileAuditLogger(base_dir=ctx.hitl_dir)
                service = HitlService(repo_root=ctx.repo_root, hitl_dir=ctx.hitl_dir, audit_logger=audit_logger)
                try:
                    service.submit_correction(
                        review_item_path=review_item_path,
                        actor_id=actor.actor_id,
                        corrections=corrections,
                        note=None,
                        correction_id=correction_id,
                    )
                except Exception:
                    self._redirect(location=f"/ui/items/{review_item_id}")
                    return

                self._redirect(location=f"/ui/items/{review_item_id}")
                return

            if path == "/api/review/login/direct-grant":
                if not ctx.auth.oidc.direct_grant.enabled:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return
                try:
                    body = self._read_json_body(max_bytes=32 * 1024)
                    username = str(body.get("username") or "")
                    password = str(body.get("password") or "")
                    token = ctx.oidc.direct_grant_password(username=username, password=password)
                    # validate immediately to fail-closed early
                    _ = ctx.oidc.validate_bearer_token(token=token)
                except Exception:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return

                cookie = _cookie_kv(name=ctx.session_cookie_name, value=token)
                self._send_json(status=HTTPStatus.OK, obj={"status": "OK"}, extra_headers={"Set-Cookie": cookie})
                return

            if path.startswith("/api/review/items/") and path.endswith("/corrections"):
                review_item_id = path[len("/api/review/items/") : -len("/corrections")]
                if "/" in review_item_id or not review_item_id:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                try:
                    actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                except OIDCTokenValidationError:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return
                except PermissionError:
                    self._send_json(status=HTTPStatus.FORBIDDEN, obj={"error": "FORBIDDEN"})
                    return

                idempotency_key = str(self.headers.get("Idempotency-Key") or "").strip()
                if not idempotency_key:
                    self._send_json(status=HTTPStatus.BAD_REQUEST, obj={"error": "MISSING_IDEMPOTENCY_KEY"})
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                review_item_path = store.find_path(review_item_id=review_item_id)
                if review_item_path is None:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                review_bytes = review_item_path.read_bytes()
                etag = _stable_etag(review_bytes)
                if_match = _parse_if_match(self.headers.get("If-Match"))
                if if_match is None or if_match != etag:
                    self._send_json(status=HTTPStatus.PRECONDITION_FAILED, obj={"error": "ETAG_MISMATCH"})
                    return

                try:
                    body = self._read_json_body()
                    corrections = body.get("corrections")
                    note = body.get("note")
                    if not isinstance(corrections, list) or not all(isinstance(x, dict) for x in corrections):
                        raise ValueError("corrections must be list[object]")
                    if note is not None and (not isinstance(note, str) or len(note) > 2000):
                        raise ValueError("note must be string up to 2000 chars")
                except Exception as e:
                    self._send_json(status=HTTPStatus.BAD_REQUEST, obj={"error": "INVALID_INPUT", "detail": str(e)})
                    return

                correction_id = _idempotency_correction_id(
                    review_item_id=review_item_id, actor_id=actor.actor_id, key=idempotency_key
                )

                audit_logger = FileAuditLogger(base_dir=ctx.hitl_dir)
                service = HitlService(repo_root=ctx.repo_root, hitl_dir=ctx.hitl_dir, audit_logger=audit_logger)
                try:
                    out_path = service.submit_correction(
                        review_item_path=review_item_path,
                        actor_id=actor.actor_id,
                        corrections=[dict(x) for x in corrections],
                        note=note,
                        correction_id=correction_id,
                    )
                except Exception as e:
                    self._send_json(status=HTTPStatus.INTERNAL_SERVER_ERROR, obj={"error": "FAILED", "detail": str(e)})
                    return

                out_bytes = out_path.read_bytes()
                rel = out_path.resolve().relative_to(ctx.hitl_dir.resolve()).as_posix()
                self._send_json(
                    status=HTTPStatus.OK,
                    obj={
                        "status": "OK",
                        "correction_id": correction_id,
                        "artifact_ref": {"schema_id": "urn:ieim:schema:correction-record:1.0.0", "uri": rel, "sha256": sha256_prefixed(out_bytes)},
                    },
                )
                return

            if path.startswith("/api/review/items/") and "/drafts/" in path:
                # /api/review/items/<id>/drafts/<kind>/<action>
                parts = [p for p in path.split("/") if p]
                if (
                    len(parts) != 7
                    or parts[0] != "api"
                    or parts[1] != "review"
                    or parts[2] != "items"
                    or parts[4] != "drafts"
                ):
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                review_item_id = parts[3]
                draft_kind = parts[5]
                action = parts[6]

                if action not in ("approve", "reject"):
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                draft_schema_id = None
                if draft_kind == "request_info":
                    draft_schema_id = "DRAFT_REQUEST_INFO"
                elif draft_kind == "reply":
                    draft_schema_id = "DRAFT_REPLY"
                else:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                try:
                    actor, perms = self._require_actor()
                    self._require_permission(perms=perms, perm_name="can_view_audit")
                    self._require_permission(perms=perms, perm_name="can_approve_drafts")
                except OIDCTokenValidationError:
                    self._send_json(status=HTTPStatus.UNAUTHORIZED, obj={"error": "UNAUTHORIZED"})
                    return
                except PermissionError:
                    self._send_json(status=HTTPStatus.FORBIDDEN, obj={"error": "FORBIDDEN"})
                    return

                idempotency_key = str(self.headers.get("Idempotency-Key") or "").strip()
                if not idempotency_key:
                    self._send_json(status=HTTPStatus.BAD_REQUEST, obj={"error": "MISSING_IDEMPOTENCY_KEY"})
                    return

                store = FileReviewStore(base_dir=ctx.hitl_dir)
                review_item_path = store.find_path(review_item_id=review_item_id)
                if review_item_path is None:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                review_bytes = review_item_path.read_bytes()
                etag = _stable_etag(review_bytes)
                if_match = _parse_if_match(self.headers.get("If-Match"))
                if if_match is None or if_match != etag:
                    self._send_json(status=HTTPStatus.PRECONDITION_FAILED, obj={"error": "ETAG_MISMATCH"})
                    return

                review_item = json.loads(review_bytes.decode("utf-8"))
                queue_id = str(review_item.get("queue_id") or "")
                if queue_id == "QUEUE_PRIVACY_DSR" and "privacy_officer" not in actor.roles and "administrator" not in actor.roles:
                    self._send_json(status=HTTPStatus.FORBIDDEN, obj={"error": "FORBIDDEN"})
                    return

                draft_ref = None
                for ref in list(review_item.get("draft_refs") or []):
                    if not isinstance(ref, dict):
                        continue
                    if ref.get("schema_id") == draft_schema_id:
                        draft_ref = dict(ref)
                        break
                if draft_ref is None:
                    self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})
                    return

                corr_action = "APPROVE" if action == "approve" else "REJECT"
                corrections = [
                    {
                        "target_stage": "HITL",
                        "patch": [
                            {
                                "op": "add",
                                "path": "/draft_approvals/-",
                                "value": {
                                    "draft_schema_id": draft_ref.get("schema_id"),
                                    "draft_uri": draft_ref.get("uri"),
                                    "draft_sha256": draft_ref.get("sha256"),
                                    "action": corr_action,
                                },
                            }
                        ],
                        "justification": None,
                        "evidence": [],
                    }
                ]

                correction_id = _idempotency_correction_id(
                    review_item_id=review_item_id,
                    actor_id=actor.actor_id,
                    key=f"draft:{draft_kind}:{action}:{idempotency_key}",
                )

                audit_logger = FileAuditLogger(base_dir=ctx.hitl_dir)
                service = HitlService(repo_root=ctx.repo_root, hitl_dir=ctx.hitl_dir, audit_logger=audit_logger)
                try:
                    out_path = service.submit_correction(
                        review_item_path=review_item_path,
                        actor_id=actor.actor_id,
                        corrections=corrections,
                        note=None,
                        correction_id=correction_id,
                    )
                except Exception as e:
                    self._send_json(status=HTTPStatus.INTERNAL_SERVER_ERROR, obj={"error": "FAILED", "detail": str(e)})
                    return

                out_bytes = out_path.read_bytes()
                rel = out_path.resolve().relative_to(ctx.hitl_dir.resolve()).as_posix()
                self._send_json(
                    status=HTTPStatus.OK,
                    obj={
                        "status": "OK",
                        "correction_id": correction_id,
                        "artifact_ref": {"schema_id": "urn:ieim:schema:correction-record:1.0.0", "uri": rel, "sha256": sha256_prefixed(out_bytes)},
                    },
                )
                return

            self._send_json(status=HTTPStatus.NOT_FOUND, obj={"error": "NOT_FOUND"})

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ieim-api")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file (repo-relative unless absolute).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--hitl-dir", default="hitl", help="HITL directory (review items + corrections).")
    parser.add_argument(
        "--artifact-root",
        action="append",
        default=None,
        help="Directory root used for resolving artifact URIs (repeatable). Defaults to repo root.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit.")
    args = parser.parse_args(argv)

    repo_root = discover_repo_root(Path(__file__).resolve())
    cfg_path = Path(args.config)
    cfg_path = cfg_path if cfg_path.is_absolute() else (repo_root / cfg_path)
    validate_config_file(path=cfg_path)

    if args.dry_run:
        print("IEIM_API_DRY_RUN_OK")
        return 0

    auth = load_auth_config(path=cfg_path)
    rbac = load_rbac_config(path=cfg_path)

    hitl_dir = Path(args.hitl_dir)
    hitl_dir = hitl_dir if hitl_dir.is_absolute() else (repo_root / hitl_dir)

    artifact_roots_raw = args.artifact_root or []
    if not artifact_roots_raw:
        artifact_roots = (repo_root,)
    else:
        roots: list[Path] = []
        for r in artifact_roots_raw:
            p = Path(r)
            roots.append(p if p.is_absolute() else (repo_root / p))
        artifact_roots = tuple(roots)

    ctx = ApiContext(
        repo_root=repo_root,
        config_path=cfg_path,
        auth=auth,
        rbac=rbac,
        oidc=OidcJwtValidator(config=auth.oidc),
        hitl_dir=hitl_dir,
        artifact_roots=artifact_roots,
    )

    server = HTTPServer((str(args.host), int(args.port)), _make_handler(ctx))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
