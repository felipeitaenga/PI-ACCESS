#!/bin/bash
# =====================================================================
#  scarvel-vpn.sh — VPN WireGuard entre o servidor SCARVEL e o roteador do local (MikroTik)
#
#  Rede da VPN: 10.66.0.0/24  (servidor = 10.66.0.1, cada roteador = 10.66.0.N)
#
#  1) No servidor, uma vez:            bash scarvel-vpn.sh init
#  2) Gerar o script do MikroTik:      bash scarvel-vpn.sh mikrotik <N> <ip_facial> <porta_cliente>
#        ex.: bash scarvel-vpn.sh mikrotik 2 192.168.0.13 8101
#     (cole no Terminal do MikroTik; ele mostra a chave pública dele no final)
#  3) Liberar o roteador no servidor:  bash scarvel-vpn.sh add <cliente> <N> <chave_publica_mikrotik> <porta_cliente>
#        ex.: bash scarvel-vpn.sh add pilares 2 AbC...= 8101
#  Ver status:                         bash scarvel-vpn.sh status
#
#  Caminhos:
#   servidor → facial : app → 10.66.0.N:80NN (MikroTik repassa para <ip_facial>:80)
#   facial → servidor : facial → <IP do MikroTik na rede local>:<porta_cliente> → 10.66.0.1:<porta_cliente> → app
#  A porta do app só é publicada no IP da VPN (10.66.0.1), nunca na internet.
# =====================================================================
set -euo pipefail
WG=/etc/wireguard/wg0.conf
PORT=51820
SRV_IP=10.66.0.1
PUBLIC_IP=${PUBLIC_IP:-$(curl -fs4 https://ifconfig.me || hostname -I | awk '{print $1}')}
erro(){ echo "ERRO: $*" >&2; exit 1; }
ok(){ echo "  ✔ $*"; }

cmd=${1:-}; shift || true
case "$cmd" in
init)
  command -v wg >/dev/null || { apt-get update -qq && apt-get install -y -qq wireguard >/dev/null; }
  ok "wireguard instalado"
  if [[ ! -f $WG ]]; then
    umask 077
    PRIV=$(wg genkey)
    cat > $WG <<EOF
[Interface]
Address = $SRV_IP/24
ListenPort = $PORT
PrivateKey = $PRIV
EOF
    ok "criado $WG"
  else ok "$WG já existia (mantido)"; fi
  systemctl enable --now wg-quick@wg0 >/dev/null 2>&1 || systemctl restart wg-quick@wg0
  ok "wg0 ativo ($SRV_IP)"
  # o Docker precisa subir depois da VPN (a porta do app fica presa ao IP 10.66.0.1)
  mkdir -p /etc/systemd/system/docker.service.d
  printf '[Unit]\nAfter=wg-quick@wg0.service\nWants=wg-quick@wg0.service\n' > /etc/systemd/system/docker.service.d/wireguard.conf
  systemctl daemon-reload
  ok "Docker inicia depois da VPN"
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow $PORT/udp >/dev/null; ok "ufw: $PORT/udp liberada"; fi
  echo; echo "Chave pública do servidor: $(wg show wg0 public-key)"
  ;;
mikrotik)
  N=${1:-}; FACIAL=${2:-}; CPORT=${3:-}
  [[ "$N" =~ ^[0-9]+$ && $N -ge 2 && $N -le 254 && -n "$FACIAL" && "$CPORT" =~ ^[0-9]+$ ]] || erro "uso: mikrotik <N 2-254> <ip_facial> <porta_cliente>"
  SPUB=$(wg show wg0 public-key 2>/dev/null) || erro "rode 'init' antes"
  FPORT=$((8000 + N))
  cat <<EOF
# ===== cole no Terminal do MikroTik (WinBox › New Terminal) =====
/interface wireguard add name=wg-scarvel listen-port=13231 comment=scarvel
/interface wireguard peers add interface=wg-scarvel public-key="$SPUB" endpoint-address=$PUBLIC_IP endpoint-port=$PORT allowed-address=$SRV_IP/32 persistent-keepalive=25s comment=scarvel
/ip address add address=10.66.0.$N/24 interface=wg-scarvel comment=scarvel
# servidor -> facial (porta $FPORT da VPN vai para o facial $FACIAL:80)
/ip firewall nat add chain=dstnat in-interface=wg-scarvel protocol=tcp dst-port=$FPORT action=dst-nat to-addresses=$FACIAL to-ports=80 comment=scarvel
/ip firewall nat add chain=srcnat out-interface=ether1 dst-address=$FACIAL protocol=tcp dst-port=80 action=masquerade comment=scarvel
# facial -> servidor (facial manda para o IP deste MikroTik, porta $CPORT)
/ip firewall nat add chain=dstnat in-interface=ether1 src-address=$FACIAL protocol=tcp dst-port=$CPORT action=dst-nat to-addresses=$SRV_IP to-ports=$CPORT comment=scarvel
/ip firewall nat add chain=srcnat out-interface=wg-scarvel action=masquerade comment=scarvel
/ip firewall filter add chain=forward in-interface=wg-scarvel dst-address=$FACIAL action=accept place-before=0 comment=scarvel
/ip firewall filter add chain=forward in-interface=ether1 src-address=$FACIAL out-interface=wg-scarvel action=accept place-before=0 comment=scarvel
# acesso ao MikroTik pela rede local (web e WinBox), sem precisar de cabo na porta 2
/ip firewall filter add chain=input in-interface=ether1 src-address=${FACIAL%.*}.0/24 protocol=tcp dst-port=80,8291 action=accept place-before=0 comment="scarvel: acesso pela rede local"
:put "CHAVE PUBLICA DO MIKROTIK:"
:put [/interface wireguard get [find name=wg-scarvel] public-key]
:put "IP DO MIKROTIK NA REDE LOCAL:"
:put [/ip address get [find interface=ether1] address]
# ===== fim =====
EOF
  ;;
add)
  C=${1:-}; N=${2:-}; KEY=${3:-}; CPORT=${4:-}
  [[ "$C" =~ ^[a-z][a-z0-9]{1,29}$ && "$N" =~ ^[0-9]+$ && ${#KEY} -eq 44 && "$CPORT" =~ ^[0-9]+$ ]] || erro "uso: add <cliente> <N> <chave_publica_44_caracteres> <porta_cliente>"
  D=/opt/scarvel/clientes/$C
  [[ -d $D ]] || erro "cliente $C não existe ($D)"
  grep -q "$KEY" $WG && ok "peer já existia" || {
    printf '\n[Peer]\n# %s (roteador 10.66.0.%s)\nPublicKey = %s\nAllowedIPs = 10.66.0.%s/32\n' "$C" "$N" "$KEY" "$N" >> $WG
    wg set wg0 peer "$KEY" allowed-ips "10.66.0.$N/32"
    ok "roteador 10.66.0.$N liberado na VPN"; }
  cat > $D/docker-compose.override.yml <<EOF
# Gerado por scarvel-vpn.sh — faciais deste cliente chegam ao app pela VPN (só no IP $SRV_IP)
services:
  app:
    ports:
      - "$SRV_IP:$CPORT:8000"
EOF
  ( cd $D && docker compose up -d app >/dev/null )
  ok "app $C publicado em $SRV_IP:$CPORT (só VPN)"
  echo; echo "No SCARVEL (Controladoras › facial): IP 10.66.0.$N  Porta $((8000 + N))"
  echo "Modo Online: endereço = IP do MikroTik na rede local, porta $CPORT"
  ;;
status)
  wg show wg0
  ;;
*) sed -n '2,21p' "$0" ;;
esac
