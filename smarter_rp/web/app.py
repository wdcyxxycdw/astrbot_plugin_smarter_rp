from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage
from smarter_rp.web.auth import verify_token_factory
from smarter_rp.web.routes_accounts import create_accounts_router
from smarter_rp.web.routes_characters import create_characters_router
from smarter_rp.web.routes_dashboard import create_dashboard_router
from smarter_rp.web.routes_debug import create_debug_router
from smarter_rp.web.routes_history import create_history_router
from smarter_rp.web.routes_sessions import create_sessions_router


STATIC_DIR = Path(__file__).parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


def create_app(token: str, storage: Storage | None = None) -> FastAPI:
    auth_dependency = verify_token_factory(token)
    account_service = AccountService(storage) if storage is not None else None
    session_service = SessionService(storage) if storage is not None else None
    history_service = (
        HistoryService(storage, session_service)
        if storage is not None and session_service is not None
        else None
    )
    debug_service = DebugService(storage) if storage is not None else None
    character_service = CharacterService(storage) if storage is not None else None
    app = FastAPI(title="Smarter RP WebUI")

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/")
    async def root():
        if INDEX_FILE.exists():
            return FileResponse(INDEX_FILE)
        return HTMLResponse(
            "<html><body><h1>Smarter RP</h1>"
            "<p>WebUI assets have not been built yet.</p>"
            "</body></html>"
        )

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    app.include_router(create_dashboard_router(auth_dependency))
    app.include_router(create_accounts_router(auth_dependency, account_service))
    app.include_router(create_sessions_router(auth_dependency, session_service))
    app.include_router(create_history_router(auth_dependency, history_service))
    app.include_router(create_debug_router(auth_dependency, debug_service))
    app.include_router(create_characters_router(auth_dependency, character_service))
    return app
