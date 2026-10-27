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
