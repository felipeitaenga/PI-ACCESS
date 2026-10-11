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

## Refactor — Novo modelo de acesso (2026-06, etapas 1-4)
- [x] **Menu lateral configurável** (`src/config/menu.js`): grupos recolhíveis c/ estado salvo, modo recolhido (ícones+tooltip), busca Ctrl+K, favoritos (estrela, localStorage), filtro por permissão, drawer mobile, badge de alarmes.
- [x] **Hub de Configurações** (cards) + subpáginas (Geral, Usuários, Integrações, Atalhos, Simulador, Backup).
- [x] **Faixas horárias** (dias da semana, feriados, intervalos), **Feriados** (recorrente/abrangência), **Áreas** (anti-dupla, lotação calculada + EXTERIOR).
- [x] **Controladoras** (test/sync com resumo TZ/Áreas/Pontos/Regras/Pessoas) + **Pontos de acesso** (leitora+relé, origem→destino, sentido, tipo).
- [x] **Categorias** (abas Dados gerais com flags: control_origin, anti-dupla, escort, reentrada temporizada, impeditiva, contingência; Áreas de acesso c/ faixa+escort; Pessoas associadas em lote).
- [x] **Motor de decisão** puro e testável (`engine.py`, 12 testes unitários) + serviço (`access_service.py`) usado no realtime e no **Simulador** (passo a passo). Fluxo origem→destino, impeditiva, faixa horária, origem, anti-dupla, reentrada, lotação.
- [x] **Organização** (Empresas, Grupos, Departamentos), **Cadastros** (Identificadores, Veículos, Visitantes lista), **Logs** (Acessos, Auditoria, Sincronização), **Ocupação por área**.
- [x] CRUD genérico (`crud.py` / `CrudPage.jsx`): soft-delete, busca, paginação (Primeira/< n >/Última/Ver todas), seleção, Mais ações (habilitar/desabilitar/excluir/exportar CSV), auditoria.
- [x] Seed v3 recriado (mantém usuários): 7 áreas + EXTERIOR, 2 faixas, 2 feriados, 6 categorias, 2 controladoras, 6 pontos, 4 empresas, 5 deptos, 45 pessoas, 10 visitantes, 7 dias de eventos. current_area inicial por tipo (pedestre→Externa Pedestre, caminhão→Externa Caminhões).
- Verificado: 23 testes backend novos + 12 do motor passam; frontend (menu/busca/CRUD/categorias/simulador/configurações/ocupação/logs/RBAC) ok. Regressões corrigidas (occupancy/muster area description, favoritos, a11y DialogTitle).

## Backlog restante (etapas 5-7)
- **Etapa 5 — Pessoas fixas** em abas completas (Dados pessoais, Vínculo, Categorias, Identificadores, Veículos, Documentos ASO/NR c/ bloqueio por vencimento, Histórico).
- **Etapa 6 — Visitantes/Portaria**: pré-cadastro, agendamento, QR por e-mail (Resend), check-in/out, expiração, visitantes presentes.
- **Etapa 7 — Sincronização real com drivers** (Control iD time_zones/areas/portals/access_rules; Hikvision planos de horário) + drivers reais + agente edge.
- Limpeza: aposentar endpoints legados `/structure/doors` e `/devices` (substituídos por `/equipment/*`).

