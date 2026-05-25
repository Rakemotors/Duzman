"""FastAPI application factory for read-only Duzman API routes."""

from fastapi import FastAPI

from duzman.api.dependencies import configured_api_key
from duzman.api.routes.market_data import router as market_data_router
from duzman.settings import Settings


def create_app() -> FastAPI:
    """Create the Duzman FastAPI app without starting schedulers or jobs."""
    settings = Settings()
    app = FastAPI(title="Duzman", version="0.1.0")
    app.state.duzman_api_key = configured_api_key(settings)
    app.include_router(market_data_router)
    return app
