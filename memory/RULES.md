# Regras fixas do cliente (PI-ACCESS)

- Filtro por empresa (company_id, host_company etc.): quando o usuário for gestor de empresa, usar `scope.own_company_or_404(user, company_id)` → 404 se a empresa não for dele. Nunca deixar o filtro sobrescrever o scope_filter (usar `$and`).
- Nada vai ao facial sem aprovação humana (anfitrião, portaria ou criador do convite com liberação automática). Lista negra só o Administrador libera, com justificativa.
- Rotas públicas aceitam apenas texto nos campos (helper `_s`), sem objetos/operadores Mongo.
- Toda mudança de backend precisa de teste automatizado em `backend/tests`.
- Antes de salvar no GitHub: `git fetch origin main` + `git merge origin/main` (origin = https://github.com/felipeitaenga/PI-ACCESS.git). Sem reset, nunca force push na main. Salvar em branch conflict_* é aceitável.
- Não alterar o arquivo VERSION (publicação é feita depois da revisão).
