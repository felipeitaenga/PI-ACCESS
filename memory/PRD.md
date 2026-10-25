# PI-ACCESS (antigo NX-ACCESS) — PRD

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
- [x] `mqtt_bus.py`: cliente de saída ao broker (Configurações › Integrações › MQTT; padrão 156.67.82.199:1883 anônimo; senha criptografada), client_id pi-access-server, QoS1, reconexão, assina mqtt/face/#, comandos com messageId + espera de Ack (10 s), fila quando offline (reenvio ao voltar online), log das últimas mensagens.
- [x] `beward_ingest.py`: HeartBeat/Online/Offline (mqtt/face/heartbeat, mqtt/face/basic), RecPush com foto → Monitoramento + PushAck (também StrSnapPush), validação de sentido (alarme "sentido_divergente"), decisão no servidor (VerifyStatus 22 → Unlock), aviso "sem eventos" configurável por dispositivo (padrão 120 min) só no horário de funcionamento do site, prioridade baixa, sem repetir.
- [x] Agente local `/app/agent/pi_access_agent.py` (stdlib, porta 5011, /Subscribe/*, fila SQLite, Subscribe com Card/Alarm, comandos POST /action/<Operator> Basic Auth via long-poll HTTPS). Tokens por site com hash, exibidos uma vez, gerar novo/revogar, último uso/IP.
- [x] UI: página Integrações (MQTT + status + log), painel "Como configurar o facial", token do agente, horário do site, saúde do facial no card.
- Teste de conectividade: broker 156.67.82.199:1883 OK (anônimo); facial 1457460 ainda não publicou nenhuma mensagem.
- Verificado: iteration_7 (backend 24/24, frontend 100%).

- Correção (2026-10-11): fotos não chegavam ao facial ("get pic and connect URI IP error") — fotos em URL agora são baixadas no servidor e enviadas em base64 no EditPerson (máx. 200 KB); pessoa sem foto retorna erro claro. Verificado iteration_8 (Ack result ok, personId 296).

## Renomeação para PI-ACCESS (2026-10-11)
- [x] Nome trocado em toda a interface (login, menu, título da aba), API, remetente de e-mail, README, agente local (`pi_access_agent.py`) e client_id MQTT (`pi-access-server`, também atualizado no banco). Logins/senhas mantidos (NxAccess@2026, @nxaccess.com). Chave do token no navegador virou `pi_access_token` (usuários precisam entrar de novo uma vez).

## Prefixo de tópico MQTT configurável (2026-10-11)
- [x] Campo "Prefixo do tópico" em Configurações › Integrações › MQTT (padrão mqtt/face; barras e #/+ removidos). Assinatura <prefixo>/#, comandos <prefixo>/<ID facial>, heartbeat <prefixo>/heartbeat e <prefixo>/basic. Testado com tjs/mqtt/face (assinatura OK) e voltado para mqtt/face.

## Empacotamento para produção multi-cliente (2026-10-11)
- [x] Dockerfile multi-stage (node build → python:3.11-slim), uvicorn único :8000 (/api, /api/ws, SPA fallback), não-root uid 10001, HEALTHCHECK /api/health (mongo+mqtt), proxy headers.
- [x] Config 100% env (backend/app_config.py): CLIENTE, CLIENTE_NOME, PUBLIC_URL, ENCRYPTION_KEY, SEED_DEMO, DATA_DIR, MQTT_*, SMTP_*. Admin inicial só se não houver usuários.
- [x] MQTT env-managed: base <MQTT_PREFIX>/face, assina base/# + mqtt/face/heartbeat|basic (filtrados por facial cadastrado), client_id piaccess-<CLIENTE>, TLS opcional; Integrações somente leitura (PUT 409); painel "Como configurar o facial" com broker/porta/usuário/senha/tópico.
- [x] migrations.py (schema_migrations), reset_admin.py (python -m app.reset_admin), /api/version + versão no rodapé/login, SMTP próprio (sem SMTP: link "Esqueceu a senha?" oculto), redefinir senha em Administração › Usuários.
- [x] deploy/docker-compose.yml, deploy/.env.example (+ cópia na raiz), deploy/README.md, .github/workflows/docker-publish.yml (ghcr.io/felipeitaenga/pi-access).
- [x] Testado em simulação de produção sem Docker (/root/prodtest: Caddy + Mosquitto com senha) — iteration_9 100%. Corrigido KeyError de áreas sem description em equipment.py.

## v1.1.0 — Cadastro de visita + Configurações › Visitantes (2026-10-11)
- [x] Sincronizado com GitHub felipeitaenga/PI-ACCESS main (v1.0.3: Dockerfile yarn.lock opcional, VERSION + workflow por VERSION, bootstrap.py, deploy/pi-cliente.sh, ACK_TIMEOUT_BY_OP, Online-Ack, get_device_info por heartbeat). frontend/yarn.lock e .env.example liberados no .gitignore.
- [x] Nova tela /cadastro/visitantes (components/visits/*): tipo, início, fim automático (duração do tipo, manual trava), +1h/+4h/fim do dia, empresa visitada + anfitrião ativo, documento com máscara/validação por config, lookup por tipo+número, lista negra (admin libera com justificativa), identificador facial/cartão(hex→dec)/QR(PIV-…), foto, placa Mercosul/antiga, observações, status de sincronização, Encerrar visita, "presentes agora" com tempo restante.
- [x] Backend: visits_core.py + routers/visits.py (/api/visits, /types, /settings, /lookup, /present, /{id}/end), job 60 s (agendado→presente, expira e DeletePersons, visit_history), migração 0003 (Visita padrão + settings), EditPerson MQTT com tempCardType=1/cardValidBegin/cardValidEnd/RFIDCard, motor reconhece visitante pelo customId.
- [x] Configurações › Visitantes: CRUD tipos de visita + validação CPF/RG + duração geral. Testes tests/test_visits.py (5) + iteration_10 100%.
- VERSION = 1.1.0

## Cadastro de fixos — documento, categorias, anfitrião (2026-10-11)
- [x] Tipo de documento (CPF/RG/Passaporte/Outro, padrão CPF, obrigatório) + número com validação das Configurações › Visitantes; duplicidade por tipo+número (doc_type/doc_number/doc_key).
- [x] Seletor de categorias com busca + lista suspensa + etiquetas removíveis (também em Tipos de visita).
- [x] Campo "Pode autorizar visitas" (can_authorize_visits); anfitrião do Cadastro de visitante só lista quem pode autorizar (front e back). Migração 0004: existentes = sim, doc_type=cpf.
- [x] Matrícula opcional. tests/test_registry.py atualizado ao novo contrato. iteration_11 100%.

## Autocompletar visitante (2026-10-11)
- [x] Nome e Número do documento no Cadastro de visitante sugerem visitantes (≥3 caracteres, ↑/↓, Enter/clique). Ao escolher preenche visitante + última visita (tipo, empresa visitada, anfitrião ativo autorizado, identificador, observações); início = agora, fim recalculado. Endpoints /api/visits/visitor-search e /api/visits/visitor/{id}/prefill. iteration_12 100%.

## Identidade Pilares — preto e laranja (2026-10-11)
- [x] Paleta: Tailwind `sky` remapeado para laranja do logo (#ef7d25) e `slate` para neutro/preto; variáveis CSS dos temas escuro (preto) e claro (branco) com laranja.
- [x] Logo Pilares (frontend/public/brand/pilares-logo.webp, enviado pelo usuário) no menu e no login; imagem do login trocada por catracas/leitor facial gerada (public/brand/login-access.jpg).
- [x] Campos destacados: fundo `bg-field`, borda visível, foco/hover laranja, rótulos mais fortes (Input, Select, Textarea, seletor de categorias). iteration_13 100%.

- [x] Favicon/ícones com o símbolo Pilares (public/favicon.ico, favicon-32.png, icon-192/512.png, apple-touch-icon.png); index.html pt-BR. Rótulo "Código" da categoria → "Nome da categoria".

## v1.2.0 — Perfil Gestor de empresa (2026-10-12)
- [x] role company_manager + users.company_ids (obrigatório p/ gestor). backend/scope.py: scope_filter/find_scoped (404 fora do escopo), MANAGER_ALLOW + middleware company_manager_gate (403 no resto da API, auditoria "gestor:<MÉTODO>"), ws_visible (WebSocket filtrado no servidor), stamp_event (company_id nos eventos: empresa da pessoa ou empresa visitada da visita ativa).
- [x] Escopo aplicado em registry (empresas, pessoas, busca, bulk, categorias liberadas, limite de ativos), visitors_reg, visits (tipos liberados, empresa visitada, busca LGPD), dashboard, events, reports, crud categories/all.
- [x] Empresa › "Acesso ao sistema": categorias/tipos de visita liberados, limite de pessoas ativas, gestores vinculados. Usuários: perfil + empresas; Configurações: "Gestor pode criar gestores da mesma empresa". Menu/rotas do frontend restritos (MANAGER_PATHS + ManagerGuard), KPIs de equipamentos ocultos.
- [x] Migração 0005 (company_ids=[], company_id nos eventos antigos quando possível). Testes tests/test_company_scope.py (A/B). iteration_14: backend 100%, ajustes de frontend aplicados. VERSION 1.2.0 (GitHub tinha 1.1.2).

## v1.4.3 — Revisão do autocadastro/agendamentos vindos do GitHub (2026-10-12)
- [x] Main do GitHub (v1.4.3) trazida para o ambiente (clone público + rsync; .env preservados; VERSION intacto).
- [x] Correções: sync_to_devices conta falha de sync_face como erro; ator do link do anfitrião/convite com role "anfitriao"/"convite" (nunca admin); convite e verificação de e-mail consumidos de forma atômica antes de criar a solicitação; código de empresa não colide com site_code.
- [x] iteration_16: testes A–K OK (19/19 backend, telas 390px OK). Teste: backend/tests/test_selfreg_flow.py.
- [ ] Facial Beward 1457460 (pilares): o sistema nunca envia SetSysTime nem SetDoorCondition (código sem chamada); StrSnapPush (rosto desconhecido) não vira access_event. O facial não publicava no broker durante a verificação.

## v1.4.6 + visitante "Desconhecido" no facial (2026-10-12)
- [x] Main 1.4.6 trazida (sync_time, StrSnapPush como evento, sincronização completa com visitantes).
- [x] visits_core.release_visitor: o fim/check-out/cancelamento de uma visita não apaga do facial se o visitante tiver outra visita ativa; reenvia com a validade da visita ativa (o facial usa o ID do visitante, não o da visita).
- [x] POST /api/visits/{id}/device-check + botão "Verificar no facial" (PresentNow): SearchPerson, GetPictureSearch e GetPictureSimilarity (captura "Desconhecido" × foto cadastrada). Consultas não entram na fila MQTT (bus.command queue=False).
- [x] iteration_17: backend 6/6 + regressão OK, frontend OK.

- [x] Monitoramento ao vivo: o feed mostra a foto capturada (captured_photo) e o motivo da negação, como o feed do cadastro (2026-10-13).

- [x] Clicar num evento (Acessos em tempo real / Monitoramento) abre a edição do fixo ou do visitante; Inspeção facial tem "Editar cadastro"; ?visitor= preenche o formulário de visita (2026-10-13, iteration_18 OK).

- [x] Evento "Desconhecido": botões "Cadastrar visitante" / "Cadastrar fixo" (Acessos em tempo real e Inspeção facial) abrem o cadastro novo com a foto capturada (sessionStorage + ?capture=) (2026-10-13, iteration_19 OK).

- [x] Câmera 3:4 com oval maior; fila do autocadastro com Liberar/Recusar/Editar (PUT /api/selfreg/requests/{id}); identificadores só Cartão; bootstrap automático em sistema novo (faixas, feriados, áreas, categorias, 14 departamentos); relatórios /api/reports/data/{access|visits|present|people|denied} com filtros e PDF/Excel (openpyxl, reportlab) (2026-10-14, iteration_20 OK).

- [x] Check-out imediato (end_visit atômico, facial em segundo plano); Visitantes agrupados por empresa visitada; "Própria" → "Fixos"/"Funcionários fixos"; identificador tipo Placa; filtro "Mostrar" (negados/desconhecidos) no relatório (2026-10-14, iteration_21 OK).

- [x] Exclusão definitiva LGPD (POST /api/lgpd/erase, admin + justificativa; apaga cadastro/foto/face/cartões/placas, remove do facial, anonimiza eventos/visitas/auditoria, apaga comandos MQTT com foto; registro em lgpd_erasures). Botão no cadastro de fixo e de visitante (2026-10-14, iteration_22 OK).

- [x] Regra fixa: filtros por empresa validados com scope.own_company_or_404 (registry/people company_id, registry/visitors host_company, reports company_id); merge de origin/main 1.5.1 feito (2026-10-14). Ver /app/memory/RULES.md.

- [x] Autocadastro: só selfie pela câmera; sem agendar (solicitação imediata, visita começa na aprovação mantendo a duração); convite gera mensagem com detalhes (copiar/WhatsApp, campo Observações); tela de espera com spinner (polling 5 s, vibração/som) + Web Push (VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY/VAPID_SUBJECT no .env, sw.js, manifest.json) avisando aprovada/recusada (2026-10-18, iteration_23 + testes test_selfreg_now_invite_msg.py, test_selfreg_push.py).

- [x] CPF primeiro e só CPF (público e portaria) com "CPF inválido"; busca por CPF (pública: só "Encontramos seu cadastro, Mar***", dados usados sem exibir; status mascara o nome); empresas do QR único só ao tocar/digitar; campo opcional "Motivo da visita" (visit_reason) na portaria, anfitrião, fila, presentes e relatório Visitas (2026-10-18, iteration_24 + tests/test_selfreg_cpf_reason.py). Merge da main 1.5.3 (validação SSRF do endpoint de push).
- [x] Merge da main 1.5.5: busca pública por CPF REMOVIDA por decisão do cliente (visitante sempre digita CPF e nome; não recriar). Mantidos doc_known/owner_verified (comparação de fotos na portaria) e busca por CPF da portaria. tests/test_selfreg_cpf_reason.py atualizado (rota inexistente, nome obrigatório, CPF conhecido sinaliza conferência).
- [x] 2026-10-24: removida a liberação automática do convite (backend ignora auto_approve, inclusive em convites antigos; tela sem a chave). Toda solicitação vai para aprovação do anfitrião/portaria. Criação de convite verificada na preview (Admin). tests/test_selfreg_flow.py ajustado.
- [x] 2026-10-25: Convite — gestor de empresa sem "Tipos de visita que a empresa pode usar" configurados não conseguia criar convite (lista de tipos vazia). Tela agora mostra aviso explicando e desativa "Criar convite". Regra de permissão mantida. Operador/Recepção/Admin criam normalmente (verificado).
- [x] 2026-10-25: Redesenho mobile-first do Autocadastro. Dialogs globais (ui/dialog.jsx): tela cheia < 640 px com cabeçalho/rodapé fixos e safe-area; desktop sem rodapé cobrindo conteúdo. Público /v e /convite em 4 passos (Visita → Seus dados → Selfie → Revisar), LGPD resumida/expansível, cartões grandes de empresa/anfitrião, máscaras, dicas da selfie (luz, sem boné, sem óculos), revisão com editar, erros junto ao campo. /solicitacao com cartão de status animado, horário, instrução do leitor e motivo da recusa (backend devolve `reason` só quando recusado). /aprovar com foto grande, avisos acima da foto e Aprovar/Recusar fixos. Interno: botão flutuante "Convidar", convite em 3 passos com resultado (WhatsApp, copiar, QR), fila em cartões no celular / tabela no desktop, Liberar rápido abre o detalhe para lista negra e CPF já cadastrado, "Baixar cartaz" (PDF A4 jsPDF) e "Compartilhar". iteration_25/26.
- [x] 2026-10-25: Fila do facial (MQTT): ao voltar online o reenvio agora é um comando por vez, esperando o Ack (antes mandava tudo a cada 0,3 s e travava o facial → "sem Ack em 40 s"). Sem Ack: para e tenta de novo no próximo ciclo do monitor. Também reenvia quando o broker reconecta e sempre que o facial está online com fila parada. O histórico "Últimas sincronizações" é atualizado com o resultado (message_id nas linhas novas; linhas antigas casadas por pessoa+facial+horário). Teste: tests/test_mqtt_queue_flush.py. Escolha do cliente: só reenviar a fila antiga (sem sincronização completa automática) e sem aviso extra na tela.
- [x] 2026-10-25: Relógio do facial errado — SetSysTime não entra mais na fila (queue=False); comandos SetSysTime antigos na fila são descartados no reenvio; após esvaziar a fila a hora é acertada de novo; falha no acerto não espera mais 24 h (time_synced_at só no sucesso, nova tentativa a cada 10 min via time_sync_tried_at). "Verificar no facial" mostra a falha e o motivo. Testes em tests/test_mqtt_queue_flush.py (6).

## Next Tasks
0. Sincronizar hora (SetSysTime) e OpendoorWay ao receber "Online" do facial; registrar StrSnapPush como evento "Desconhecido".
1. Implement real Control iD driver + device connection test against real API.
2. Finalizar e documentar pi-access-agent (agente local).
3. Credenciais + Visitantes modules (Resend email QR).
