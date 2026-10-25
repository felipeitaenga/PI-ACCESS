# Regras fixas do cliente (PI-ACCESS)

- Filtro por empresa (company_id, host_company etc.): quando o usuário for gestor de empresa, usar `scope.own_company_or_404(user, company_id)` → 404 se a empresa não for dele. Nunca deixar o filtro sobrescrever o scope_filter (usar `$and`).
- Nada vai ao facial sem aprovação humana (anfitrião ou portaria). Convite NÃO tem liberação automática (removida a pedido do cliente): toda solicitação vai para aprovação. Lista negra só o Administrador libera, com justificativa.
- Rotas públicas aceitam apenas texto nos campos (helper `_s`), sem objetos/operadores Mongo.
- Toda mudança de backend precisa de teste automatizado em `backend/tests`.
- Antes de salvar no GitHub: `git fetch origin main` + `git merge origin/main` (origin = https://github.com/felipeitaenga/PI-ACCESS.git). Sem reset, nunca force push na main. Salvar em branch conflict_* é aceitável.
- Não alterar o arquivo VERSION (publicação é feita depois da revisão).
- Autocadastro público NÃO tem busca por CPF (rota /public/selfreg/lookup e preenchimento automático removidos na 1.5.5 por decisão do cliente). Visitante sempre digita CPF e nome. Não recriar. Mantêm-se doc_known/owner_verified (alerta + comparação de fotos na portaria). Busca por CPF na portaria (logado, /visits/lookup) continua.
