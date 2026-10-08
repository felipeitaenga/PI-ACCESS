# NX-ACCESS

Sistema profissional de **Controle de Acesso** corporativo (pt-BR) — padrão de mercado comparável a Genetec Synergis / LenelS2 / Control iD iDSecure.

- **Backend**: FastAPI + MongoDB + WebSocket (eventos em tempo real)
- **Frontend**: React + Tailwind + shadcn/ui + Recharts
- **Auth**: JWT (cookie httpOnly + Bearer token) com refresh e bcrypt
- **Drivers**: camada Adapter (Control iD, Hikvision, Intelbras, ZKTeco, **SIMULADO**)

## Módulos (entrega atual — núcleo)
Dashboard · Monitoramento ao vivo · Pessoas · Dispositivos (driver simulado) · Estrutura (Sites>Áreas>Portas>Dispositivos) · Alarmes · Emergência/Incêndio · Relatórios · Administração (usuários, auditoria, configurações).

## Usuários padrão (seed)
| Perfil | E-mail | Senha |
|---|---|---|
| Administrador | felipejferreira@gmail.com | NxAccess@2026 |
| Operador | operador@nxaccess.com | Operador@2026 |
| Recepção | recepcao@nxaccess.com | Recepcao@2026 |
| Somente leitura | leitura@nxaccess.com | Leitura@2026 |

Dados de exemplo são gerados automaticamente: 1 site, 3 áreas, 6 portas, 4 dispositivos simulados, 50 pessoas e eventos dos últimos 7 dias. Um simulador gera eventos contínuos para demonstração.

---

## Desenvolvimento local
```bash
# Backend
cd backend && pip install -r requirements.txt
# Frontend
cd frontend && yarn install
```
Serviços são gerenciados por supervisor (backend :8001, frontend :3000, mongo).

### Variáveis de ambiente
`backend/.env`: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `FERNET_KEY` (senhas de dispositivos), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `FRONTEND_URL`, `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME`.
`frontend/.env`: `REACT_APP_BACKEND_URL`.
Nunca comite credenciais; use sempre `.env`.

---

## Deploy em Docker (servidor Linux próprio, atrás de proxy reverso HTTPS)

Exemplo de `docker-compose.yml`:
```yaml
version: "3.9"
services:
  mongo:
    image: mongo:7
    restart: always
    volumes: ["mongo_data:/data/db"]
    networks: [nx]

  backend:
    build: ./backend
    restart: always
    environment:
      - MONGO_URL=mongodb://mongo:27017
      - DB_NAME=nxaccess
      - JWT_SECRET=${JWT_SECRET}
      - FERNET_KEY=${FERNET_KEY}
      - ADMIN_EMAIL=${ADMIN_EMAIL}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - FRONTEND_URL=https://acesso.suaempresa.com
    depends_on: [mongo]
    networks: [nx]

  frontend:
    build: ./frontend
    restart: always
    environment:
      - REACT_APP_BACKEND_URL=https://acesso.suaempresa.com
    depends_on: [backend]
    networks: [nx]

volumes: { mongo_data: {} }
networks: { nx: {} }
```
Coloque Nginx/Traefik como proxy reverso com certificado TLS (Let's Encrypt), roteando `/api` → backend:8001 e o restante → frontend:3000. Gere segredos:
```bash
python -c "import secrets;print(secrets.token_hex(32))"              # JWT_SECRET
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # FERNET_KEY
```

---

## Agente local (EDGE) — `nx-access-agent` (próxima iteração)
Serviço Python separado para rodar na rede do cliente (PC/mini-PC/Raspberry):
- Conversa com os equipamentos na LAN e conecta ao servidor central por **WebSocket/MQTT com TLS** usando um **token de site**.
- **Fila local SQLite** para guardar eventos quando o servidor estiver offline e reenviar depois.
- Dispositivos de um site podem ser **"acesso direto"** (servidor alcança o IP) ou **"via agente"** (campo `connection_mode` no cadastro de dispositivo).

Estrutura planejada: `agent/main.py` (loop de conexão + reconexão), `agent/queue.py` (SQLite), `agent/devices/` (reuso dos drivers), `agent/.env` (`SERVER_URL`, `SITE_TOKEN`).

---

## Como adicionar um novo driver de equipamento
A comunicação usa o padrão **Adapter**. Para adicionar uma marca, **não** é preciso alterar o núcleo:

1. Crie `backend/drivers/minhamarca.py` herdando de `AccessControlDriver` (`backend/drivers/base.py`) e implemente a interface comum:
   `connect`, `get_status`, `get_device_info`, `open_door`, `set_door_mode`, `sync_person`, `delete_person`, `sync_face`, `sync_card`, `sync_access_rules`, `get_events`, `set_datetime`, `reboot`.
2. Registre no factory (`backend/drivers/factory.py`):
   ```python
   from .minhamarca import MinhaMarcaDriver
   register_driver("minhamarca", MinhaMarcaDriver)
   ```
3. Adicione a marca na lista de `/api/devices/brands` (router `devices.py`). Pronto — o dispositivo poderá ser cadastrado com essa marca e o sistema usará o driver automaticamente via `get_driver(device)`.

Exemplo de referência: `backend/drivers/simulated.py`.

---

## Segurança & LGPD
- Senhas de dispositivos criptografadas com **Fernet/AES** (`FERNET_KEY`).
- Senhas de usuários com **bcrypt**; rate limit no login; logs sem dados sensíveis.
- Termo de consentimento vinculado ao cadastro biométrico; exclusão definitiva de pessoa remove biometria.
- Retenção configurável de eventos/fotos em Administração > Configurações.
