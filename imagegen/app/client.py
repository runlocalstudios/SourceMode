"""The OpenAI Images edit call, and a mock with the same shape.

Verified against the live docs 2026-10-01 and openai-python 3.22: `images.edit`
takes `image` (a list of files, up to 16), `prompt`, `model`, `size`, `quality`,
`input_fidelity`, `output_format`; `moderation` is not a named SDK argument at this
version so it goes through `extra_body`. The response carries `usage` with
input_tokens_details {image_tokens, text_tokens} and output_tokens.
"""
from __future__ import annotations

import base64
import io
import random
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ApiError(Exception):
    kind: str                 # rate_limit | quota | auth | config | moderation | transient | local_io
    message: str
    code: str | None = None
    status: int | None = None
    request_id: str | None = None
    retry_after: float | None = None

    def __str__(self) -> str:
        return f"{self.kind}: {self.message}"


@dataclass
class Result:
    image_bytes: bytes
    usage: dict | None
    model_requested: str
    model_returned: str | None
    request_id: str | None
    raw: dict = field(default_factory=dict)


def classify(exc: Exception) -> ApiError:
    """Map SDK exceptions onto the kinds the queue acts on. Keeps the exact code,
    message, request id and any retry hint."""
    import openai

    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None) or {}
    err = body.get("error", body) if isinstance(body, dict) else {}
    code = (err.get("code") if isinstance(err, dict) else None) or getattr(exc, "code", None)
    msg = (err.get("message") if isinstance(err, dict) else None) or str(exc)
    req_id = getattr(exc, "request_id", None)
    headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
    retry_after = None
    try:
        if headers.get("retry-after"):
            retry_after = float(headers["retry-after"])
    except (TypeError, ValueError):
        retry_after = None
    text = f"{code or ''} {msg}".lower()

    if isinstance(exc, openai.AuthenticationError) or status in (401, 403):
        return ApiError("auth", msg, code, status, req_id)
    if isinstance(exc, openai.RateLimitError) or status == 429:
        if "insufficient_quota" in text or "billing" in text or "quota" in text or "credit" in text:
            return ApiError("quota", msg, code, status, req_id, retry_after)
        return ApiError("rate_limit", msg, code, status, req_id, retry_after)
    if status == 400 or isinstance(exc, openai.BadRequestError):
        if "moderation" in text or "safety" in text or "content_policy" in text or "rejected" in text:
            return ApiError("moderation", msg, code, status, req_id)
        return ApiError("config", msg, code, status, req_id)
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError)) or (status and status >= 500):
        return ApiError("transient", msg, code, status, req_id, retry_after)
    if isinstance(exc, openai.NotFoundError):
        return ApiError("config", msg, code, status, req_id)
    return ApiError("transient", msg, code, status, req_id, retry_after)


def _usage_dict(u) -> dict | None:
    if u is None:
        return None
    d = u.model_dump() if hasattr(u, "model_dump") else dict(u)
    inp = d.get("input_tokens_details") or {}
    return {"input_tokens": d.get("input_tokens"), "output_tokens": d.get("output_tokens"),
            "total_tokens": d.get("total_tokens"),
            "image_in_tokens": inp.get("image_tokens"), "text_tokens": inp.get("text_tokens")}


class RealClient:
    billable = True

    def __init__(self, api_key: str, timeout_s: float = 300.0):
        import openai
        self._c = openai.OpenAI(api_key=api_key, timeout=timeout_s, max_retries=0)

    def edit(self, prompt: str, refs: list[Path], settings: dict) -> Result:
        files = []
        try:
            for p in refs:
                files.append((p.name, p.read_bytes(), _mime(p)))
            kwargs = dict(image=files, prompt=prompt, model=settings["model"], n=1,
                          size=settings["size"], quality=settings["quality"],
                          output_format=settings.get("output_format", "png"))
            # Sent only when asked for: the 2.5 models reject the parameter outright
            # rather than ignoring it, so an unused default fails the request.
            if settings.get("input_fidelity") not in (None, "", "none"):
                kwargs["input_fidelity"] = settings["input_fidelity"]
            if settings.get("moderation"):
                kwargs["extra_body"] = {"moderation": settings["moderation"]}
            resp = self._c.images.with_raw_response.edit(**kwargs)
        except Exception as exc:  # noqa: BLE001 - every SDK error is classified
            raise classify(exc) from exc
        parsed = resp.parse()
        req_id = resp.headers.get("x-request-id")
        if not parsed.data or not parsed.data[0].b64_json:
            raise ApiError("transient", "response carried no image", request_id=req_id)
        raw = parsed.model_dump(exclude={"data"})
        return Result(base64.b64decode(parsed.data[0].b64_json), _usage_dict(parsed.usage),
                      settings["model"], raw.get("model"), req_id, raw)


class MockClient:
    """Deterministic stand-in: a labelled grey image, plausible usage, and scripted
    failures via `script` (a list of ApiError kinds or None, consumed in order)."""

    billable = False

    def __init__(self, script: list[str | None] | None = None, delay_s: float = 0.0):
        self.script = list(script or [])
        self.delay_s = delay_s
        self.calls: list[dict] = []

    def edit(self, prompt: str, refs: list[Path], settings: dict) -> Result:
        self.calls.append({"prompt": prompt, "refs": [str(r) for r in refs], "settings": dict(settings)})
        if self.delay_s:
            time.sleep(self.delay_s)
        kind = self.script.pop(0) if self.script else None
        if kind == "quota":
            raise ApiError("quota", "You exceeded your current quota", "insufficient_quota", 429, "req_mock_q")
        if kind == "rate_limit":
            raise ApiError("rate_limit", "Rate limit reached", "rate_limit_exceeded", 429, "req_mock_r", retry_after=0.01)
        if kind == "moderation":
            raise ApiError("moderation", "Your request was rejected by the safety system", "moderation_blocked", 400, "req_mock_m")
        if kind == "transient":
            raise ApiError("transient", "server error", None, 500, "req_mock_t")
        if kind == "auth":
            raise ApiError("auth", "Incorrect API key", "invalid_api_key", 401, "req_mock_a")
        if kind == "config":
            raise ApiError("config", "Invalid value for size", "invalid_value", 400, "req_mock_c")
        if kind == "uncertain":
            raise ApiError("transient", "timed out after sending", None, None, None)
        from PIL import Image, ImageDraw
        w, h = (int(x) for x in settings["size"].split("x"))
        im = Image.new("RGB", (w, h), (90 + random.randint(0, 40),) * 3)
        ImageDraw.Draw(im).text((20, 20), f"MOCK {settings['model']} {settings['quality']}\n{prompt[:60]}", fill="white")
        buf = io.BytesIO(); im.save(buf, "PNG")
        usage = {"input_tokens": 250 + 1500 * len(refs), "output_tokens": 10550, "total_tokens": 0,
                 "image_in_tokens": 1500 * len(refs), "text_tokens": 250}
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        return Result(buf.getvalue(), usage, settings["model"], settings["model"] + "-mock", f"req_mock_{len(self.calls)}")


def _mime(p: Path) -> str:
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(p.suffix.lower(), "application/octet-stream")
