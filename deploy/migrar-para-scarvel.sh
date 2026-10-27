#!/bin/bash
# =====================================================================
#  migrar-para-scarvel.sh — migra UM cliente da instalação antiga (PI-ACCESS) para SCARVEL
#
#  Uso (no servidor, como root):
#    bash migrar-para-scarvel.sh <cliente> [versao]        ex.: bash migrar-para-scarvel.sh pilares 2.0.0
#
#  O que faz (a instalação antiga fica INTACTA em /opt/piaccess para voltar, se precisar):
#   1. backup completo (mongodump + cópia da pasta do cliente parada)
#   2. copia /opt/piaccess/clientes/<c> → /opt/scarvel/clientes/<c>
#   3. novo docker-compose (containers scarvel_<c>), banco e usuário "scarvel", prefixo MQTT scarvel/<c>
#   4. Mosquitto: libera o tópico scarvel/<usuário>/# (o antigo continua até trocar no facial)
#   5. Caddy aponta para scarvel_<c>; instala o comando "scarvel"
#
#  Voltar para o antigo:
#    cd /opt/scarvel/clientes/<c> && docker compose down
#    cd /opt/piaccess/clientes/<c> && docker compose up -d
#    (e no Caddy: reverse_proxy piaccess_<c>:8000)
# =====================================================================
set -euo pipefail

C=${1:-}; V=${2:-2.0.0}
OLD=/opt/piaccess; NEW=/opt/scarvel
REPO_RAW=https://raw.githubusercontent.com/felipeitaenga/SCARVEL/main
CADDY=nx360_caddy; CADDY_DIR=/opt/caddy/clientes
MQTT_CONT=mosquitto; ACL=/root/mosquitto/config/acl

erro(){ echo "ERRO: $*" >&2; exit 1; }
ok(){ echo "  ✔ $*"; }
[[ "$C" =~ ^[a-z][a-z0-9]{1,29}$ ]] || erro "uso: bash migrar-para-scarvel.sh <cliente> [versao]"
OD=$OLD/clientes/$C; ND=$NEW/clientes/$C
[[ -d "$OD" ]] || erro "não existe $OD"
[[ -e "$ND" ]] && erro "$ND já existe (migração já feita?)"
command -v curl >/dev/null || erro "curl não instalado"
envget(){ grep -E "^$1=" "$2" | cut -d= -f2- || true; }

OLD_DB=$(envget DB_NAME "$OD/.env"); OLD_USER=$(envget MONGO_USER "$OD/.env"); MPASS=$(envget MONGO_PASSWORD "$OD/.env")
[[ -n "$OLD_DB" && -n "$OLD_USER" && -n "$MPASS" ]] || erro ".env antigo sem DB_NAME/MONGO_USER/MONGO_PASSWORD"
T=$(date +%F_%H%M)

echo "== 1/7 Baixando arquivos da versão SCARVEL"
mkdir -p "$NEW/template" "$NEW/clientes"
curl -fsSL "$REPO_RAW/deploy/docker-compose.yml" -o "$NEW/template/docker-compose.yml" || erro "não consegui baixar o docker-compose (repositório já renomeado para SCARVEL?)"
curl -fsSL "$REPO_RAW/deploy/scarvel.sh" -o /usr/local/bin/scarvel && chmod +x /usr/local/bin/scarvel
ok "template e comando 'scarvel' instalados"

echo "== 2/7 Backup (instalação antiga)"
mkdir -p "$OD/backups"
docker exec "piaccess_${C}_mongo" mongodump --archive --gzip --quiet -u "$OLD_USER" -p "$MPASS" \
  --authenticationDatabase admin --db "$OLD_DB" > "$OD/backups/pre-scarvel_$T.archive.gz"
ok "mongodump → $OD/backups/pre-scarvel_$T.archive.gz"
( cd "$OD" && docker compose down )
tar czf "$OLD/pre-scarvel_${C}_$T.tar.gz" -C "$OLD/clientes" "$C"
ok "cópia completa (parada) → $OLD/pre-scarvel_${C}_$T.tar.gz"

echo "== 3/7 Copiando para $ND"
cp -a "$OD" "$ND"
cp "$NEW/template/docker-compose.yml" "$ND/docker-compose.yml"
sed -i "s/^VERSAO=.*/VERSAO=$V/" "$ND/.env"
if grep -q "^MQTT_PREFIX=" "$ND/.env"; then sed -i "s#^MQTT_PREFIX=.*#MQTT_PREFIX=scarvel/$C#" "$ND/.env"
else echo "MQTT_PREFIX=scarvel/$C" >> "$ND/.env"; fi
ok "pasta, compose e .env (versão $V, MQTT scarvel/$C)"

