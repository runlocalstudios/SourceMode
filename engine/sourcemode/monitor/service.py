"""HTTP surface for the readout. Read-only today; /generate and /video land here later."""

from __future__ import annotations

from contextlib import asynccontextmanager

from .sampler import Sampler


def create_app(cfg: dict, sampler: Sampler | None = None):
    from fastapi import FastAPI  # noqa: PLC0415

    sampler = sampler or Sampler(cfg)

    @asynccontextmanager
    async def lifespan(_app):
        sampler.sample_once()
        sampler.start()
        yield
        sampler.stop()

    app = FastAPI(title="SourceMode engine monitor", version="0.1", lifespan=lifespan)
    app.state.sampler = sampler

    @app.get("/status")
    def status() -> dict:
        return sampler.status()

    @app.get("/history")
    def history(max_points: int = 360) -> dict:
        return {"points": sampler.history_points(max_points)}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    from ..assets.judge import judge_router  # noqa: PLC0415
    from .hub import hub_router  # noqa: PLC0415
    from .queue_page import queue_router  # noqa: PLC0415
    from ..assets.review import review_router  # noqa: PLC0415
    from ..train.preview import preview_router  # noqa: PLC0415

    app.include_router(hub_router(cfg))
    app.include_router(queue_router(cfg))
    app.include_router(review_router(cfg))
    app.include_router(judge_router(cfg))
    app.include_router(preview_router(cfg))
    return app


def monitor_host(cfg: dict, host: str | None = None) -> str:
    """Bind address: explicit argument, then SOURCEMODE_MONITOR_HOST, then config.

    The env var is how this box reaches a phone over Tailscale without the repo
    shipping a wide-open default - the service has no auth, so the committed value
    stays loopback and the machine that wants remote access opts in locally.
    `start-monitor.ps1` has documented this override since it was written, but
    nothing read it, so setting it did nothing.
    """
    import os  # noqa: PLC0415

    return host or os.environ.get("SOURCEMODE_MONITOR_HOST") or cfg["monitor"]["host"]


def serve(cfg: dict, host: str | None = None, port: int | None = None) -> None:
    import uvicorn  # noqa: PLC0415

    # log_config=None: uvicorn's default config builds a colourising formatter that
    # needs a console, and dies with "Unable to configure formatter 'default'" when
    # the process is started detached with its stdout redirected to a file - which is
    # how the autostart task and every background relaunch run it. 2026-10-03: the
    # judge page was down for Jeremy because of exactly this.
    uvicorn.run(create_app(cfg), host=monitor_host(cfg, host),
                port=port or int(cfg["monitor"]["port"]), log_level="warning", log_config=None)
