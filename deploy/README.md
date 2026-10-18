# PI-ACCESS — Implantação em produção (Docker, multi-cliente isolado)

Cada cliente tem **seu próprio container da aplicação e seu próprio MongoDB**, numa pasta própria no servidor.
A imagem é única para todos: `ghcr.io/felipeitaenga/pi-access:<versão>`.

```
/opt/piaccess/clientes/
├── pilares/
│   ├── docker-compose.yml   (cópia de deploy/docker-compose.yml)
│   ├── .env                 (cópia editada de deploy/.env.example)
│   └── dados/
│       ├── app/             → /app/data (fotos, uploads, exportações)
│       └── mongo/           → /data/db
└── outrocliente/ ...
```

## 1. Arquitetura da imagem

- Um processo (uvicorn) na porta **8000**: `/api/*` → API, `/api/ws` → WebSocket, `/*` → frontend React (SPA, `index.html` como fallback).
- O frontend chama a API por caminho relativo (`/api`), então o mesmo build serve qualquer domínio.
- Roda como usuário não-root (`uid 10001`), logs no stdout (`docker logs`).
- Healthcheck: `GET /api/health` → `{"status":"ok","mongo":"ok","mqtt":"conectado",...}` (HTTP 503 se o Mongo cair).
- Versão: `GET /api/version` → `{"version":"1.0.0","cliente":"pilares",...}`; também aparece no rodapé do menu e na tela de login.
- Atrás de proxy: uvicorn com `--proxy-headers --forwarded-allow-ips=*` (IP real do cliente e HTTPS respeitados). Cookies são `Secure`.
- No startup: cria índices do Mongo e executa as migrações versionadas (`schema_migrations`), tudo idempotente.

## 2. Build da imagem

### Automático (GitHub Actions)
Ao criar uma tag `vX.Y.Z`, o workflow `.github/workflows/docker-publish.yml` gera e publica
`ghcr.io/felipeitaenga/pi-access:X.Y.Z` e `:latest`.

```bash
git tag v1.0.0
git push origin v1.0.0
```
> Na primeira publicação, em GitHub › Packages › pi-access › Package settings, deixe o pacote **público**
> ou faça `docker login ghcr.io -u felipeitaenga` no servidor com um token (scope `read:packages`).

### Manual (no servidor ou na sua máquina)
```bash
docker build --build-arg VERSION=1.0.0 -t ghcr.io/felipeitaenga/pi-access:1.0.0 .
docker push ghcr.io/felipeitaenga/pi-access:1.0.0     # opcional
```

## 3. Pré-requisitos no servidor (uma vez)

```bash
docker network create proxy        # rede compartilhada com o Caddy (se ainda não existir)
```
Caddyfile (Caddy também na rede `proxy`) — WebSocket e cabeçalhos X-Forwarded já são automáticos:
```
pilares.piaccess.pilaresautomacao.com.br {
    reverse_proxy piaccess_pilares:8000
}
```
Depois de editar: `docker exec caddy caddy reload --config /etc/caddy/Caddyfile`.

## 4. Variáveis de ambiente (`.env`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `CLIENTE` | sim | slug do cliente (`pilares`). Nome do container `piaccess_<CLIENTE>`, client_id MQTT `piaccess-<CLIENTE>` |
| `CLIENTE_NOME` | não | nome exibido (padrão = CLIENTE) |
| `VERSAO` | sim | tag da imagem |
| `PUBLIC_URL` | sim | `https://pilares.piaccess.pilaresautomacao.com.br` (links e e-mails) |
| `DB_NAME` | sim | nome do banco |
| `MONGO_USER` / `MONGO_PASSWORD` | sim | usuário root do Mongo do cliente (o compose monta o `MONGO_URL`) |
| `JWT_SECRET` | sim | segredo dos tokens de login |
| `ENCRYPTION_KEY` | sim | criptografia de senhas de dispositivos/biometria — **não trocar depois** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | 1º start | admin inicial, criado só se não houver nenhum usuário |
| `MQTT_HOST` / `MQTT_PORT` | sim | broker MQTT |
| `MQTT_USER` / `MQTT_PASSWORD` | não | credenciais do broker (vazio = anônimo) |
| `MQTT_TLS` | não | `true`/`false` |
| `MQTT_PREFIX` | não | padrão `piaccess/<CLIENTE>` |
| `TZ` | não | `America/Sao_Paulo` |
| `SEED_DEMO` | não | `false` em produção (banco inicia vazio) |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` | não | e-mails (recuperação de senha e autocadastro: código de confirmação, aprovação do anfitrião, avisos ao visitante). Porta 465 = SSL; outras = STARTTLS |
| `TURNSTILE_SITE_KEY` `TURNSTILE_SECRET` | não | captcha Cloudflare Turnstile nas páginas públicas do autocadastro |
| `VAPID_PUBLIC_KEY` `VAPID_PRIVATE_KEY` | não | aviso no celular do visitante (Web Push). Gere com `pi-cliente vapid <cliente>` |
| `CORS_ORIGINS` | não | origens extras, separadas por vírgula |

Variáveis definidas pela imagem (não precisa mexer): `APP_VERSION`, `STATIC_DIR=/app/static`, `DATA_DIR=/app/data`.

## 5. MQTT por cliente

- Tópico base dos faciais: **`<MQTT_PREFIX>/face`** (ex.: `piaccess/pilares/face`).
  Comandos para o facial: `<MQTT_PREFIX>/face/<DeviceID>`; eventos: `<MQTT_PREFIX>/face/<DeviceID>/Rec`, Ack etc.
- O servidor assina somente `<MQTT_PREFIX>/face/#`, `mqtt/face/heartbeat` e `mqtt/face/basic`.
- Nos tópicos fixos (heartbeat/basic), só são processadas mensagens cujo `facesluiceId` seja de um facial cadastrado **neste** cliente; o resto é ignorado (nem aparece no log).
- client_id `piaccess-<CLIENTE>`, QoS 1, reconexão automática com backoff (2 → 60 s).
- Em Configurações › Integrações a configuração MQTT aparece **somente leitura** (vem do `.env`).
- No cadastro da controladora Beward (modo MQTT), o quadro "Como configurar o facial" mostra broker, porta, usuário, senha (só para administrador), tópico base e as opções do painel:
  Evento de Identificação = **Enviar com Foto**; Retomar do ponto de interrupção = **Habilitar**.

