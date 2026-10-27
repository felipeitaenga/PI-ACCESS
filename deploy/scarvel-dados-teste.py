#!/usr/bin/env python3
"""
scarvel-dados-teste.py — cria dados FICTÍCIOS de teste num cliente SCARVEL (via API, com as validações do sistema).
Só para ambiente de homologação. Todos os registros levam "(TESTE)" no nome para achar e apagar depois.

  python3 scarvel-dados-teste.py --url https://pilares.scarvel.com.br
  (pede e-mail e senha do Administrador)

Cria: 3 empresas, 6 fixos (funcionários), 4 terceiros, 4 visitas (2 presentes agora, 2 agendadas p/ amanhã).
Sem foto: os cadastros não vão para o facial (para testar no facial, adicione uma foto real com consentimento).
"""
import argparse
import getpass
import json
import random
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

T = " (TESTE)"


def cpf():
    n = [random.randint(0, 9) for _ in range(9)]
    for k in (10, 11):
        s = sum(d * w for d, w in zip(n, range(k, 1, -1))) % 11
        n.append(0 if s < 2 else 11 - s)
    return "".join(map(str, n))


def cnpj():
    n = [random.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    for w in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        s = sum(d * p for d, p in zip(n, w)) % 11
        n.append(0 if s < 2 else 11 - s)
    d = "".join(map(str, n))
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


class Api:
    def __init__(self, url, token=""):
        self.url, self.token = url.rstrip("/") + "/api", token
        self.ctx = ssl.create_default_context()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=60) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} → {e.code}: {e.read().decode()[:300]}") from None
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            raise RuntimeError(f"{method} {path} → sem resposta válida da API ({e}). Confira o --url.") from None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", default="", help="(opcional) usar token em vez de login")
    a = ap.parse_args()
    api = Api(a.url, a.token)
    if not a.token:
        email = input("E-mail do Administrador: ").strip()
        api.token = api.call("POST", "/auth/login", {"email": email, "password": getpass.getpass("Senha: ")})["access_token"]
    print("✔ login")

    cats = api.call("GET", "/access/categories?limit=200")["items"]
    cats = [c for c in cats if c.get("enabled", True)]
    if not cats:
        sys.exit("Nenhuma categoria cadastrada. Rode antes: scarvel padrao <cliente>")
    pick = lambda *words: next((c for c in cats if any(w in (c.get("code", "") + " " + c.get("description", "")).lower() for w in words)), cats[0])
    cat_func, cat_terc = pick("func", "colab"), pick("terc", "prest")
    types = api.call("GET", "/visits/types?active=true")
    if not types:
        sys.exit("Nenhum tipo de visita ativo. Cadastre um em Tipos de visita.")
    vtype = types[0]
    print(f"✔ categorias: fixos={cat_func.get('code')}  terceiros={cat_terc.get('code')}  · tipo de visita: {vtype['name']}")

    empresas = [("Alfa Engenharia Ltda", "Alfa Engenharia", ""), ("Beta Serviços de Limpeza Ltda", "Beta Limpeza", "terceirizada"),
                ("Gama Tecnologia S.A.", "Gama Tec", "")]
    comp = {}
    for name, trade, typ in empresas:
        c = api.call("POST", "/org/companies", {"name": name + T, "trade_name": trade, "cnpj": cnpj(), "type": typ,
                                                "enabled": True, "contract_valid_until": None, "default_category_id": None})
        comp[trade] = c["id"]
        print(f"  + empresa  {name}{T}")

    hoje = datetime.now(timezone.utc)
    fixos = [("Ana Paula Martins", "Alfa Engenharia", "Gerente de Projetos", True), ("Bruno Carvalho Souza", "Alfa Engenharia", "Engenheiro Civil", True),
             ("Camila Rocha Lima", "Alfa Engenharia", "Analista Administrativa", False), ("Diego Fernandes Alves", "Gama Tec", "Coordenador de TI", True),
             ("Elisa Moura Castro", "Gama Tec", "Desenvolvedora", False), ("Fábio Nogueira Pinto", "Gama Tec", "Suporte Técnico", False)]
    hosts = {}
    for i, (name, emp, cargo, anfitriao) in enumerate(fixos, 1):
        p = api.call("POST", "/registry/people", {
            "person_type": "funcionario", "name": name + T, "doc_type": "cpf", "doc_number": cpf(), "company_id": comp[emp],
            "category_ids": [cat_func["id"]], "role_title": cargo, "matricula": f"T{1000 + i}", "status": "ativo",
            "email": f"teste{i}@exemplo.com", "phone": "(11) 90000-00%02d" % i, "can_authorize_visits": anfitriao})
        if anfitriao and emp not in hosts:
            hosts[emp] = (p.get("person") or p)["id"]
        print(f"  + fixo     {name}{T} · {emp}")

    terceiros = [("Gustavo Ribeiro Dias", "Beta Limpeza", "Auxiliar de Limpeza"), ("Helena Barros Costa", "Beta Limpeza", "Encarregada"),
                 ("Igor Teixeira Melo", "Beta Limpeza", "Auxiliar de Limpeza"), ("Juliana Freitas Lopes", "Beta Limpeza", "Copeira")]
    for name, emp, cargo in terceiros:
        api.call("POST", "/registry/people", {
            "person_type": "terceiro", "name": name + T, "doc_type": "cpf", "doc_number": cpf(), "company_id": comp[emp],
            "category_ids": [cat_terc["id"]], "function": cargo, "status": "ativo",
            "valid_from": hoje.date().isoformat(), "valid_until": (hoje + timedelta(days=90)).date().isoformat()})
        print(f"  + terceiro {name}{T} · {emp} (válido 90 dias)")

    amanha = (hoje + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)  # 09:00 de Brasília
    visitas = [("Karen Duarte Pires", "Fornecedor XYZ", "Reunião comercial", "Alfa Engenharia", None),
               ("Leonardo Santos Viana", "Transportes Rápido", "Entrega de material", "Alfa Engenharia", None),
               ("Mariana Azevedo Cruz", "Consultoria Delta", "Treinamento", "Gama Tec", amanha),
               ("Nelson Prado Farias", "Elevadores Sul", "Manutenção preventiva", "Gama Tec", amanha + timedelta(hours=2))]
    for name, origem, motivo, emp, inicio in visitas:
        if emp not in hosts:
            continue
        body = {"visit_type_id": vtype["id"], "host_company_id": comp[emp], "host_person_id": hosts[emp], "name": name + T,
                "doc_type": "cpf", "doc_number": cpf(), "visitor_company": origem, "visit_reason": motivo,
                "identifier": {"type": "qrcode"}}
        if inicio:
            body["start_at"] = inicio.isoformat()
        api.call("POST", "/visits", body)
        print(f"  + visita   {name}{T} → {emp} · {'agendada ' + inicio.strftime('%d/%m') if inicio else 'presente agora'}")
    print("\nPronto. Para apagar depois: busque por \"(TESTE)\" em Empresas, Pessoas e Visitas.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"ERRO: {e}")
