# NX-ACCESS — PRD

## Problem Statement (original)
Aplicação web profissional de CONTROLE DE ACESSO "NX-ACCESS", padrão corporativo (comparável a Genetec Synergis / LenelS2 / Control iD iDSecure). Interface pt-BR, tema escuro padrão + claro, layout painel de operação (sidebar + topbar + conteúdo), responsivo. Backend FastAPI + MongoDB + WebSocket; Frontend React + Tailwind + shadcn/ui + Recharts; JWT auth. Camada de drivers (Adapter) para equipamentos (Control iD, Hikvision, Intelbras, ZKTeco, SIMULADO), agente edge, e módulos completos (Dashboard, Monitoramento, Pessoas, Credenciais, Visitantes, Estrutura, Dispositivos, Regras, Emergência, Relatórios, Alarmes, Administração, Integrações). LGPD e segurança.

## Architecture
- **Backend** `/app/backend`: FastAPI, Motor (MongoDB async), WebSocket `/api/ws`. Modular: `security.py` (JWT+bcrypt+Fernet, RBAC), `routers/` (auth, structure, people, devices, events[alarms/emergency/admin], dashboard[reports]), `drivers/` (base Adapter + factory + simulated), `realtime.py` (ConnectionManager + event simulator), `seed.py`.
- **Frontend** `/app/frontend`: React 19, React Router, Tailwind + shadcn/ui, Recharts, sonner. `context/` (Auth, Realtime), `lib/api.js` (axios + Bearer token in localStorage + cookie), `pages/`, `components/Layout.jsx`.
- **Auth**: JWT access(15m)+refresh(7d). Dual transport: httpOnly Secure cookies AND Bearer token (localStorage) — fallback because preview/automation browsers reject Partitioned SameSite=None cookies. bcrypt hashing, login brute-force lockout, password reset via managed email.
- **Drivers**: `AccessControlDriver` ABC + `factory.register_driver`. Adding a brand = new file + register, no core change. SIMULADO implemented; Control iD/Hikvision/Intelbras/ZKTeco are registration stubs for next iteration.

## Personas
- **Administrador**: full control, user mgmt, audit, settings, LGPD deletion.
- **Operador**: operations, devices, doors, alarms, emergency.
- **Recepção**: people, visitors, remote door open.
- **Somente leitura**: view-only.

## Core Requirements (static)
Auth+RBAC · Structure (Sites>Áreas>Portas>Dispositivos) · People (CRUD/CSV/photo) · Devices (simulated driver, test/sync, heartbeat) · Live Monitoring (WS feed, facial inspect, remote open w/ confirmation+audit) · Dashboard (KPIs, hourly flow, recent) · Alarms (ack) · Emergency (lockdown + muster) · Reports (access/occupancy/presence) · Admin (users/audit/settings). Timezone America/Sao_Paulo.

## Implemented (2026-06)
- [x] JWT auth (cookie+Bearer), refresh, reset-password flow, 4 role profiles, default admin (felipejferreira@gmail.com) + seeded operator/reception/viewer.
- [x] Structure CRUD; People CRUD + CSV import/export + webcam/photo + LGPD consent + definitive delete.
- [x] Devices with SIMULADO driver: test comms, manual sync with per-person sync log.
- [x] Live Monitoring WebSocket feed + facial inspector + remote door open/mode with audit.
- [x] Dashboard KPIs + Recharts hourly flow + recent events (realtime).
- [x] Alarms (priority/ack/comment), Emergency (lockdown + muster report), Reports (3), Admin (users+audit+settings).
- [x] Seed: 1 site, 3 áreas, 6 portas, 4 dispositivos, 50 pessoas, 7 dias de eventos + simulador contínuo.
- [x] README (Docker deploy, agente edge, adicionar driver).
- Verified: testing agent iteration_1 — backend 28/28, frontend 100%.

## Backlog (prioritized)
- **P1 Drivers reais**: Control iD (login.fcgi/load_objects), Hikvision ISAPI Digest, Intelbras CGI, ZKTeco PUSH/ADMS.
- **P1 Agente edge** (`nx-access-agent`): LAN↔servidor via WebSocket/MQTT TLS, fila SQLite offline, site token.
- **P1 Credenciais** completo (facial/cartão Wiegand/MIFARE/QR/PIN/placa) UI; **Visitantes** (pré-cadastro, QR por e-mail Resend, check-in/out, expiração).
- **P2 Regras de acesso**: zonas de tempo, feriados, níveis, anti-passback runtime, intertravamento, dupla validação, limite ocupação.
- **P2 Integrações**: Swagger público, webhooks, MQTT publish, endpoint alarme externo (incêndio/BMS); exportação PDF/Excel nos relatórios; retenção automática (cron) LGPD.

## Next Tasks
1. Implement real Control iD driver + device connection test against real API.
2. Build nx-access-agent service skeleton with SQLite queue.
3. Credenciais + Visitantes modules (Resend email QR).
