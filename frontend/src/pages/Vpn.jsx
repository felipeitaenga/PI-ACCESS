import { useCallback, useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Copy, Download, KeyRound, Loader2, Network, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const ago = (ts) => {
  if (!ts) return "nunca";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return `há ${s} s`;
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  return `há ${Math.round(s / 86400)} dias`;
};
const copy = (t) => navigator.clipboard.writeText(t).then(() => toast.success("Copiado"), () => toast.error("Não foi possível copiar"));

export default function Vpn() {
  const [st, setSt] = useState(null);
  const [script, setScript] = useState("");
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/vpn").then(({ data }) => setSt(data)).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);

  const getScript = async () => {
    try {
      const { data } = await api.get("/vpn/mikrotik/script", { responseType: "text" });
      setScript(data);
      const l = await api.post("/vpn/mikrotik/link");
      setLink(l.data);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Aguardando o servidor"); }
  };

  // depois de gerar, espera o servidor liberar (sincroniza a cada 15 s)
  useEffect(() => {
    if (!st?.pending) return undefined;
    const t = setInterval(async () => {
      const { data } = await api.get("/vpn");
      setSt(data);
      if (data.ready) { clearInterval(t); setBusy(false); getScript(); }
    }, 4000);
    return () => clearInterval(t);
  }, [st?.pending]); // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async () => {
    if (st?.ready && !window.confirm("Gerar novas chaves? O MikroTik atual para de funcionar até você colar o script novo nele.")) return;
    setBusy(true); setScript(""); setLink(null);
    try { const { data } = await api.post("/vpn/mikrotik"); setSt(data); }
    catch (e) { setBusy(false); toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  const dl = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([script], { type: "text/plain" }));
    a.download = `${st?.identity || "scarvel"}.rsc`;
    a.click();
  };

  if (!st) return <div className="p-6 text-muted-foreground"><Loader2 className="inline h-4 w-4 animate-spin" /> Carregando…</div>;
  return (
    <div className="space-y-4">
      <PageHeader title="Rede / VPN" subtitle="O MikroTik deste cliente liga os faciais ao SCARVEL por uma VPN segura" />
      <Card className="border-border bg-card p-5" data-testid="vpn-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><Network className="h-5 w-5" /></div>
            <div>
              <div className="font-semibold">MikroTik deste cliente{st.n ? ` · nº ${st.n}` : ""}</div>
              <div className="text-xs text-muted-foreground">{st.identity || "ainda não configurado"}</div>
            </div>
          </div>
          <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${st.online ? "border-emerald-500/40 text-emerald-400" : "border-amber-500/40 text-amber-300"}`} data-testid="vpn-online">
            ● {st.online ? "Online" : st.pending ? "Aguardando servidor…" : st.ready ? "Offline" : "Não configurado"}
          </span>
        </div>
        {st.n && (
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-muted-foreground">Último contato</dt><dd>{ago(st.latest_handshake)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">MikroTik na VPN</dt><dd className="font-mono">{st.vpn_ip}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Rede dos faciais</dt><dd className="font-mono">192.168.88.101 – .199</dd></div>
            <div><dt className="text-xs text-muted-foreground">Gateway dos faciais</dt><dd className="font-mono">192.168.88.1</dd></div>
          </dl>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button className="bg-sky-500 text-white" onClick={generate} disabled={busy || st.pending} data-testid="vpn-generate">
            {busy || st.pending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <KeyRound className="mr-2 h-4 w-4" />}
            {st.ready ? "Gerar de novo (trocar MikroTik)" : "Gerar script do MikroTik"}
          </Button>
          {st.ready && !script && <Button variant="outline" onClick={getScript} data-testid="vpn-show"><RefreshCw className="mr-2 h-4 w-4" />Ver script atual</Button>}
        </div>
        {(busy || st.pending) && <p className="mt-2 text-xs text-muted-foreground">Liberando no servidor… leva até 30 s (na primeira vez o sistema reinicia em segundos).</p>}
      </Card>

      {script && (
        <Card className="space-y-3 border-border bg-card p-5" data-testid="vpn-script">
          <h2 className="font-heading text-sm font-bold uppercase tracking-widest">Colar no MikroTik</h2>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
            <li>Porta 1 do MikroTik na internet do cliente. Faciais nas portas 2–5 (ou switch), IP fixo 192.168.88.101 em diante, gateway 192.168.88.1.</li>
            <li>Abra o MikroTik (WinBox › New Terminal, ou página web › Terminal).</li>
            <li>Cole o script abaixo e aperte Enter. Em ~30 s o status acima fica <b>Online</b>.</li>
          </ol>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => copy(script)} data-testid="vpn-copy"><Copy className="mr-2 h-4 w-4" />Copiar script</Button>
            <Button variant="outline" onClick={dl}><Download className="mr-2 h-4 w-4" />Baixar .rsc</Button>
          </div>
          <pre className="max-h-72 overflow-auto rounded-md border border-border bg-black/40 p-3 text-[11px] leading-relaxed">{script}</pre>
          {link && (
            <div className="rounded-md border border-sky-500/30 bg-sky-500/5 p-3 text-sm">
              <p className="mb-1 font-medium">Ou, sem copiar e colar: digite no Terminal do MikroTik (link vale {link.minutes} min, 1 uso)</p>
              <pre className="overflow-auto text-[11px]">{link.commands.join("\n")}</pre>
              <Button size="sm" variant="ghost" className="mt-1" onClick={() => copy(link.commands.join("\n"))}><Copy className="mr-1 h-3 w-3" />Copiar comandos</Button>
              <p className="mt-1 text-xs text-muted-foreground">MikroTik novo bloqueia o download (device-mode): rode antes /system/device-mode/update fetch=yes e desligue/ligue o MikroTik.</p>
            </div>
          )}
          <p className="text-xs text-amber-300">O script contém a chave secreta do MikroTik: não envie por WhatsApp/e-mail.</p>
        </Card>
      )}
    </div>
  );
}
