# Regras fixas do cliente (PI-ACCESS)

- Filtro novo por empresa (company_id, host_company etc.): se o usuário for gestor de empresa, validar contra cids(user) com `scope.own_company_or_404(user, cid)` → 404 se a empresa não for dele. Nunca deixar o filtro sobrescrever o scope_filter (usar `$and`).
- Antes de salvar no GitHub: `git fetch origin main` + `git merge origin/main` (remote origin = https://github.com/felipeitaenga/PI-ACCESS.git). Sem reset, sem force push. Não alterar VERSION.
