from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from scope import is_manager, manager_allowed
from util import log_audit
from starlette.middleware.cors import CORSMiddleware

import app_config as cfg
from database import db, create_indexes
from migrations import run_migrations
from security import hash_password, resolve_user_from_token
from drivers.factory import available_brands
from realtime import manager, start_simulator, stop_simulator
from seed import generate_seed

from routers.auth import router as auth_router
from routers.structure import router as structure_router
from routers.people import router as people_router
from routers.devices import router as devices_router
from routers.events import router as events_router, alarms_router, emergency_router, admin_router
from routers.dashboard import router as dashboard_router, reports_router
from routers.access_model import router as access_router
from routers.equipment import router as equipment_router
from routers.org import router as org_router
from routers.cadastros import router as cadastros_router
from routers.beward import router as beward_router
from routers.registry import router as registry_router
from routers.visitors_reg import router as visitors_reg_router
from routers.visits import router as visits_router
from routers.backups import router as backups_router
from routers.selfreg import router as selfreg_router, public as selfreg_public
from routers.reports import router as reports_v2_router
from routers.lgpd import router as lgpd_router
from registry_common import refresh_expired
from routers.integrations import router as integrations_router
from routers.intelbras import router as intelbras_router
from routers.vpn import router as vpn_router
from mqtt_bus import bus as mqtt_bus
from beward_ingest import watch_loop as beward_watch_loop
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="SCARVEL API", version=cfg.APP_VERSION, description="Sistema de Controle de Acesso Corporativo")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"name": "SCARVEL", "status": "online", "drivers": available_brands()}


@api_router.get("/health")
async def health(response: Response):
    try:
        await db.command("ping")
        mongo = "ok"
    except Exception as e:  # noqa: BLE001
        mongo = f"erro: {e}"
    st = mqtt_bus.status()
    mqtt = "conectado" if st["connected"] else ("desconectado" if st["enabled"] else "desabilitado")
    if mongo != "ok":
        response.status_code = 503
    return {"status": "ok" if mongo == "ok" else "erro", "mongo": mongo, "mqtt": mqtt,
            "mqtt_topics": st.get("topics"), "version": cfg.APP_VERSION, "cliente": cfg.CLIENTE,
            "ts": datetime.now(timezone.utc).isoformat()}


@api_router.get("/version")
async def version():
    return {"version": cfg.APP_VERSION, "cliente": cfg.CLIENTE, "cliente_nome": cfg.CLIENTE_NOME,
            "email_enabled": cfg.EMAIL_ENABLED, "demo": cfg.SEED_DEMO}


api_router.include_router(auth_router)
api_router.include_router(structure_router)
api_router.include_router(people_router)
api_router.include_router(devices_router)
api_router.include_router(events_router)
api_router.include_router(alarms_router)
api_router.include_router(emergency_router)
api_router.include_router(admin_router)
api_router.include_router(dashboard_router)
api_router.include_router(reports_router)
api_router.include_router(reports_v2_router)
api_router.include_router(lgpd_router)
api_router.include_router(access_router)
api_router.include_router(equipment_router)
api_router.include_router(org_router)
api_router.include_router(cadastros_router)
api_router.include_router(beward_router)
api_router.include_router(registry_router)
api_router.include_router(visits_router)
api_router.include_router(backups_router)
api_router.include_router(selfreg_router)
api_router.include_router(selfreg_public)
api_router.include_router(visitors_reg_router)
api_router.include_router(integrations_router)
api_router.include_router(intelbras_router)
api_router.include_router(vpn_router)