## Driver BEWARD B2002FR (2026-06)
- [x] **Dois transportes** com interface Adapter comum, selecionáveis no cadastro: `beward_http` e `beward_mqtt` (registrados no factory; núcleo intocado). Marca adicionada na lista de Controladoras + campos Device ID/SN e Modo de decisão (servidor/local/local+remoto).
- [x] **HTTP (protocolo V2.0.3)**: POST /action/<Operator>, Basic auth, Content-Length, {operator,code,info{Result,Detail}}. Comandos: GetSysParam (connect/test, salva DeviceID), SetSysTime, EditPersonNew (IdType=2/PersonUUID, picinfo/picURI, PersonType lista branca/negra, PIN, strategyInfo), EditPersonsNew (lote até 1000 via picURI + endpoint público de face com token JWT curto `/api/public/faces/<token>.jpg`), DeletePerson/DeleteAllPerson, searchPersonNum, OpenDoor, SetKeepOpen (Emergência), RebootDevice, Get/SetDoorCondition (OpendoorWay), Get/SetFaceParam, searchControl, Subscribe.
- [x] **Faixas horárias → AccessStrategy** (`time_range_to_strategy`, pura/testada): strategyID estável (crc32), dias sem acesso omitidos, feriados→holidayInfo (período vazio se faixa não vale em feriado), PersonsBindStrategyID como **substituição total** (união das faixas das categorias que contêm a área de destino). Endpoint `/api/beward/controllers/{cid}/sync-strategies`.
- [x] **Credenciais**: facial (prepare_photo valida/redimensiona ≤1MB via Pillow opcional), cartão RFID (dec/hex), Wiegand (MjCardFrom=2, WiegandType), PIN.
- [x] **Recebimento de eventos (Subscribe)**: endpoints por site `/api/beward/<site>/{verify,heartbeat,snap,card,qrcode,alarm,password}`; heartbeat marca online; **dedup** por DeviceID+CreateTime+PersonID (coleção TTL); mapeamento VerifyStatus/VerfyType/Direction e códigos de alarme.
- [x] **Decisão online** (OpendoorWay=3): no VerifyPush o backend acha a pessoa por PersonUUID + ponto de acesso da controladora, roda o **motor de decisão existente** e responde no mesmo request com `openDoor` + `showInfo` (≤64B); retroativos (Sendintime=0) e VerfyType=27 só respondem `{code:200}` sem reabrir; publica no WebSocket (foto capturada x cadastrada). Modos local/local+remoto e nota de contingência (watchdog troca OpendoorWay).
- [x] **MQTT** (`beward_mqtt`, paho-mqtt): tópicos mqtt/face/<ID>, messageId/Ack, EditPerson/DeletePersons/AddAccessStrategy/Unlock/SetKeepOpen/Reboot; **Mosquitto** adicionado ao docker-compose (61613/61614) + MQTT_BROKER/PORT no backend.
- [x] Testes: `tests/test_beward.py` (8) — conversão faixa→strategy, status/type, dedup, retroativo; +12 do motor. Verificado via curl: heartbeat, VerifyPush online (openDoor conforme motor), retroativo suprime reabertura, token de face decodifica.
- Pendente: telas "Configuração do equipamento" e "Comparar (sistema × equipamento)" completas; job agendado de expiração que remove pessoa/visitante do equipamento ao vencer; implementação completa do loop de Ack/retry MQTT e QueryProgress.

## Refactor Pessoas Fixas + Visitantes + Portaria (2026-10-11)
- [x] Tela fixa 3 colunas (`pages/Registry.jsx`, modos people/visitors/portaria; abas no celular): Empresas (busca, chips, cards c/ stats+alertas, grupos recolhíveis, fixos "Funcionários próprios"/"Visitantes do dia", "+ Empresa" rápido) | Pessoas da empresa (filtros, scroll infinito 50, seleção + lote: categoria/bloquear/desbloquear/renovar/sincronizar/exportar) | Formulário fixo (FUNCIONÁRIO/TERCEIRO/VISITANTE, seções Credenciais/Veículos/Documentos/Histórico, Salvar/Salvar e novo/Salvar e check-in, Ctrl+S, aviso de alterações não salvas, status de sync por equipamento).
- [x] Busca global Ctrl+K (nome, CPF, documento, matrícula, cartão, placa, visitantes).
- [x] Backend `routers/registry.py`, `routers/visitors_reg.py`, `registry_common.py` (validação CPF, bloqueio automático por validade/documento/contrato → status `vencido`, loop a cada 10 min, sync com controladoras + log em sync_jobs), `photo_quality.py` (OpenCV Haar: 1 rosto, centralizado, nitidez, iluminação; miniatura).
- [x] Visitantes: reaproveitamento por documento, lista negra (409), credencial temporária (QR gerado/cartão/face), check-in/check-out, expiração de visitas agendadas.
- [x] CameraCapture reescrito (getUserMedia no clique, isSecureContext, seletor de câmera lembrado, guia oval, recorte 3x4 JPEG ≤200KB/1080p, erros amigáveis, stop tracks, logs [Camera]); header `Permissions-Policy: camera=(self)` no backend e dev server.
- [x] Seed v4: NX Corp (30), 3 terceirizadas (5 cada, 1 ASO vencido), 2 transportadoras (3 motoristas c/ placa), 10 visitantes de 4 empresas (3 presentes, 1 em lista negra).
- Verificado: iteration_3 — backend 34/34, frontend 100%.
- Pendente: QR por e-mail (Resend); visitantes ainda não passam pelo motor de decisão nas leitoras (só sincronizados como pessoa temporária).

