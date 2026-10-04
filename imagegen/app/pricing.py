"""Cost estimates. Three numbers are kept apart everywhere: API-reported tokens,
our local dollar estimate from those tokens, and what OpenAI billing shows."""
from __future__ import annotations

import json
from pathlib import Path

from .config import PRICING_PATH


def load(path: Path = PRICING_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(doc: dict, path: Path = PRICING_PATH) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(path)


def _key(model: str, size: str, quality: str) -> str:
    return f"{model}|{size}|{quality}"


def estimate(pricing: dict, model: str, size: str, quality: str, n_refs: int) -> dict:
    """Per-image estimate with its assumptions spelled out."""
    p = pricing["per_million"].get(model)
    if not p:
        return {"per_image_usd": None, "assumptions": [f"no pricing for {model}"], "observed": False}
    obs = pricing.get("observed", {}).get(_key(model, size, quality))
    assumptions = []
    if obs and obs.get("n", 0) > 0:
        out_tokens = obs["output_tokens_mean"]
        img_in = obs["image_in_tokens_mean"]
        text = obs["text_tokens_mean"]
        assumptions.append(f"tokens from {obs['n']} observed request(s) at these settings")
        observed = True
    else:
        out_tokens = pricing["output_tokens_assumed"].get(size, {}).get(quality)
        img_in = pricing["ref_image_tokens_assumed"] * n_refs
        text = pricing["text_tokens_assumed"]
        assumptions.append(f"output tokens ASSUMED {out_tokens} for {size} {quality} (not published; replaced by observed usage)")
        assumptions.append(f"reference input ASSUMED {pricing['ref_image_tokens_assumed']} tokens x {n_refs} refs")
        observed = False
        if out_tokens is None:
            return {"per_image_usd": None, "assumptions": [f"no token assumption for {size} {quality}"], "observed": False}
    usd = (text * p["text_in"] + img_in * p["image_in"] + out_tokens * p["image_out"]) / 1e6
    assumptions.append(f"prices per 1M tokens: text {p['text_in']}, image in {p['image_in']}, image out {p['image_out']} ({pricing['source']}, verified {pricing['verified']})")
    return {"per_image_usd": round(usd, 4), "assumptions": assumptions, "observed": observed,
            "tokens": {"text": text, "image_in": img_in, "image_out": out_tokens}}


def cost_of(pricing: dict, model: str, usage: dict | None) -> float | None:
    """Dollar estimate from API-reported usage. None when usage is unknown."""
    if not usage:
        return None
    p = pricing["per_million"].get(model)
    if not p:
        return None
    text = usage.get("text_tokens") or 0
    img_in = usage.get("image_in_tokens") or 0
    out = usage.get("output_tokens") or 0
    return round((text * p["text_in"] + img_in * p["image_in"] + out * p["image_out"]) / 1e6, 5)


def record_observation(pricing: dict, model: str, size: str, quality: str, usage: dict) -> dict:
    """Fold a real usage record into the running means for these settings."""
    k = _key(model, size, quality)
    o = pricing.setdefault("observed", {}).get(k) or {"n": 0, "output_tokens_mean": 0, "image_in_tokens_mean": 0, "text_tokens_mean": 0}
    n = o["n"]
    for field, src in (("output_tokens_mean", "output_tokens"), ("image_in_tokens_mean", "image_in_tokens"), ("text_tokens_mean", "text_tokens")):
        v = usage.get(src) or 0
        o[field] = round((o[field] * n + v) / (n + 1), 1)
    o["n"] = n + 1
    pricing["observed"][k] = o
    return pricing
