#!/bin/bash
# =====================================================================
#  pi-cliente.sh — gestão de clientes PI-ACCESS (1 app + 1 Mongo por cliente)
#  Servidor: Caddy (nx360_caddy, /opt/caddy) + Mosquitto (/root/mosquitto, porta 1884)
#
#  Uso:
#    pi-cliente.sh criar <cliente> [versao]      cria e sobe um cliente novo
#    pi-cliente.sh listar                        lista clientes, status e versão
#    pi-cliente.sh pausar <cliente>              para o cliente (dados preservados)
#    pi-cliente.sh ativar <cliente>              volta a rodar
#    pi-cliente.sh atualizar <cliente> <versao>  backup + troca de versão
#    pi-cliente.sh backup <cliente>              backup do Mongo + fotos
#    pi-cliente.sh backup-todos                  backup de todos (usar no cron)
#    pi-cliente.sh logs <cliente>                acompanha os logs da aplicação
#    pi-cliente.sh padrao <cliente> ["Local"]    cria áreas, faixas, feriados e categorias padrão
#    pi-cliente.sh empresas <cliente> <csv> <email-admin>  cria empresas e gestores em lote
#    pi-cliente.sh senha-admin <cliente>         redefine a senha do administrador
#    pi-cliente.sh senha-mqtt <cliente>          gera nova senha MQTT (atualizar no facial!)
#    pi-cliente.sh vapid <cliente>               gera as chaves do aviso no celular (autocadastro)
#    pi-cliente.sh excluir <cliente>             backup + remove (dados vão para excluidos/)
#
#  Variáveis opcionais no "criar":  NOME="Hospital X"  ADMIN_EMAIL="ti@hospitalx.com.br"
# =====================================================================
set -euo pipefail

BASE=/opt/piaccess
CLIENTES=$BASE/clientes
EXCLUIDOS=$BASE/excluidos
TEMPLATE=$BASE/template/docker-compose.yml
TEMPLATE_URL=https://raw.githubusercontent.com/felipeitaenga/PI-ACCESS/main/deploy/docker-compose.yml

DOMINIO=piaccess.pilaresautomacao.com.br
CADDY=nx360_caddy
CADDY_DIR=/opt/caddy/clientes

MQTT_CONT=mosquitto
MQTT_HOST=156.67.82.199
MQTT_PORTA=1884

VERSAO_PADRAO=1.0.0
ADMIN_EMAIL_PADRAO=admin@pilaresautomacao.com.br
BACKUPS_MANTER=14          # quantos backups manter por cliente

CMD=${1:-}; C=${2:-}

erro(){ echo "ERRO: $*" >&2; exit 1; }
ok(){ echo "  ✔ $*"; }
validar(){
  [[ -n "$C" ]] || erro "informe o nome do cliente"
  [[ "$C" =~ ^[a-z][a-z0-9]{1,29}$ ]] || erro "nome inválido: use a-z e 0-9, 2 a 30 caracteres, começando com letra (ex.: pilares)"
}
dir(){ echo "$CLIENTES/$C"; }
existe(){ [[ -d "$(dir)" ]] || erro "cliente '$C' não existe"; }
senha(){ openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c "${1:-20}"; }
caddy_reload(){ docker exec $CADDY caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null; }
mqtt_reload(){ docker kill -s HUP $MQTT_CONT >/dev/null; }
mqtt_set(){ docker exec -u 1883:1883 $MQTT_CONT mosquitto_passwd -b /mosquitto/config/passwd "$1" "$2"; mqtt_reload; }
mqtt_del(){ docker exec -u 1883:1883 $MQTT_CONT mosquitto_passwd -D /mosquitto/config/passwd "$1" 2>/dev/null || true; mqtt_reload; }
env_get(){ grep -E "^$1=" "$(dir)/.env" | cut -d= -f2-; }

fazer_backup(){
  local D; D=$(dir); local T; T=$(date +%F_%H%M)
  mkdir -p "$D/backups"
  docker exec "piaccess_${C}_mongo" mongodump --archive --gzip --quiet \
    -u "$(env_get MONGO_USER)" -p "$(env_get MONGO_PASSWORD)" --authenticationDatabase admin \
    --db "$(env_get DB_NAME)" > "$D/backups/mongo_$T.archive.gz"
  tar czf "$D/backups/app_$T.tar.gz" --exclude=app/backups -C "$D/dados" app   # app/backups = backups do próprio sistema
  ls -t "$D"/backups/mongo_*.archive.gz 2>/dev/null | tail -n +$((BACKUPS_MANTER+1)) | xargs -r rm -f
  ls -t "$D"/backups/app_*.tar.gz       2>/dev/null | tail -n +$((BACKUPS_MANTER+1)) | xargs -r rm -f
  ok "backup $C → $D/backups (mongo_$T / app_$T)"
}

