from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware

from database import db, create_indexes
from security import hash_password, verify_password, resolve_user_from_token
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
from registry_common import refresh_expired
from routers.integrations import router as integrations_router
from mqtt_bus import bus as mqtt_bus
from beward_ingest import watch_loop as beward_watch_loop
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="PI-ACCESS API", version="1.0.0", description="Sistema de Controle de Acesso Corporativo")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"name": "PI-ACCESS", "status": "online", "drivers": available_brands()}


@api_router.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


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
api_router.include_router(access_router)
api_router.include_router(equipment_router)
api_router.include_router(org_router)
api_router.include_router(cadastros_router)
api_router.include_router(beward_router)
api_router.include_router(registry_router)
api_router.include_router(visitors_reg_router)
api_router.include_router(integrations_router)

app.include_router(api_router)


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    user = await resolve_user_from_token(token)
    if not user:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
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
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def permissions_policy(request, call_next):
    resp = await call_next(request)
    resp.headers["Permissions-Policy"] = "camera=(self)"
    return resp


async def expiry_loop():
    while True:
        try:
            await refresh_expired()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"expiry_loop: {e}")
        await asyncio.sleep(600)


SEED_USERS = [
    ("operador@nxaccess.com", "Operador@2026", "Carlos Operador", "operator"),
    ("recepcao@nxaccess.com", "Recepcao@2026", "Beatriz Recepção", "reception"),
    ("leitura@nxaccess.com", "Leitura@2026", "Daniel Leitura", "viewer"),
]


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Felipe Ferreira", "role": "admin", "site_ids": [], "active": True,
            "token_version": 0, "created_at": datetime.now(timezone.utc).isoformat()})
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
    for email, pwd, name, role in SEED_USERS:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({
                "email": email, "password_hash": hash_password(pwd), "name": name,
                "role": role, "site_ids": [], "active": True, "token_version": 0,
                "created_at": datetime.now(timezone.utc).isoformat()})


@app.on_event("startup")
async def on_startup():
    await create_indexes()
    await seed_admin()
    result = await generate_seed()
    logger.info(f"Seed: {result}")
    start_simulator()
    asyncio.create_task(expiry_loop())
    if not await db.settings.find_one({"id": "mqtt"}) and os.environ.get("MQTT_BROKER"):
        await db.settings.insert_one({"id": "mqtt", "host": os.environ["MQTT_BROKER"],
                                      "port": int(os.environ.get("MQTT_PORT", "1883")), "username": "",
                                      "password_enc": "", "client_id": "pi-access-server", "enabled": True})
    await mqtt_bus.start()
    asyncio.create_task(beward_watch_loop())
    logger.info("PI-ACCESS backend iniciado")


@app.on_event("shutdown")
async def on_shutdown():
    stop_simulator()
