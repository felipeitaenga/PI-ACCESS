import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormRow } from "@/components/CrudPage";
import { Copy, KeyRound, ShieldOff } from "lucide-react";
import { toast } from "sonner";

const fmt = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

const MQTT_STEPS = (f) => [
  "Configuração MQTT › Habilitar = Sim; Endereço, Porta, ID Núvem (usuário) e Senha conforme o quadro acima",
  `ID Equipamento = ${f.beward_device_id || "<Device ID informado aqui>"} (é o DeviceID/facesluiceId e o client ID)`,
  "Tópico = tópico base do quadro acima (o facial completa com /<ID Equipamento>)",
  "Evento de Identificação = Enviar com Foto (sem isso os acessos não chegam)",
  "Retomar do ponto de interrupção = Habilitar (o servidor responde PushAck a cada evento)",
  `Entrada ou Saída = igual ao sentido do ponto de acesso (${f.point_direction || "entrada"})`,
  "Configuração Http › Verificação = Não inscrever (para não duplicar eventos)",
];
const HTTP_STEPS = [
  "Requer o pi-access-agent rodando num PC da mesma rede do facial (o facial só aceita IP + porta, sem domínio/HTTPS)",
  "Configuração MQTT › desmarcar Habilitar",
  "Configuração Http › servidor = IP do PC do agente, porta 5011, caminhos /Subscribe/Verify e /Subscribe/heartbeat",
  "Cartão RFID e Alarme são configurados automaticamente pelo agente (comando Subscribe)",
  "Gere o token do agente abaixo e cole no agent.json junto com o endereço do servidor e o IP do PC (advertise_ip)",
];

function BrokerInfo({ deviceId }) {
  const [d, setD] = useState(null);
  const [show, setShow] = useState(false);
  useEffect(() => { api.get("/integrations/mqtt/device-setup").then(({ data }) => setD(data)).catch(() => {}); }, []);
  if (!d) return null;
  const rows = [
    ["Broker", d.host || "—", "broker"], ["Porta", `${d.port}${d.tls ? " (TLS)" : ""}`, "port"],
    ["Usuário (ID Núvem)", d.username || "(anônimo)", "user"],
    ["Senha", d.password == null ? "(visível só para administrador)" : !d.password ? "(sem senha)" : show ? d.password : "••••••••", "password"],
    ["Tópico base", d.topic_base, "topic"], ["Tópico de comandos", `${d.topic_base}/${deviceId || "<ID>"}`, "cmd-topic"],
  ];
  return (
    <div className="mb-2 grid grid-cols-1 gap-1 rounded border border-border bg-background/40 p-2 font-mono text-[11px] sm:grid-cols-2" data-testid="beward-broker-info">
      {rows.map(([k, v, id]) => (
        <div key={id} className="flex gap-2"><span className="text-muted-foreground">{k}:</span><span className="break-all text-foreground" data-testid={`beward-setup-${id}`}>{v}</span>
          {id === "password" && d.password && <button type="button" className="text-sky-400" onClick={() => setShow(!show)} data-testid="beward-setup-show-password">{show ? "ocultar" : "mostrar"}</button>}
        </div>
      ))}
    </div>
  );
}

export function BewardSetupPanel({ form }) {
  const mqtt = form.transport === "mqtt";
  return (
    <div className="col-span-2 rounded-md border border-sky-500/30 bg-sky-500/5 p-3 text-xs" data-testid="beward-setup-panel">
      <p className="mb-2 font-semibold text-sky-300">Como configurar o facial — modo {mqtt ? "MQTT" : "HTTP local"} (MQTT e HTTP são exclusivos)</p>
      {mqtt && <BrokerInfo deviceId={form.beward_device_id} />}
      <ol className="list-decimal space-y-1 pl-4 text-muted-foreground">{(mqtt ? MQTT_STEPS(form) : HTTP_STEPS).map((s) => <li key={s}>{s}</li>)}</ol>
    </div>
  );
}