case "$CMD" in

criar)
  validar
  D=$(dir); [[ -e "$D" ]] && erro "cliente '$C' já existe"
  VERSAO=${3:-$VERSAO_PADRAO}
  NOME=${NOME:-$C}
  ADMIN_EMAIL=${ADMIN_EMAIL:-$ADMIN_EMAIL_PADRAO}
  docker network inspect proxy >/dev/null 2>&1 || erro "rede 'proxy' não existe (docker network create proxy)"
  grep -q "pattern readwrite piaccess/%u/#" /root/mosquitto/config/acl 2>/dev/null || erro "ACL do Mosquitto sem a regra 'pattern readwrite piaccess/%u/#'"

  mkdir -p "$BASE/template"
  [[ -f "$TEMPLATE" ]] || curl -fsSL "$TEMPLATE_URL" -o "$TEMPLATE" || erro "não consegui baixar o template"

  echo "Criando cliente '$C' (versão $VERSAO)..."
  mkdir -p "$D/dados/app" "$D/dados/mongo" "$D/backups"
  cp "$TEMPLATE" "$D/docker-compose.yml"

  MQTT_PASS=$(senha 20); ADMIN_PASS=$(senha 14)
  cat > "$D/.env" <<EOF
CLIENTE=$C
CLIENTE_NOME=$NOME
VERSAO=$VERSAO
PUBLIC_URL=https://$C.$DOMINIO
DB_NAME=piaccess
MONGO_USER=piaccess
MONGO_PASSWORD=$(senha 24)
JWT_SECRET=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASS
MQTT_HOST=$MQTT_HOST
MQTT_PORT=$MQTT_PORTA
MQTT_USER=$C
MQTT_PASSWORD=$MQTT_PASS
MQTT_TLS=false
MQTT_PREFIX=piaccess/$C
TZ=America/Sao_Paulo
SEED_DEMO=false
EOF
  chmod 600 "$D/.env"
  chown -R 10001:10001 "$D/dados/app"
  ok ".env gerado"

  mqtt_set "$C" "$MQTT_PASS";                               ok "usuário MQTT '$C' criado"

  printf '%s.%s {\n\treverse_proxy piaccess_%s:8000\n}\n' "$C" "$DOMINIO" "$C" > "$CADDY_DIR/$C.caddy"
  caddy_reload;                                             ok "Caddy: https://$C.$DOMINIO"

  ( cd "$D" && docker compose pull -q && docker compose up -d ) ; ok "containers iniciados"

  cat > "$D/CREDENCIAIS.txt" <<EOF
PI-ACCESS — cliente $C ($NOME)  — criado em $(date '+%d/%m/%Y %H:%M')
Painel ........ https://$C.$DOMINIO
Admin ......... $ADMIN_EMAIL  /  $ADMIN_PASS   (troque no primeiro acesso)

Configuração do FACIAL (painel web > MQTT):
  Habilitar ..................... sim
  ID Equipamento ................ <DeviceID do facial>
  Endereço ...................... $MQTT_HOST
  Porta ......................... $MQTT_PORTA
  ID Núvem (usuário) ............ $C
  Senha ......................... $MQTT_PASS
  Tópico ........................ piaccess/$C/face/<DeviceID>
  Evento de Identificação ....... Enviar com Foto
  Retomar do ponto de interrupção Habilitar
EOF
  chmod 600 "$D/CREDENCIAIS.txt"
  echo; cat "$D/CREDENCIAIS.txt"
  echo; echo "Aguarde ~1 min e acesse o painel. Se o domínio não abrir, confira o DNS de $C.$DOMINIO."
  ;;

