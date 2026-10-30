# Regras fixas do cliente (SCARVEL — antigo PI-ACCESS)

- Produto renomeado para SCARVEL na v2.0.0: nome, logo (/brand/scarvel-*.png), cor azul (primary 214 100% 55%), imagem ghcr.io/felipeitaenga/scarvel, containers scarvel_<cliente>, pasta /opt/scarvel, comando `scarvel`, banco/usuário scarvel, prefixo MQTT scarvel/<cliente>. NÃO usar "PI-ACCESS", "piaccess" nem marca/logo da Pilares no produto (Pilares é só um cliente).

- Filtro por empresa (company_id, host_company etc.): quando o usuário for gestor de empresa, usar `scope.own_company_or_404(user, company_id)` → 404 se a empresa não for dele. Nunca deixar o filtro sobrescrever o scope_filter (usar `$and`).
- Nada vai ao facial sem aprovação humana (anfitrião ou portaria). Convite NÃO tem liberação automática (removida a pedido do cliente): toda solicitação vai para aprovação. Lista negra só o Administrador libera, com justificativa.
- Rotas públicas aceitam apenas texto nos campos (helper `_s`), sem objetos/operadores Mongo.
- Toda mudança de backend precisa de teste automatizado em `backend/tests`.
- Antes de salvar no GitHub: `git fetch origin main` + `git merge origin/main` (origin = https://github.com/felipeitaenga/PI-ACCESS.git). Sem reset, nunca force push na main. Salvar em branch conflict_* é aceitável.
- Não alterar o arquivo VERSION (publicação é feita depois da revisão).
- Autocadastro público NÃO tem busca por CPF (rota /public/selfreg/lookup e preenchimento automático removidos na 1.5.5 por decisão do cliente). Visitante sempre digita CPF e nome. Não recriar. Mantêm-se doc_known/owner_verified (alerta + comparação de fotos na portaria). Busca por CPF na portaria (logado, /visits/lookup) continua.

## Facial Beward MQTT — formatos TESTADOS no aparelho real (1457460, 25/10/2026). Não alterar.
- SetSysTime: `info.SysTime = "AAAA-MM-DDTHH:MM:SS"` (com T). Com espaço o facial responde ok e NÃO aplica; campos separados → "Can't find SysTime".
- DeletePersons: `info = {DataBegin:"BeginFlag", PersonNum:N, customId:[...], DataEnd:"EndFlag"}`. Sem DataBegin → "can not find DataBegin" (não apaga). Resposta traz DelErrNum/DelSucNum (sem "result").
- EditPerson SUBSTITUI o cadastro inteiro (sem foto apaga nome/foto). Nunca mandar EditPerson parcial.
- Respostas do facial às vezes vêm com JSON inválido (vírgula faltando/sobrando) → usar `parse_json_lenient`.
- Modo de Liberação "Verificação local Aberta à distância": RecPush chega com VerifyStatus "0"; o servidor decide e responde `Unlock {openDoor:"1"|"0"}`. Liberado = áudio "autorizado"; o texto showInfo não aparece na tela; negado = silêncio.
- Modo "Face": o facial decide sozinho (VerifyStatus 1) → regras do servidor (anti-dupla, reentrada) NÃO valem.
- GetDoorCondition/SetDoorCondition não respondem por MQTT neste firmware: o modo é trocado no painel web do facial.
- Unlock, SetKeepOpen, RebootDevice, Versions e SetSysTime nunca vão para a fila (NO_REPLAY).
- CPF e telefone não vão para o facial (idCard/telnum vazios) — LGPD.
- Categoria: toda área liberada precisa de faixa horária; sem faixa o motor nega ("Fora da faixa horária").
- Controladoras: fabricante/modelo vêm do catálogo `backend/device_catalog.py` (status homologado / em_teste / em_breve; em_breve não pode ser salvo). Novo modelo de marca com driver existente = uma linha em MODELS. Não voltar para a lista fixa de modelos na tela.

## Facial Intelbras Bio-T (SS 3532 MF W, firmware 20250403) — driver em teste (2.2.0)
- API CGI HTTP com Digest (`backend/drivers/intelbras.py`). UserID no facial = número curto do mapa `device_uids` (uuid ↔ número). Não mandar o uuid como UserID.
- LGPD: não enviar CitizenIDNo (CPF) nem telefone ao facial.
- Modo Online: o facial faz POST `/api/intelbras/<token>/notification` (multipart: JSON `Events[]` + JPEG) e GET `/api/intelbras/<token>/keepalive`. Resposta: `{"message","code":"200","auth":"true|false"}` (`intelbras_ingest.py`). O token é secreto (campo `intelbras_token`, nunca sai na API).
- Sem keepalive o facial fica Offline e LIBERA TODOS os cadastrados 24h → o SCARVEL gera alarme `facial_offline`. Por isso visitante tem que sair do facial no fim da visita.
- Eventos guardados no offline chegam depois: registrar como retroativos, sem decidir de novo.
- Relógio: o SS 3532 MF W volta para 01/01/2000 sem energia → visitante não passa (validade). O SCARVEL acerta a hora ao voltar online, a cada 6 h, no Testar e no Sincronizar.

## Rede / VPN (2.3.0) — um MikroTik por cliente, padrão igual em todo cliente
- Padrão: MikroTik porta 1 = internet do cliente; portas 2-5 = rede do controle de acesso 192.168.88.0/24 (gateway .1). Faciais com IP fixo 192.168.88.101 a .199.
- Cada cliente tem um nº N (2..254) na VPN: MikroTik 10.66.0.N; o servidor enxerga os faciais como 10.67.N.x (netmap no MikroTik); o app é publicado só em 10.66.0.1:<porta do cliente>.
- O app não mexe na VPN do servidor: grava DATA_DIR/vpn/request.json (chave pública do MikroTik) e lê DATA_DIR/vpn/status.json. Quem aplica é o `scarvel-vpn-sync.py` (root, systemd timer 15 s), com registro em /etc/scarvel-vpn/clients.json.
- Isolamento: o MikroTik N só abre conexão na porta do próprio cliente (chain SCARVEL-VPN em DOCKER-USER).
- Nome do cliente nunca leva o nº (URL/containers/MQTT). O nº aparece em `scarvel listar`, na tela Rede / VPN e no nome do MikroTik (SCARVEL-<cliente>-<N>).

## Confirmação de passagem (2.4.0)
- Ponto de acesso com passage_mode="confirmacao": acesso liberado fica PENDENTE (coleção passages) e só conta (área atual, ocupação, anti-dupla) quando o sensor confirmar o giro (`passage.py`).
- Sem giro em passage_timeout s → evento "nao_passou" (não conta; reentrada temporizada ignora). Giro sem pendente → alarme passagem_nao_autorizada. Debounce 2 s (abre/fecha do mesmo giro).
- Intelbras: sinal = evento DoorStatus Status=Open no Modo Online. Sincronizar envia relé/porta aberta/sensor ao facial (configure_door). SensorType 0=NA/1=NF ainda NÃO confirmado no aparelho.
- Beward: ainda não ligado (alarme code 6 = sensor de porta) — fazer depois do teste.