export function AgentTokenPanel({ siteId }) {
  const { hasRole } = useAuth();
  const [items, setItems] = useState([]);
  const [fresh, setFresh] = useState(null);
  const load = () => siteId && api.get(`/agents?site_id=${siteId}`).then(({ data }) => setItems(data)).catch(() => {});
  useEffect(() => { setFresh(null); load(); }, [siteId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!hasRole("admin")) return null;
  if (!siteId) return <p className="col-span-2 text-xs text-amber-300">Selecione o site para gerar o token do agente.</p>;
  const gen = async () => {
    if (items.length && !window.confirm("Gerar novo token revoga o atual deste site. Continuar?")) return;
    try { const { data } = await api.post("/agents", { site_id: siteId }); setFresh(data.token); load(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const revoke = async (id) => { if (!window.confirm("Revogar o token? O agente deixa de funcionar.")) return; await api.post(`/agents/${id}/revoke`); setFresh(null); load(); };
  const cur = items[0];
  return (
    <div className="col-span-2 rounded-md border border-border p-3" data-testid="agent-token-panel">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold"><KeyRound className="h-3.5 w-3.5 text-sky-400" />Token do agente local (por site)</p>
      {cur ? (
        <p className="mb-2 text-[11px] text-muted-foreground" data-testid="agent-token-info">
          <span className="font-mono text-foreground">{cur.prefix}…</span> · criado {fmt(cur.created_at)} · último uso {fmt(cur.last_used_at)} · IP {cur.last_ip || "—"}
        </p>
      ) : <p className="mb-2 text-[11px] text-muted-foreground">Nenhum token ativo.</p>}
      {fresh && (
        <FormRow label="Copie agora — o token completo não será exibido novamente">
          <div className="flex gap-2">
            <Input readOnly value={fresh} className="font-mono text-xs" data-testid="agent-token-value" />
            <Button type="button" size="icon" variant="outline" onClick={() => { navigator.clipboard?.writeText(fresh); toast.success("Token copiado"); }}><Copy className="h-4 w-4" /></Button>
          </div>
        </FormRow>
      )}
      <div className="mt-2 flex gap-2">
        <Button type="button" size="sm" variant="outline" onClick={gen} data-testid="agent-token-generate">Gerar novo</Button>
        {cur && <Button type="button" size="sm" variant="ghost" className="text-red-400" onClick={() => revoke(cur.id)} data-testid="agent-token-revoke"><ShieldOff className="mr-1 h-3.5 w-3.5" />Revogar</Button>}
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Executar no PC da rede: <span className="font-mono">python3 pi_access_agent.py agent.json</span> (arquivo em /agent do projeto).</p>
    </div>
  );
}

const DAYS = [[1, "Seg"], [2, "Ter"], [3, "Qua"], [4, "Qui"], [5, "Sex"], [6, "Sáb"], [7, "Dom"]];

export function NoEventAlertFields({ form, setForm, hours, setHours }) {
  const toggle = (d) => setHours((h) => ({ ...h, days: h.days.includes(d) ? h.days.filter((x) => x !== d) : [...h.days, d].sort() }));
  return (
    <div className="col-span-2 grid grid-cols-1 gap-3 rounded-md border border-border p-3 sm:grid-cols-2 [&>*]:min-w-0" data-testid="no-event-alert-fields">
      <FormRow label="Aviso sem eventos após (min)"><Input type="number" min={10} value={form.no_event_alert_minutes ?? 120} onChange={(e) => setForm((f) => ({ ...f, no_event_alert_minutes: +e.target.value }))} data-testid="controller-no-event-minutes" /></FormRow>
      <FormRow label="Horário de funcionamento do site">
        <div className="flex min-w-0 items-center gap-1 [&>input]:min-w-0">
          <Input type="time" value={hours.start} onChange={(e) => setHours((h) => ({ ...h, start: e.target.value }))} data-testid="site-hours-start" />
          <span className="text-xs">às</span>
          <Input type="time" value={hours.end} onChange={(e) => setHours((h) => ({ ...h, end: e.target.value }))} data-testid="site-hours-end" />
        </div>
      </FormRow>
      <div className="col-span-2 flex flex-wrap gap-1">
        {DAYS.map(([d, l]) => (
          <button key={d} type="button" onClick={() => toggle(d)} data-testid={`site-day-${d}`}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] ${hours.days.includes(d) ? "border-sky-500 bg-sky-500/15 text-sky-300" : "border-border text-muted-foreground"}`}>{l}</button>
        ))}
      </div>
      <p className="col-span-2 text-[11px] text-muted-foreground">Fora do horário de funcionamento não há aviso. Prioridade baixa, sem repetir até chegar novo evento.</p>
    </div>
  );
}
