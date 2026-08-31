"""Minimal ComfyUI HTTP client.

POST /prompt with {"prompt": workflow_json, "client_id"}, poll
GET /history/{prompt_id}, fetch outputs via GET /view.
`session` is injectable (anything with .get/.post like requests) for tests.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8188, session=None, client_id: str | None = None):
        self.base = f"http://{host}:{port}"
        if session is None:
            import requests  # noqa: PLC0415

            session = requests.Session()
        self.session = session
        self.client_id = client_id or str(uuid.uuid4())

    def is_reachable(self, timeout: float = 2.0) -> bool:
        try:
            resp = self.session.get(f"{self.base}/system_stats", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def submit(self, workflow: dict) -> str:
        resp = self.session.post(
            f"{self.base}/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
            timeout=30,
        )
        if resp.status_code != 200:
            raise ComfyUIError(f"POST /prompt -> {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        if "prompt_id" not in data:
            raise ComfyUIError(f"no prompt_id in response: {data}")
        return data["prompt_id"]

    def wait(self, prompt_id: str, *, poll_s: float = 2.0, timeout_s: float = 3600.0) -> dict:
        """Poll /history until the prompt appears (finished); return its history entry.

        Transient poll failures (timeouts, connection resets while the GPU is
        saturated by a long render) are tolerated and retried — a single
        dropped request must never kill a run mid-render."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                resp = self.session.get(f"{self.base}/history/{prompt_id}", timeout=30)
                if resp.status_code == 200:
                    history = resp.json()
                    if prompt_id in history:
                        entry = history[prompt_id]
                        status = entry.get("status", {})
                        if status.get("status_str") == "error":
                            raise ComfyUIError(f"prompt {prompt_id} errored: {status}")
                        return entry
            except ComfyUIError:
                raise
            except Exception:  # noqa: BLE001 — transient network/parse hiccup, keep polling
                pass
            time.sleep(poll_s)
        raise ComfyUIError(f"timed out waiting for prompt {prompt_id}")

    def outputs(self, history_entry: dict) -> list[dict]:
        """Flatten output file descriptors ({filename, subfolder, type}) from a history entry."""
        files = []
        for node_output in history_entry.get("outputs", {}).values():
            for key in ("images", "videos", "gifs", "audio"):
                for item in node_output.get(key, []):
                    files.append(item)
        return files

    def upload_image(self, path: Path) -> str:
        """Upload an image to ComfyUI's input store; returns the server-side name."""
        with open(path, "rb") as f:
            resp = self.session.post(
                f"{self.base}/upload/image",
                files={"image": (Path(path).name, f, "image/png")},
                timeout=120,
            )
        if resp.status_code != 200:
            raise ComfyUIError(f"POST /upload/image -> {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        name = data.get("name", Path(path).name)
        sub = data.get("subfolder", "")
        return f"{sub}/{name}" if sub else name

    def fetch(self, file_desc: dict, dest: Path) -> Path:
        params = {
            "filename": file_desc["filename"],
            "subfolder": file_desc.get("subfolder", ""),
            "type": file_desc.get("type", "output"),
        }
        resp = self.session.get(f"{self.base}/view", params=params, timeout=120)
        if resp.status_code != 200:
            raise ComfyUIError(f"GET /view -> {resp.status_code}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return dest
