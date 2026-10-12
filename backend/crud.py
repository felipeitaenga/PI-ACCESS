"""CRUD genérico com soft-delete, busca, paginação, bulk e auditoria."""
from fastapi import Depends, HTTPException, Request
from database import db
from security import get_current_user, require_role
from models import new_id, now_iso
from util import log_audit, client_ip


def make_crud(router, path, coll, search_fields=None, sort="created_at",
              write_roles=("admin", "operator"), enrich=None, default_doc=None, on_delete=None):
    search_fields = search_fields or []
    label = coll

    async def _list(q: str = "", enabled: str = "", page: int = 1, limit: int = 20,
                    user: dict = Depends(get_current_user)):
        query = {"deleted": {"$ne": True}}
        if q and search_fields:
            query["$or"] = [{f: {"$regex": q, "$options": "i"}} for f in search_fields]
        if enabled in ("true", "false"):
            query["enabled"] = (enabled == "true")
        total = await db[coll].count_documents(query)
        items = await db[coll].find(query, {"_id": 0}).sort(sort, 1).skip((page - 1) * limit).limit(limit).to_list(limit)
        return {"items": items, "total": total, "page": page, "limit": limit}

    async def _all(user: dict = Depends(get_current_user)):
        from scope import scope_filter
        return await db[coll].find({"deleted": {"$ne": True}, **(await scope_filter(user, coll))}, {"_id": 0}).sort(sort, 1).to_list(2000)

    async def _get(item_id: str, user: dict = Depends(get_current_user)):
        doc = await db[coll].find_one({"id": item_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Não encontrado")
        return doc

    async def _create(body: dict, request: Request, user: dict = Depends(require_role(*write_roles))):
        doc = {**(default_doc or {}), **body}
        doc["id"] = new_id()
        doc["enabled"] = doc.get("enabled", True)
        doc["deleted"] = False
        doc["created_at"] = now_iso()
        if enrich:
            doc = await enrich(doc)
        await db[coll].insert_one(dict(doc))
        doc.pop("_id", None)
        await log_audit(user, "criar", label, doc["id"],
                        str(body.get("description") or body.get("name") or body.get("code") or ""),
                        client_ip(request))
        return doc

    async def _update(item_id: str, body: dict, request: Request, user: dict = Depends(require_role(*write_roles))):
        before = await db[coll].find_one({"id": item_id}, {"_id": 0})
        if not before:
            raise HTTPException(status_code=404, detail="Não encontrado")
        body.pop("id", None)
        body.pop("_id", None)
        upd = {**before, **body}
        if enrich:
            upd = await enrich(upd)
        upd.pop("_id", None)
        await db[coll].update_one({"id": item_id}, {"$set": upd})
        after = await db[coll].find_one({"id": item_id}, {"_id": 0})
        await log_audit(user, "editar", label, item_id,
                        f"alterou {list(body.keys())}", client_ip(request))
        return after

    async def _delete(item_id: str, request: Request, user: dict = Depends(require_role(*write_roles))):
        await db[coll].update_one({"id": item_id}, {"$set": {"deleted": True, "enabled": False}})
        if on_delete:
            await on_delete([item_id])
        await log_audit(user, "excluir", label, item_id, "exclusão lógica", client_ip(request))
        return {"ok": True}

    async def _bulk(body: dict, request: Request, user: dict = Depends(require_role(*write_roles))):
        ids = body.get("ids", [])
        action = body.get("action")
        if action == "enable":
            await db[coll].update_many({"id": {"$in": ids}}, {"$set": {"enabled": True}})
        elif action == "disable":
            await db[coll].update_many({"id": {"$in": ids}}, {"$set": {"enabled": False}})
        elif action == "delete":
            await db[coll].update_many({"id": {"$in": ids}}, {"$set": {"deleted": True, "enabled": False}})
            if on_delete:
                await on_delete(ids)
        else:
            raise HTTPException(status_code=400, detail="Ação inválida")
        await log_audit(user, f"bulk_{action}", label, ",".join(ids[:5]), f"{len(ids)} itens", client_ip(request))
        return {"ok": True, "affected": len(ids)}

    router.add_api_route(path, _list, methods=["GET"], name=f"{coll}_list")
    router.add_api_route(path + "/all", _all, methods=["GET"], name=f"{coll}_all")
    router.add_api_route(path + "/bulk", _bulk, methods=["POST"], name=f"{coll}_bulk")
    router.add_api_route(path + "/{item_id}", _get, methods=["GET"], name=f"{coll}_get")
    router.add_api_route(path, _create, methods=["POST"], name=f"{coll}_create")
    router.add_api_route(path + "/{item_id}", _update, methods=["PUT"], name=f"{coll}_update")
    router.add_api_route(path + "/{item_id}", _delete, methods=["DELETE"], name=f"{coll}_delete")
