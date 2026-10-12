#!/usr/bin/env python3
"""
pi-empresas.py — cria empresas e usuários "Gestor de empresa" no PI-ACCESS em lote (via API).

Uso:
  python3 pi-empresas.py --url https://pilares.piaccess.pilaresautomacao.com.br \
                         --admin seu@email.com --arquivo empresas.csv
  (a senha do admin é pedida no terminal; ou use a variável PI_ADMIN_PASSWORD)

CSV (separado por ponto e vírgula, com cabeçalho):
  empresa;cnpj;tipo;categorias;tipos_visita;gestor_nome;gestor_email
  Transportadora X;12.345.678/0001-90;transportadora;CAMINHÃO|VISITANTE;Visita padrão;João Silva;joao@x.com.br

  tipo .......... propria | terceirizada | transportadora | cliente   (padrão: terceirizada)
  categorias .... nomes das categorias separados por |   (vazio = não altera)
  tipos_visita .. nomes dos tipos de visita separados por | (vazio = não altera)
  gestor_* ...... vazio = cria só a empresa

Rodar de novo não duplica: empresa existente (mesmo nome) é reaproveitada e
e-mail já cadastrado é ignorado.
"""
import argparse
import csv
import datetime
import getpass
import json
import os
import secrets
import ssl
import string
import sys
import urllib.error
import urllib.request

TIPOS = {"propria", "terceirizada", "transportadora", "cliente"}


class Api:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.token = None
        self.ctx = ssl.create_default_context()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + "/api" + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                raw = r.read().decode() or "null"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "null")
            except Exception:  # noqa: BLE001
                return e.code, None

    def login(self, email, password):
        st, js = self.call("POST", "/auth/login", {"email": email, "password": password})
        if st != 200 or not js or not js.get("access_token"):
            sys.exit(f"Falha no login do admin ({st}): {js}")
        if js.get("role") != "admin":
            sys.exit("O usuário informado não é administrador.")
        self.token = js["access_token"]


def senha_forte(n=14):
    alfabeto = string.ascii_letters + string.digits
    while True:
        s = "".join(secrets.choice(alfabeto) for _ in range(n))
        if any(c.islower() for c in s) and any(c.isupper() for c in s) and any(c.isdigit() for c in s):
            return s


def nomes(campo):
    return [x.strip() for x in (campo or "").split("|") if x.strip()]


def main():
    ap = argparse.ArgumentParser(description="Cria empresas e gestores no PI-ACCESS")
    ap.add_argument("--url", required=True, help="ex.: https://pilares.piaccess.pilaresautomacao.com.br")
    ap.add_argument("--admin", required=True, help="e-mail do administrador")
    ap.add_argument("--arquivo", required=True, help="CSV com as empresas (ver cabeçalho no topo do script)")
    a = ap.parse_args()

    api = Api(a.url)
    pwd = os.environ.get("PI_ADMIN_PASSWORD") or getpass.getpass(f"Senha de {a.admin}: ")
    api.login(a.admin, pwd)

    _, cats = api.call("GET", "/access/categories/all")
    _, vtypes = api.call("GET", "/visits/types")
    cat_por_nome = {(c.get("code") or "").strip().upper(): c["id"] for c in (cats or [])}
    vt_por_nome = {(t.get("name") or "").strip().upper(): t["id"] for t in (vtypes or [])}
    _, emps = api.call("GET", "/org/companies/all")
    emp_por_nome = {(e.get("name") or "").strip().upper(): e for e in (emps or [])}

    with open(a.arquivo, newline="", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    if not linhas:
        sys.exit("CSV vazio.")

    resultado, avisos = [], []
    for i, ln in enumerate(linhas, start=2):
        ln = {k.strip().lower(): (v or "").strip() for k, v in ln.items() if k}
        nome = ln.get("empresa", "")
        if not nome:
            avisos.append(f"linha {i}: sem nome de empresa — ignorada")
            continue
        tipo = (ln.get("tipo") or "terceirizada").lower()
        if tipo not in TIPOS:
            avisos.append(f"linha {i}: tipo '{tipo}' inválido — usando 'terceirizada'")
            tipo = "terceirizada"

        emp = emp_por_nome.get(nome.upper())
        if emp:
            acao_emp = "já existia"
        else:
            st, emp = api.call("POST", "/org/companies", {"name": nome, "cnpj": ln.get("cnpj", ""),
                                                         "trade_name": "", "type": tipo, "enabled": True})
            if st not in (200, 201) or not emp:
                avisos.append(f"linha {i}: erro ao criar empresa '{nome}' ({st}): {emp}")
                continue
            emp_por_nome[nome.upper()] = emp
            acao_emp = "criada"

        upd = {}
        cn = nomes(ln.get("categorias"))
        if cn:
            ids = [cat_por_nome[c.upper()] for c in cn if c.upper() in cat_por_nome]
            faltam = [c for c in cn if c.upper() not in cat_por_nome]
            if faltam:
                avisos.append(f"linha {i}: categorias não encontradas: {', '.join(faltam)}")
            upd["allowed_category_ids"] = ids
        vn = nomes(ln.get("tipos_visita"))
        if vn:
            ids = [vt_por_nome[t.upper()] for t in vn if t.upper() in vt_por_nome]
            faltam = [t for t in vn if t.upper() not in vt_por_nome]
            if faltam:
                avisos.append(f"linha {i}: tipos de visita não encontrados: {', '.join(faltam)}")
            upd["allowed_visit_type_ids"] = ids
        if upd:
            st, js = api.call("PUT", f"/org/companies/{emp['id']}", upd)
            if st != 200:
                avisos.append(f"linha {i}: erro ao liberar categorias/tipos ({st}): {js}")

        email = ln.get("gestor_email", "").lower()
        senha, acao_user = "", "-"
        if email:
            senha = senha_forte()
            st, js = api.call("POST", "/auth/users", {"email": email, "password": senha,
                                                      "name": ln.get("gestor_nome") or email.split("@")[0],
                                                      "role": "company_manager", "company_ids": [emp["id"]]})
            if st in (200, 201):
                acao_user = "criado"
            else:
                detalhe = (js or {}).get("detail") if isinstance(js, dict) else js
                acao_user, senha = f"não criado ({detalhe})", ""
        resultado.append({"empresa": nome, "empresa_status": acao_emp, "gestor_email": email or "-",
                          "gestor_status": acao_user, "senha": senha or "-"})

    print()
    print(f"{'EMPRESA':<32} {'STATUS':<11} {'GESTOR':<34} {'USUÁRIO':<22} SENHA")
    for r in resultado:
        print(f"{r['empresa'][:31]:<32} {r['empresa_status']:<11} {r['gestor_email'][:33]:<34} "
              f"{r['gestor_status'][:21]:<22} {r['senha']}")
    for av in avisos:
        print("AVISO:", av)

    saida = f"empresas-resultado-{datetime.datetime.now():%Y%m%d-%H%M}.csv"
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resultado[0].keys()) if resultado else ["empresa"], delimiter=";")
        w.writeheader()
        w.writerows(resultado)
    os.chmod(saida, 0o600)
    print(f"\nCredenciais salvas em {saida} (somente root pode ler). Envie a cada gestor e apague o arquivo depois.")


if __name__ == "__main__":
    main()
