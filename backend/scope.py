"""Escopo por empresa (perfil Gestor de empresa). Toda rota usa estes helpers; o backend é a proteção real."""
import re
from fastapi import HTTPException
from database import db

MANAGER = "company_manager"
ND = {"deleted": {"$ne": True}}

# Rotas liberadas ao gestor (o resto da API responde 403). Escopo de dados é aplicado dentro de cada rota.
MANAGER_ALLOW = [
    ("GET", r"/api/(health|version)"),
    ("*", r"/api/auth/(me|logout|refresh|login)"),
    ("POST", r"/api/auth/users"),
    ("GET", r"/api/dashboard/stats"),
    ("GET", r"/api/reports/(access|presence)"),
    ("*", r"/api/registry/(people|people/bulk|photo/check)"),
    ("GET", r"/api/registry/(people/[^/]+|companies|search|visitors|visitors/lookup|visitors/[^/]+|visits/present|visitor-companies)"),
    ("PUT", r"/api/registry/people/[^/]+"),
    ("*", r"/api/visits(/.*)?"),
    ("*", r"/api/selfreg(/.*)?"),
    ("*", r"/api/public/.*"),
    ("GET", r"/api/events"),
    ("GET", r"/api/access/categories/all"),
    ("GET", r"/api/org/departments/all"),
]
_ALLOW = [(m, re.compile(p + r"/?$")) for m, p in MANAGER_ALLOW]


def is_manager(user):
    return (user or {}).get("role") == MANAGER


def manager_allowed(method, path):
    return any((m == "*" or m == method) and rx.match(path) for m, rx in _ALLOW)


def cids(user):
    return list(user.get("company_ids") or [])


async def visitor_ids(user):
    """Visitantes que já visitaram as empresas do gestor (LGPD)."""
    return await db.visits.distinct("visitor_id", {"host_company_id": {"$in": cids(user)}})


async def scope_filter(user, coll):
    """Filtro Mongo a aplicar na coleção para o usuário logado ({} = sem restrição)."""
    if not is_manager(user):
        return {}
    c = cids(user)
    if coll in ("people",):
        return {"company_id": {"$in": c}}
    if coll == "companies":
        return {"id": {"$in": c}}
    if coll == "visits":
        return {"host_company_id": {"$in": c}}
    if coll == "visitors":
        return {"id": {"$in": await visitor_ids(user)}}
    if coll == "access_events":
        return {"company_id": {"$in": c}}
    if coll == "categories":
        return {"id": {"$in": await allowed_ids(user, "allowed_category_ids")}}
    if coll == "visit_types":
        return {"id": {"$in": await allowed_ids(user, "allowed_visit_type_ids")}}
    if coll in ("identifiers", "vehicles", "person_documents"):
        return {"person_id": {"$in": await db.people.distinct("id", {"company_id": {"$in": c}})}}
    return {"_id": None}


async def allowed_ids(user, field):
    out = set()
    async for comp in db.companies.find({"id": {"$in": cids(user)}}, {"_id": 0, field: 1}):
        out.update(comp.get(field) or [])
    return list(out)


async def find_scoped(user, coll, doc_id, projection=None, msg="Registro não encontrado"):
    """Busca por id dentro do escopo; fora dele responde 404 (não revela existência)."""
    doc = await db[coll].find_one({"$and": [{"id": doc_id}, await scope_filter(user, coll)]}, projection or {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=msg)
    return doc


def require_company(user, company_id):
    if is_manager(user) and company_id not in cids(user):
        raise HTTPException(status_code=422, detail={"msg": "Empresa não permitida", "fields": {"company_id": "Escolha uma das suas empresas"}})


async def event_company_id(person_id, at_iso=None):
    """Empresa dona do evento: empresa da pessoa fixa, ou empresa visitada da visita ativa do visitante."""
    if not person_id:
        return None
    p = await db.people.find_one({"id": person_id}, {"_id": 0, "company_id": 1})
    if p:
        return p.get("company_id")
    q = {"visitor_id": person_id}
    if at_iso:
        q.update({"start_at": {"$lte": at_iso}, "end_at": {"$gte": at_iso}})
    v = await db.visits.find_one(q, {"_id": 0, "host_company_id": 1}, sort=[("start_at", -1)])
    if not v and at_iso:
        v = await db.visits.find_one({"visitor_id": person_id, "status": {"$in": ["presente", "agendado"]}},
                                     {"_id": 0, "host_company_id": 1})
    return (v or {}).get("host_company_id")


async def stamp_event(ev):
    if ev.get("company_id") is None:
        ev["company_id"] = await event_company_id(ev.get("person_id"), ev.get("timestamp"))
    return ev


def ws_visible(user, message):
    """Filtro do WebSocket: gestor só recebe eventos das suas empresas e nada de alarmes/equipamentos."""
    if not is_manager(user):
        return True
    if message.get("type") != "access_event":
        return message.get("type") in ("connected",)
    return (message.get("data") or {}).get("company_id") in cids(user)
