import { useCallback, useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { FormRow } from "@/components/CrudPage";
import { cn } from "@/lib/utils";
import { PlugZap, Radio, Save } from "lucide-react";
import { toast } from "sonner";

const fmt = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

function MqttStatus({ st }) {
  if (!st) return null;
  return (
    <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4" data-testid="mqtt-status">
      <div className="rounded border border-border p-2"><p className="text-muted-foreground">Conexão</p>
        <p className={cn("font-semibold", st.connected ? "text-emerald-400" : "text-red-400")} data-testid="mqtt-connected">{st.connected ? "Conectado" : "Desconectado"}</p></div>
      <div className="rounded border border-border p-2"><p className="text-muted-foreground">Broker</p><p className="font-mono">{st.host || "—"}:{st.port || ""}</p></div>
      <div className="rounded border border-border p-2"><p className="text-muted-foreground">Mensagens recebidas</p><p className="font-mono" data-testid="mqtt-msg-count">{st.messages}</p></div>
      <div className="rounded border border-border p-2"><p className="text-muted-foreground">Última mensagem</p><p className="font-mono">{fmt(st.last_message_at)}</p></div>
      {st.last_error && <p className="col-span-full text-red-400">Erro: {st.last_error}</p>}
    </div>
  );
}

export default function Integrations() {
  const [cfg, setCfg] = useState({ host: "", port: 1883, username: "", password: "", client_id: "nx-access-server", enabled: true });
  const [log, setLog] = useState({ status: null, messages: [] });
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadLog = useCallback(() => api.get("/integrations/mqtt/log").then(({ data }) => setLog(data)).catch(() => {}), []);
  useEffect(() => {
    api.get("/integrations/mqtt").then(({ data }) => setCfg((c) => ({ ...c, ...data.config, password: "" }))).catch(() => {});
    loadLog();
    const t = setInterval(loadLog, 5000);
    return () => clearInterval(t);
  }, [loadLog]);

  const set = (k) => (v) => setCfg((c) => ({ ...c, [k]: v }));
  const save = async () => {
    setBusy(true);
    try { await api.put("/integrations/mqtt", { ...cfg, port: Number(cfg.port) }); toast.success("Configuração MQTT salva — reconectando"); loadLog(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const runTest = async () => {
    setTest({ detail: "Testando…" });
    try { const { data } = await api.post("/integrations/mqtt/test", { ...cfg, port: Number(cfg.port) }); setTest(data); }
    catch (e) { setTest({ ok: false, detail: formatApiErrorDetail(e.response?.data?.detail) }); }
  };

  return (
    <div data-testid="integrations-page">
      <PageHeader title="Integrações" subtitle="MQTT — broker usado pelos faciais Beward" />
      <Card className="mb-4 border-border bg-card p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground"><Radio className="h-4 w-4 text-sky-400" />Broker MQTT</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FormRow label="Endereço"><Input value={cfg.host || ""} onChange={(e) => set("host")(e.target.value)} data-testid="mqtt-host" /></FormRow>
          <FormRow label="Porta (TCP)"><Input type="number" value={cfg.port || ""} onChange={(e) => set("port")(e.target.value)} data-testid="mqtt-port" /></FormRow>
          <FormRow label="Client ID do servidor"><Input value={cfg.client_id || ""} onChange={(e) => set("client_id")(e.target.value)} data-testid="mqtt-client-id" /></FormRow>
          <FormRow label="Usuário (vazio = anônimo)"><Input value={cfg.username || ""} onChange={(e) => set("username")(e.target.value)} data-testid="mqtt-username" /></FormRow>
          <FormRow label="Senha (criptografada)"><Input type="password" placeholder="(inalterada)" value={cfg.password} onChange={(e) => set("password")(e.target.value)} data-testid="mqtt-password" /></FormRow>
          <label className="flex items-center gap-2 pt-6 text-sm"><Switch checked={!!cfg.enabled} onCheckedChange={set("enabled")} data-testid="mqtt-enabled" />Habilitado</label>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">O servidor conecta de saída ao broker (QoS 1, reconexão automática) e assina <span className="font-mono">mqtt/face/#</span>.</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={runTest} data-testid="mqtt-test-button"><PlugZap className="mr-2 h-4 w-4" />Testar conexão</Button>
          <Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" disabled={busy} onClick={save} data-testid="mqtt-save-button"><Save className="mr-2 h-4 w-4" />Salvar e reconectar</Button>
          {test && <span className={cn("text-sm", test.ok ? "text-emerald-400" : "text-red-400")} data-testid="mqtt-test-result">{test.detail}{test.latency_ms ? ` (${test.latency_ms} ms)` : ""}</span>}
        </div>
      </Card>
      <Card className="border-border bg-card p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Status e mensagens recebidas</h2>
        <MqttStatus st={log.status} />
        <div className="mt-3 max-h-80 space-y-1 overflow-y-auto" data-testid="mqtt-log">
          {log.messages.length === 0 && <p className="py-4 text-center text-xs text-muted-foreground">Nenhuma mensagem recebida ainda. Confira no facial: Habilitar MQTT, endereço/porta do broker e ID Equipamento.</p>}
          {log.messages.map((m, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 rounded border border-border/60 px-2 py-1 font-mono text-[11px]">
              <span className="col-span-3 text-muted-foreground">{fmt(m.at)}</span>
              <span className="col-span-4 truncate text-sky-300">{m.topic}</span>
              <span className="col-span-2">{m.operator}</span>
              <span className="col-span-3 truncate text-muted-foreground">{m.device_id} {m.summary}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