echo "== 4/7 Banco: $OLD_DB → scarvel, usuário $OLD_USER → scarvel"
( cd "$ND" && docker compose up -d mongo )
for i in $(seq 1 30); do docker exec "scarvel_${C}_mongo" mongosh --quiet --eval "db.adminCommand('ping').ok" >/dev/null 2>&1 && break; sleep 2; done
MS(){ docker exec "scarvel_${C}_mongo" mongosh --quiet -u "$OLD_USER" -p "$MPASS" --authenticationDatabase admin --eval "$1"; }
if [[ "$OLD_DB" != "scarvel" ]]; then
  docker exec "scarvel_${C}_mongo" sh -c "mongodump --archive --quiet -u '$OLD_USER' -p '$MPASS' --authenticationDatabase admin --db '$OLD_DB' \
    | mongorestore --archive --quiet -u '$OLD_USER' -p '$MPASS' --authenticationDatabase admin --nsFrom '$OLD_DB.*' --nsTo 'scarvel.*'"
  A=$(MS "var n=0; db.getSiblingDB('$OLD_DB').getCollectionNames().forEach(c=>n+=db.getSiblingDB('$OLD_DB')[c].countDocuments()); print(n)")
  B=$(MS "var n=0; db.getSiblingDB('scarvel').getCollectionNames().forEach(c=>n+=db.getSiblingDB('scarvel')[c].countDocuments()); print(n)")
  [[ "$A" == "$B" ]] || erro "contagem diferente após copiar o banco ($A ≠ $B) — nada apagado; instalação antiga intacta"
  MS "db.getSiblingDB('$OLD_DB').dropDatabase()" >/dev/null
  ok "banco copiado ($B documentos) e antigo removido (backup no passo 2)"
fi
if [[ "$OLD_USER" != "scarvel" ]]; then
  MS "db.getSiblingDB('admin').createUser({user:'scarvel',pwd:'$MPASS',roles:['root']})" >/dev/null
  docker exec "scarvel_${C}_mongo" mongosh --quiet -u scarvel -p "$MPASS" --authenticationDatabase admin \
    --eval "db.getSiblingDB('admin').dropUser('$OLD_USER')" >/dev/null
  ok "usuário do banco agora é 'scarvel'"
fi
sed -i "s/^DB_NAME=.*/DB_NAME=scarvel/; s/^MONGO_USER=.*/MONGO_USER=scarvel/" "$ND/.env"

echo "== 5/7 Mosquitto (tópico scarvel/<usuário>/#)"
if [[ -f "$ACL" ]] && ! grep -q "pattern readwrite scarvel/%u/#" "$ACL"; then
  printf '\npattern readwrite scarvel/%%u/#\n' >> "$ACL"; docker kill -s HUP $MQTT_CONT >/dev/null; ok "regra adicionada"
else ok "regra já existia (ou ACL em outro lugar: confira $ACL)"; fi

echo "== 6/7 Subindo SCARVEL $V e Caddy"
( cd "$ND" && docker compose pull && docker compose up -d )
if [[ -f "$CADDY_DIR/$C.caddy" ]]; then
  sed -i "s/piaccess_$C:8000/scarvel_$C:8000/" "$CADDY_DIR/$C.caddy"
  docker exec $CADDY caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null && ok "Caddy → scarvel_$C"
fi
for i in $(seq 1 40); do docker exec "scarvel_$C" curl -fs localhost:8000/api/health >/dev/null 2>&1 && break; sleep 3; done
docker exec "scarvel_$C" curl -fs localhost:8000/api/health >/dev/null 2>&1 && ok "aplicação respondendo" || echo "  ! aplicação ainda não respondeu — veja: scarvel logs $C"

echo "== 7/7 Configuração do servidor e credenciais"
if [[ ! -f "$NEW/scarvel.conf" ]]; then
  PU=$(envget PUBLIC_URL "$ND/.env"); DOM=${PU#https://$C.}
  cat > "$NEW/scarvel.conf" <<EOF
# Configuração do comando "scarvel" neste servidor
DOMINIO=$DOM                 # troque quando tiver o domínio próprio (ex.: scarvel.com.br)
MQTT_HOST=$(envget MQTT_HOST "$ND/.env")
MQTT_PORTA=$(envget MQTT_PORT "$ND/.env")
ADMIN_EMAIL_PADRAO=$(envget ADMIN_EMAIL "$ND/.env")
CADDY=$CADDY
EOF
  ok "$NEW/scarvel.conf criado (DOMINIO=$DOM)"
fi
[[ -f "$ND/CREDENCIAIS.txt" ]] && sed -i "s#piaccess/$C/face#scarvel/$C/face#; s/^PI-ACCESS/SCARVEL/" "$ND/CREDENCIAIS.txt"
if crontab -l 2>/dev/null | grep -q "pi-cliente"; then
  crontab -l | sed 's#[^ ]*pi-cliente[^ ]*#/usr/local/bin/scarvel#g' | crontab - && ok "cron de backup → scarvel"
fi

cat <<EOF

=====================================================================
 MIGRAÇÃO CONCLUÍDA — $C agora roda como SCARVEL $V
=====================================================================
 Falta 1 passo em CADA facial deste cliente (painel web › MQTT):
   Tópico:  piaccess/$C/face/<DeviceID>   →   scarvel/$C/face/<DeviceID>
 (usuário e senha MQTT não mudam)

 Comandos novos:  scarvel listar | scarvel atualizar $C <versão> | scarvel logs $C
 Instalação antiga parada e intacta em $OD (apague depois de alguns dias)
 Backup: $OLD/pre-scarvel_${C}_$T.tar.gz
=====================================================================
EOF