app.include_router(api_router)


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    user = await resolve_user_from_token(token)
    if not user:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, user)
    try:
        await websocket.send_json({"type": "connected", "data": {"user": user.get("name")}})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[o for o in [cfg.PUBLIC_URL, *(os.environ.get("CORS_ORIGINS") or "").split(",")] if o.strip() and o.strip() != "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def permissions_policy(request, call_next):
    resp = await call_next(request)
    resp.headers["Permissions-Policy"] = "camera=(self)"
    return resp


@app.middleware("http")
async def company_manager_gate(request, call_next):
    """Gestor de empresa: só rotas liberadas (resto 403) e auditoria de toda ação."""
    path = request.url.path
    if not path.startswith("/api/") or request.method == "OPTIONS":
        return await call_next(request)
    auth = request.headers.get("authorization") or ""
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get("access_token")
    user = await resolve_user_from_token(token) if token else None
    if not is_manager(user):
        return await call_next(request)
    if not manager_allowed(request.method, path):
        return JSONResponse(status_code=403, content={"detail": "Permissão insuficiente"})
    resp = await call_next(request)
    if request.method != "GET":
        await log_audit(user, f"gestor:{request.method}", "api", path,
                        f"empresas={','.join(user.get('company_ids') or [])} status={resp.status_code}",
                        request.client.host if request.client else "")
    return resp


async def expiry_loop():
    while True:
        try:
            await refresh_expired()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"expiry_loop: {e}")
        await asyncio.sleep(600)


async def visits_loop():
    from visits_core import visits_tick
    while True:
        try:
            await visits_tick()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"visits_loop: {e}")
        await asyncio.sleep(60)


SEED_USERS = [
    ("operador@nxaccess.com", "Operador@2026", "Carlos Operador", "operator"),
    ("recepcao@nxaccess.com", "Recepcao@2026", "Beatriz Recepção", "reception"),
    ("leitura@nxaccess.com", "Leitura@2026", "Daniel Leitura", "viewer"),
]


async def seed_admin():
    """Cria o administrador inicial SOMENTE se não existir nenhum usuário."""
    if await db.users.count_documents({}) == 0:
        email, pwd = os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD")
        if not email or not pwd:
            logger.error("Nenhum usuário e ADMIN_EMAIL/ADMIN_PASSWORD não definidos — use python -m app.reset_admin")
        else:
            await db.users.insert_one({
                "email": email.strip().lower(), "password_hash": hash_password(pwd),
                "name": "Administrador", "role": "admin", "site_ids": [], "active": True,
                "token_version": 0, "created_at": datetime.now(timezone.utc).isoformat()})
            logger.info(f"Administrador inicial criado: {email}")
    if not cfg.SEED_DEMO:
        return
    for email, pwd, name, role in SEED_USERS:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({
                "email": email, "password_hash": hash_password(pwd), "name": name,
                "role": role, "site_ids": [], "active": True, "token_version": 0,
                "created_at": datetime.now(timezone.utc).isoformat()})


@app.on_event("startup")
async def on_startup():
    for sub in ("photos", "uploads", "exports"):
        os.makedirs(os.path.join(cfg.DATA_DIR, sub), exist_ok=True)
    await create_indexes()
    await run_migrations()
    await seed_admin()
    if cfg.SEED_DEMO:
        result = await generate_seed()
        logger.info(f"Seed demo: {result}")
        start_simulator()
    else:
        import bootstrap
        await bootstrap.auto()
    asyncio.create_task(expiry_loop())
    asyncio.create_task(visits_loop())
    from backup_service import backup_loop
    asyncio.create_task(backup_loop())
    from selfreg_core import retention_loop
    asyncio.create_task(retention_loop())
    await mqtt_bus.start()
    asyncio.create_task(beward_watch_loop())
    from intelbras_ingest import watch_loop as intelbras_watch_loop
    asyncio.create_task(intelbras_watch_loop())
    import passage
    asyncio.create_task(passage.loop())
    logger.info(f"SCARVEL {cfg.APP_VERSION} iniciado — cliente {cfg.CLIENTE}")


@app.on_event("shutdown")
async def on_shutdown():
    stop_simulator()
    await mqtt_bus.stop()


if cfg.STATIC_DIR and os.path.isdir(cfg.STATIC_DIR):
    _static_root = Path(cfg.STATIC_DIR).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Não encontrado")
        f = (_static_root / path).resolve()
        if path and f.is_file() and _static_root in f.parents:
            return FileResponse(f)
        return FileResponse(_static_root / "index.html", headers={"Cache-Control": "no-cache"})
