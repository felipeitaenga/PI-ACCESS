from fastapi import APIRouter
from database import db
from crud import make_crud

router = APIRouter(prefix="/org", tags=["org"])

make_crud(router, "/companies", "companies", search_fields=["name", "cnpj", "trade_name"], sort="name")
make_crud(router, "/company-groups", "company_groups", search_fields=["name"], sort="name")
make_crud(router, "/departments", "departments", search_fields=["name"], sort="name")
