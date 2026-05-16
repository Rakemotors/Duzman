"""FastAPI application factory for read-only Duzman API routes."""

from fastapi import FastAPI

from duzman.api.routes.market_data import router as market_data_router


def create_app() -> FastAPI:
    """Create the Duzman FastAPI app without starting schedulers or jobs."""
    app = FastAPI(title="Duzman", version="0.1.0")
    app.include_router(market_data_router)
    return app