## 6. Operação de um cliente

### Criar
```bash
mkdir -p /opt/piaccess/clientes/pilares && cd /opt/piaccess/clientes/pilares
cp /caminho/do/repo/deploy/docker-compose.yml .
cp /caminho/do/repo/deploy/.env.example .env && nano .env      # CLIENTE, segredos, MQTT, PUBLIC_URL...
mkdir -p dados/app dados/mongo && chown -R 10001:10001 dados/app
docker compose up -d
docker compose logs -f app        # aguarde "PI-ACCESS x.y.z iniciado — cliente pilares"
curl -s http://localhost:8000/api/health   # (de dentro: docker exec piaccess_pilares curl -s localhost:8000/api/health)
```
Adicione o bloco do domínio no Caddyfile e recarregue o Caddy.

### Atualizar versão
```bash
cd /opt/piaccess/clientes/pilares
sed -i 's/^VERSAO=.*/VERSAO=1.1.0/' .env
docker compose pull && docker compose up -d     # migrações rodam sozinhas no startup
```
Voltar versão: ajuste `VERSAO` para a anterior e repita (faça backup antes de atualizar).

### Pausar / retomar
```bash
docker compose stop      # pausa (dados preservados)
docker compose start
```

### Excluir cliente
```bash
docker compose down              # remove containers (dados ficam em ./dados)
# definitivo, depois de um backup:
cd .. && rm -rf pilares
```
Remova também o bloco do domínio no Caddyfile.

### Redefinir senha do administrador (emergência)
```bash
docker exec -it piaccess_pilares python -m app.reset_admin                       # ADMIN_EMAIL, gera senha aleatória
docker exec -it piaccess_pilares python -m app.reset_admin admin@empresa.com NovaSenha@2026
```
Cria o admin se o e-mail não existir, reativa a conta, libera bloqueio de tentativas e encerra as sessões abertas.
Sem SMTP, os demais usuários têm a senha redefinida em **Administração › Usuários › ícone de chave**.

## 7. Backup e restauração

Os dados do cliente são: o banco Mongo (inclui fotos das pessoas) + a pasta `dados/app`.

### Backup
```bash
cd /opt/piaccess/clientes/pilares
set -a; . ./.env; set +a
mkdir -p backups
docker exec piaccess_${CLIENTE}_mongo mongodump --archive --gzip \
  -u "$MONGO_USER" -p "$MONGO_PASSWORD" --authenticationDatabase admin --db "$DB_NAME" \
  > backups/mongo_$(date +%F_%H%M).archive.gz
tar czf backups/app_$(date +%F_%H%M).tar.gz -C dados app
```
Agende no cron (ex.: diário às 02:00) e copie a pasta `backups/` para fora do servidor.

### Restauração
```bash
cd /opt/piaccess/clientes/pilares
set -a; . ./.env; set +a
docker compose stop app
docker exec -i piaccess_${CLIENTE}_mongo mongorestore --archive --gzip --drop \
  -u "$MONGO_USER" -p "$MONGO_PASSWORD" --authenticationDatabase admin \
  < backups/mongo_AAAA-MM-DD_HHMM.archive.gz
tar xzf backups/app_AAAA-MM-DD_HHMM.tar.gz -C dados && chown -R 10001:10001 dados/app
docker compose start app
```

## 8. Recursos e limites
- app: `mem_limit 512m`; mongo: `mem_limit 400m` com `--wiredTigerCacheSizeGB 0.25`.
- Logs com rotação (json-file, 10 MB × 5).
- Nenhuma porta publicada no host; só o Caddy acessa `piaccess_<cliente>:8000` pela rede `proxy`. O Mongo fica só na rede `interna` do cliente.
