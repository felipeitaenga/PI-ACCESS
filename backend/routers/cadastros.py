from fastapi import APIRouter
from database import db
from crud import make_crud

router = APIRouter(prefix="/cadastros", tags=["cadastros"])

make_crud(router, "/identifiers", "identifiers", search_fields=["value", "type"], sort="type")
make_crud(router, "/vehicles", "vehicles", search_fields=["plate", "model"], sort="plate")
make_crud(router, "/visitors", "visitors", search_fields=["name", "document"], sort="name")
make_crud(router, "/visits", "visits", search_fields=["reason"], sort="created_at")