## Telas separadas de Cadastro (2026-10-11)
- [x] Menu "Cadastro": Cadastro de visitantes (/cadastro/visitantes), Cadastro de fixos (/cadastro/fixos), Visitantes (/visitantes, consulta por origem + presentes), Fixos (/pessoas, empresas + grade de pessoas + lote). Clique na consulta abre o cadastro em edição (?person= / ?visitor=). /portaria redireciona para Cadastro de visitantes.
- [x] Cadastro de visitantes: formulário + à direita monitoramento ao vivo (fixos e visitantes, filtros) e visitantes presentes com check-out. Simulador gera eventos de visitantes presentes; eventos trazem person_type/company_name.
- [x] Busca por autocomplete nos próprios campos (nome, documento, CPF, RG) — visitantes sugere só visitantes, fixos só pessoas fixas; campo grande de busca removido.
- Verificado: iteration_4 e iteration_5 (100%).

## Equipamentos — pontos dentro da controladora (2026-10-11)
- [x] Cadastro da controladora com abas "Dados gerais" e "Pontos de acesso (N)"; cada ponto = 1 leitora + 1 relé (numerados automaticamente). Campos Leitoras/Relés removidos → "Quantidade de pontos de acesso".
- [x] Modelo da controladora: Simulado (até 8), Facial Beward (1, HTTP/MQTT), Facial Hikvision (1), Facial Control iD (1), CT300-2L (até 2). Hikvision/Control iD/CT300-2L usam driver pendente (`drivers/pending.py`) que retorna "Driver X ainda não implementado".
- [x] Menu "Pontos de acesso" removido (/pontos-acesso → /controladoras). Excluir controladora exclui seus pontos (crud on_delete).
- Verificado: iteration_6 (100%).
- Pendente: drivers reais Hikvision (ISAPI), Control iD e CT300-2L (fabricante/protocolo da CT300-2L a confirmar).

## Driver Beward — MQTT real + agente local HTTP (2026-10-11)
- [x] `mqtt_bus.py`: cliente de saída ao broker (Configurações › Integrações › MQTT; padrão 156.67.82.199:1883 anônimo; senha criptografada), client_id nx-access-server, QoS1, reconexão, assina mqtt/face/#, comandos com messageId + espera de Ack (10 s), fila quando offline (reenvio ao voltar online), log das últimas mensagens.
- [x] `beward_ingest.py`: HeartBeat/Online/Offline (mqtt/face/heartbeat, mqtt/face/basic), RecPush com foto → Monitoramento + PushAck (também StrSnapPush), validação de sentido (alarme "sentido_divergente"), decisão no servidor (VerifyStatus 22 → Unlock), aviso "sem eventos" configurável por dispositivo (padrão 120 min) só no horário de funcionamento do site, prioridade baixa, sem repetir.
- [x] Agente local `/app/agent/nx_access_agent.py` (stdlib, porta 5011, /Subscribe/*, fila SQLite, Subscribe com Card/Alarm, comandos POST /action/<Operator> Basic Auth via long-poll HTTPS). Tokens por site com hash, exibidos uma vez, gerar novo/revogar, último uso/IP.
- [x] UI: página Integrações (MQTT + status + log), painel "Como configurar o facial", token do agente, horário do site, saúde do facial no card.
- Teste de conectividade: broker 156.67.82.199:1883 OK (anônimo); facial 1457460 ainda não publicou nenhuma mensagem.
- Verificado: iteration_7 (backend 24/24, frontend 100%).

- Correção (2026-10-11): fotos não chegavam ao facial ("get pic and connect URI IP error") — fotos em URL agora são baixadas no servidor e enviadas em base64 no EditPerson (máx. 200 KB); pessoa sem foto retorna erro claro. Verificado iteration_8 (Ack result ok, personId 296).

## Next Tasks
1. Implement real Control iD driver + device connection test against real API.
2. Build nx-access-agent service skeleton with SQLite queue.
3. Credenciais + Visitantes modules (Resend email QR).
