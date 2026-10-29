#!/usr/bin/env python3
"""scarvel-vpn-sync — roda no SERVIDOR (root) a cada 15 s (systemd timer).

Ponte entre o app de cada cliente e a VPN WireGuard do servidor (wg0):
  lê   /opt/scarvel/clientes/<c>/dados/app/vpn/request.json  (chave pública do MikroTik pedida pelo app)
  grava /opt/scarvel/clientes/<c>/dados/app/vpn/status.json  (nº, chave do servidor, porta, último contato)

Cada cliente recebe um nº N (2..254): MikroTik = 10.66.0.N, faciais vistos como 10.67.N.0/24,
app publicado só em 10.66.0.1:<porta>. Isolamento: o MikroTik N só abre conexão com a porta do próprio cliente.
Registro: /etc/scarvel-vpn/clients.json
"""
import glob
import json
import os
import re
import subprocess
import time

WG_CONF = "/etc/wireguard/wg0.conf"
REG = "/etc/scarvel-vpn/clients.json"
BASE = "/opt/scarvel/clientes"
SRV_IP = "10.66.0.1"
PORT = 51820
CHAIN = "SCARVEL-VPN"


APP_UID = 10001  # usuário do container (Dockerfile: scarvel)


def sh(*cmd, check=False, inp=None, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, input=inp, cwd=cwd)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)}: {r.stderr.strip()}")
    return r


def load_json(p, default):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(p, data, mode=0o644):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.chmod(tmp, mode)
    os.replace(tmp, p)


def split_conf(text):
    """→ (texto do [Interface], lista de peers {pubkey, allowed, comment})"""
    parts = re.split(r"\n(?=\[Peer\])", text.strip())
    iface, peers = parts[0], []
    for blk in parts[1:]:
        key = re.search(r"PublicKey\s*=\s*(\S+)", blk)
        allowed = re.search(r"AllowedIPs\s*=\s*(.+)", blk)
        comment = re.search(r"#\s*(.+)", blk)
        if key:
            peers.append({"pubkey": key.group(1), "allowed": allowed.group(1).strip() if allowed else "",
                          "comment": comment.group(1).strip() if comment else ""})
    return iface, peers


def bootstrap(reg, peers):
    """Instalações feitas com 'scarvel-vpn add' (comentário '<cliente> (roteador 10.66.0.N)')."""
    for p in peers:
        m = re.match(r"(?:scarvel:)?([a-z][a-z0-9]{1,29})\b", p["comment"])
        n = re.search(r"10\.66\.0\.(\d+)/32", p["allowed"])
        if m and n and m.group(1) not in reg["clients"]:
            c = m.group(1)
            port = None
            try:
                txt = open(f"{BASE}/{c}/docker-compose.override.yml").read()
                pm = re.search(rf"{re.escape(SRV_IP)}:(\d+):8000", txt)
                port = int(pm.group(1)) if pm else None
            except OSError:
                pass
            reg["clients"][c] = {"n": int(n.group(1)), "port": port or 8100 + int(n.group(1)), "pubkey": p["pubkey"]}


def free_n(reg):
    used = {v["n"] for v in reg["clients"].values()}
    return next(i for i in range(2, 255) if i not in used)


def free_port(reg, n):
    used = {v["port"] for v in reg["clients"].values()}
    p = 8100 + n
    while p in used:
        p += 1
    return p


def ensure_override(c, port):
    d = f"{BASE}/{c}"
    want = (f"# Gerado por scarvel-vpn — faciais deste cliente chegam ao app pela VPN (só no IP {SRV_IP})\n"
            f"services:\n  app:\n    ports:\n      - \"{SRV_IP}:{port}:8000\"\n")
    p = f"{d}/docker-compose.override.yml"
    try:
        if open(p).read() == want:
            return False
    except OSError:
        pass
    with open(p, "w") as f:
        f.write(want)
    sh("docker", "compose", "up", "-d", "app", cwd=d)
    return True


