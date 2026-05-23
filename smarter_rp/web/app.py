from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from smarter_rp.config import SmarterRpConfig
from smarter_rp.tavern_bindings import TavernBindingService
from smarter_rp.web.auth import resolve_token
from smarter_rp.web import routes_bindings, routes_characters, routes_status, routes_worldbooks


def create_web_app(
    *,
    client: Any,
    bindings: TavernBindingService,
    config: SmarterRpConfig,
    webui_token: str | None = None,
) -> FastAPI:
    app = FastAPI(title="AstrBot Smarter RP WebUI")
    app.state.tavern_client = client
    app.state.bindings = bindings
    app.state.config = config
    app.state.webui_token = webui_token or resolve_token(str(config.webui.get("token", "") or ""))

    app.include_router(routes_status.router)
    app.include_router(routes_characters.router)
    app.include_router(routes_worldbooks.router)
    app.include_router(routes_bindings.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        for error in exc.errors():
            if error.get("type") == "missing" and tuple(error.get("loc", ())) == ("body", "file"):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Missing file"},
                )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})

    static_dir = _find_static_dir()
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="webui")

    return app


def _find_static_dir() -> Path | None:
    package_static = Path(__file__).with_name("static")
    if package_static.exists():
        return package_static

    project_root = Path(__file__).resolve().parents[2]
    webui_dist = project_root / "webui" / "dist"
    if webui_dist.exists():
        return webui_dist
    return None
