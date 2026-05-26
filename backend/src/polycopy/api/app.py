from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polycopy import __version__
from polycopy.core.db import init_db
from polycopy.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await init_db()
    log.info("api.startup", version=__version__)
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Polycopy API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    from polycopy.api.routes import router

    app.include_router(router)
    return app


app = create_app()