listar)
  printf "%-16s %-12s %-10s %s\n" CLIENTE STATUS VERSAO URL
  for D in "$CLIENTES"/*/; do
    [[ -d "$D" ]] || continue
    C=$(basename "$D")
    S=$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "piaccess_$C" 2>/dev/null || echo "parado")
    printf "%-16s %-12s %-10s %s\n" "$C" "$S" "$(env_get VERSAO)" "https://$C.$DOMINIO"
  done
  echo; docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -E "NAME|piaccess_" || true
  ;;

pausar)  validar; existe; ( cd "$(dir)" && docker compose stop );  ok "$C pausado" ;;
ativar)  validar; existe; ( cd "$(dir)" && docker compose start ); ok "$C ativo" ;;

atualizar)
  validar; existe; V=${3:-}; [[ -n "$V" ]] || erro "informe a versão (ex.: 1.1.0)"
  ANT=$(env_get VERSAO)
  fazer_backup
  sed -i "s/^VERSAO=.*/VERSAO=$V/" "$(dir)/.env"
  echo "  ↓ baixando a imagem $V (pode levar alguns minutos)..."
  ( cd "$(dir)" && docker compose pull && docker compose up -d )
  ok "$C: $ANT → $V   (voltar: pi-cliente.sh atualizar $C $ANT)"
  ;;

backup)        validar; existe; fazer_backup ;;
backup-todos)  for D in "$CLIENTES"/*/; do [[ -d "$D" ]] || continue; C=$(basename "$D"); fazer_backup || echo "falha no backup de $C"; done ;;

logs)          validar; existe; ( cd "$(dir)" && docker compose logs -f --tail 100 app ) ;;
senha-admin)   validar; existe; docker exec -it "piaccess_$C" python -m app.reset_admin ;;
empresas)
  validar; existe; CSV=${3:-}; ADM=${4:-}
  [[ -f "$CSV" && -n "$ADM" ]] || erro "uso: pi-cliente empresas <cliente> <arquivo.csv> <email-admin>"
  curl -fsSL https://raw.githubusercontent.com/felipeitaenga/PI-ACCESS/main/deploy/pi-empresas.py -o "$BASE/pi-empresas.py"
  ( cd "$(dir)" && python3 "$BASE/pi-empresas.py" --url "https://$C.$DOMINIO" --admin "$ADM" --arquivo "$(realpath "$CSV")" )
  ;;
vapid)
  # chaves do aviso no celular (Web Push) do autocadastro; gera uma vez por cliente
  validar; existe
  if [[ -n "$(env_get VAPID_PRIVATE_KEY)" ]]; then ok "$C já tem chaves VAPID"; exit 0; fi
  KEYS=$(docker exec "piaccess_$C" python -c "
from py_vapid import Vapid01, b64urlencode
from cryptography.hazmat.primitives import serialization as s
v = Vapid01(); v.generate_keys()
pub = v.public_key.public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint)
prv = v.private_key.private_numbers().private_value.to_bytes(32, 'big')
print(b64urlencode(pub), b64urlencode(prv))") || erro "não foi possível gerar as chaves (container piaccess_$C rodando na 1.5.3+?)"
  read -r PUBK PRVK <<<"$KEYS"
  printf 'VAPID_PUBLIC_KEY=%s\nVAPID_PRIVATE_KEY=%s\n' "$PUBK" "$PRVK" >> "$(dir)/.env"
  ( cd "$(dir)" && docker compose up -d app ) && ok "chaves VAPID criadas para $C (aviso no celular ativo)" ;;
padrao)        validar; existe; docker exec "piaccess_$C" python -m app.bootstrap ${3:+"$3"} ;;

senha-mqtt)
  validar; existe; P=$(senha 20)
  mqtt_set "$C" "$P"
  sed -i "s/^MQTT_PASSWORD=.*/MQTT_PASSWORD=$P/" "$(dir)/.env"
  sed -i "s/^  Senha \.*.*/  Senha ......................... $P/" "$(dir)/CREDENCIAIS.txt"
  ( cd "$(dir)" && docker compose up -d )
  ok "nova senha MQTT de $C: $P   >>> atualize em TODOS os faciais deste cliente"
  ;;

excluir)
  validar; existe
  read -r -p "Digite o nome do cliente para confirmar a EXCLUSÃO de '$C': " CONF
  [[ "$CONF" == "$C" ]] || erro "confirmação não confere, nada foi feito"
  fazer_backup || echo "aviso: backup falhou (cliente parado?)"
  ( cd "$(dir)" && docker compose down )
  rm -f "$CADDY_DIR/$C.caddy"; caddy_reload
  mqtt_del "$C"
  mkdir -p "$EXCLUIDOS"; mv "$(dir)" "$EXCLUIDOS/${C}_$(date +%F_%H%M)"
  ok "$C removido. Dados e backups em $EXCLUIDOS/ (apague manualmente quando não precisar mais)"
  ;;

*)
  sed -n '3,23p' "$0" | sed 's/^# \{0,1\}//'
  ;;
esac
