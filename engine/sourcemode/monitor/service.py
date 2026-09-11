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

    from ..assets.review import review_router  # noqa: PLC0415

    app.include_router(review_router(cfg))
    return app


def serve(cfg: dict, host: str | None = None, port: int | None = None) -> None:
    import uvicorn  # noqa: PLC0415

    uvicorn.run(create_app(cfg), host=host or cfg["monitor"]["host"],
                port=port or int(cfg["monitor"]["port"]), log_level="warning")