def firewall(reg):
    if sh("iptables", "-nL", "DOCKER-USER").returncode:
        return  # Docker ainda não criou a chain
    sh("iptables", "-N", CHAIN)
    sh("iptables", "-F", CHAIN)
    for v in reg["clients"].values():
        sh("iptables", "-A", CHAIN, "-i", "wg0", "-s", f"10.66.0.{v['n']}", "-p", "tcp",
           "-m", "conntrack", "--ctorigdstport", str(v["port"]), "-j", "RETURN")
    sh("iptables", "-A", CHAIN, "-i", "wg0", "-m", "conntrack", "--ctstate", "NEW", "-j", "DROP")
    sh("iptables", "-A", CHAIN, "-j", "RETURN")
    if sh("iptables", "-C", "DOCKER-USER", "-j", CHAIN).returncode:
        sh("iptables", "-I", "DOCKER-USER", "1", "-j", CHAIN)


def main():
    if not os.path.exists(WG_CONF):
        return
    reg = load_json(REG, {"clients": {}})
    reg.setdefault("clients", {})
    if not reg.get("endpoint"):
        r = sh("curl", "-fs4", "--max-time", "5", "https://ifconfig.me")
        reg["endpoint"] = r.stdout.strip() or sh("hostname", "-I").stdout.split()[0]
    text = open(WG_CONF).read()
    iface, peers = split_conf(text)
    bootstrap(reg, peers)
    srv_pub = sh("wg", "show", "wg0", "public-key").stdout.strip()

    changed_peers = False
    for d in sorted(glob.glob(f"{BASE}/*/")):
        c = os.path.basename(d.rstrip("/"))
        req = load_json(f"{d}dados/app/vpn/request.json", {})
        if req.get("pubkey") and len(req["pubkey"]) == 44:
            e = reg["clients"].get(c)
            if not e:
                n = free_n(reg)
                e = reg["clients"][c] = {"n": n, "port": free_port(reg, n), "pubkey": ""}
            if e["pubkey"] != req["pubkey"]:
                e["pubkey"] = req["pubkey"]
                changed_peers = True

    # wg0.conf: [Interface] + um peer por cliente
    blocks = [iface.strip()]
    for c, v in sorted(reg["clients"].items(), key=lambda x: x[1]["n"]):
        if v.get("pubkey"):
            blocks.append(f"[Peer]\n# scarvel:{c} (nº {v['n']})\nPublicKey = {v['pubkey']}\n"
                          f"AllowedIPs = 10.66.0.{v['n']}/32, 10.67.{v['n']}.0/24")
    new = "\n\n".join(blocks) + "\n"
    if new != text.strip() + "\n" or changed_peers:
        with open(WG_CONF + ".tmp", "w") as f:
            f.write(new)
        os.chmod(WG_CONF + ".tmp", 0o600)
        os.replace(WG_CONF + ".tmp", WG_CONF)
        stripped = sh("wg-quick", "strip", "wg0").stdout
        sh("wg", "syncconf", "wg0", "/dev/stdin", inp=stripped)
    for v in reg["clients"].values():
        sh("ip", "route", "replace", f"10.67.{v['n']}.0/24", "dev", "wg0")
    write_json(REG, reg, 0o600)
    firewall(reg)

    # status para o app de cada cliente
    dump = sh("wg", "show", "wg0", "dump").stdout.splitlines()[1:]
    by_key = {}
    for line in dump:
        f = line.split("\t")
        if len(f) >= 7:
            by_key[f[0]] = {"latest_handshake": int(f[4] or 0), "rx": int(f[5] or 0), "tx": int(f[6] or 0)}
    for c, v in reg["clients"].items():
        d = f"{BASE}/{c}"
        if not os.path.isdir(d):
            continue
        ensure_override(c, v["port"])
        st = {"n": v["n"], "server_pubkey": srv_pub, "endpoint": reg["endpoint"], "endpoint_port": PORT,
              "app_port": v["port"], "peer_pubkey": v.get("pubkey", ""), "updated_at": int(time.time()),
              **by_key.get(v.get("pubkey", ""), {"latest_handshake": 0, "rx": 0, "tx": 0})}
        vdir = f"{d}/dados/app/vpn"
        if not os.path.isdir(vdir):
            os.makedirs(vdir)
            os.chown(vdir, APP_UID, APP_UID)  # o app (uid 10001) grava o request.json aqui
        write_json(f"{vdir}/status.json", st)


def resumo(c):
    st = load_json(f"{BASE}/{c}/dados/app/vpn/status.json", {})
    if not st.get("n"):
        raise SystemExit(1)
    h = st.get("latest_handshake") or 0
    print(f"nº {st['n']} " + ("online" if h and time.time() - h < 180 else "offline"))


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--resumo":
        resumo(sys.argv[2])
    else:
        main()
