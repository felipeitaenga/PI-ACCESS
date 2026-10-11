"""Emergência: redefine (ou cria) um administrador.

No container:  docker exec -it piaccess_<cliente> python -m app.reset_admin [email] [nova_senha]
Sem e-mail usa ADMIN_EMAIL; sem senha gera uma aleatória e mostra na tela.
"""
import asyncio
import os
import secrets
import sys
from datetime import datetime, timezone

from database import db
from security import hash_password


async def main(args):
    email = (args[0] if args else os.environ["ADMIN_EMAIL"]).strip().lower()
    pwd = args[1] if len(args) > 1 else secrets.token_urlsafe(12)
    if len(pwd) < 8:
        sys.exit("A senha deve ter pelo menos 8 caracteres")
    h = hash_password(pwd)
    user = await db.users.find_one({"email": email})
    if user:
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": h, "active": True, "role": "admin"},
                                                         "$inc": {"token_version": 1}})
        acao = "redefinido"
    else:
        await db.users.insert_one({"email": email, "password_hash": h, "name": "Administrador", "role": "admin",
                                   "site_ids": [], "active": True, "token_version": 0,
                                   "created_at": datetime.now(timezone.utc).isoformat()})
        acao = "criado"
    await db.login_attempts.delete_many({"email": email})
    print(f"Administrador {acao}: {email}\nSenha: {pwd}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
