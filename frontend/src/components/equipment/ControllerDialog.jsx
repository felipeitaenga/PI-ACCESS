import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { FormRow } from "@/components/CrudPage";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRight, DoorOpen } from "lucide-react";
import { AgentTokenPanel, BewardSetupPanel, NoEventAlertFields } from "@/components/equipment/BewardPanels";
import { toast } from "sonner";

export const MODELS = {
  simulado: { label: "Simulado (demonstração)", max: 8, point_type: "catraca" },
  beward_facial: { label: "Facial Beward", max: 1, point_type: "facial" },
  hikvision_facial: { label: "Facial Hikvision", max: 1, point_type: "facial", pending: true },
  controlid_facial: { label: "Facial Control iD", max: 1, point_type: "facial", pending: true },
  intelbras_facial: { label: "Facial Intelbras", max: 1, point_type: "facial", pending: true },
  ct300_2l: { label: "CT300-2L", max: 2, point_type: "catraca", pending: true },
};
const POINT_TYPES = [["porta", "Porta"], ["catraca", "Catraca"], ["cancela", "Cancela"], ["torniquete", "Torniquete"], ["facial", "Facial"]];
const EMPTY = { name: "", manufacturer: "beward", catalog_model: "beward_face", model_type: "beward_facial", transport: "http", ip: "", port: 80, username: "admin", password: "", site_id: "", num_access_points: 1 };

const sel = (value, onChange, options, ph, testid) => (
  <Select value={value || ""} onValueChange={onChange}>
    <SelectTrigger data-testid={testid}><SelectValue placeholder={ph} /></SelectTrigger>
    <SelectContent>{options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
  </Select>
);

const newPoint = (form, i) => ({ description: `${form.name || "Controladora"} - Ponto ${i + 1}`, type: (MODELS[form.model_type] || MODELS.simulado).point_type, direction: i % 2 ? "saida" : "entrada", relay_time: 5, door_open_time: 20 });

function PointCard({ p, i, areas, onChange }) {
  const set = (k) => (v) => onChange({ ...p, [k]: v });
  const areaOpts = areas.map((a) => [a.id, a.description]);
  return (
    <div className="rounded-lg border border-border bg-secondary/20 p-3" data-testid={`ap-card-${i}`}>
      <div className="mb-2 flex items-center gap-2">
        <DoorOpen className="h-4 w-4 text-sky-400" />
        <span className="text-sm font-semibold">Ponto {i + 1}</span>
        <Badge variant="outline" className="font-mono text-[10px]" data-testid={`ap-io-${i}`}>Leitora {i + 1} · Relé {i + 1}</Badge>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <FormRow label="Descrição" className="col-span-2"><Input value={p.description || ""} onChange={(e) => set("description")(e.target.value)} data-testid={`ap-desc-${i}`} /></FormRow>
        <FormRow label="Tipo">{sel(p.type, set("type"), POINT_TYPES, "Tipo", `ap-type-${i}`)}</FormRow>
        <FormRow label="Sentido">{sel(p.direction, set("direction"), [["entrada", "Entrada"], ["saida", "Saída"]], "Sentido", `ap-direction-${i}`)}</FormRow>
        <FormRow label="Área de ORIGEM">{sel(p.origin_area_id, set("origin_area_id"), areaOpts, "Origem", `ap-origin-${i}`)}</FormRow>
        <FormRow label="Área de DESTINO">{sel(p.dest_area_id, set("dest_area_id"), areaOpts, "Destino", `ap-dest-${i}`)}</FormRow>
        <FormRow label="Tempo de relé (s)"><Input type="number" value={p.relay_time ?? 5} onChange={(e) => set("relay_time")(+e.target.value)} data-testid={`ap-relay-time-${i}`} /></FormRow>
        <FormRow label="Tempo porta aberta (s)"><Input type="number" value={p.door_open_time ?? 20} onChange={(e) => set("door_open_time")(+e.target.value)} data-testid={`ap-open-time-${i}`} /></FormRow>
      </div>
      {p.origin_area_id && p.dest_area_id && (
        <p className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground">
          {areas.find((a) => a.id === p.origin_area_id)?.description}<ArrowRight className="h-3 w-3 text-sky-400" />{areas.find((a) => a.id === p.dest_area_id)?.description}
        </p>
      )}
    </div>
  );
}

export const STATUS = {
  homologado: ["Homologado", "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"],
  em_teste: ["Em teste", "border-amber-500/40 bg-amber-500/10 text-amber-300"],
  em_breve: ["Em breve", "border-slate-500/40 bg-slate-500/10 text-slate-400"],
};
const yes = (b) => (b ? "✔" : "✘");

export function ModelCard({ cm, manName }) {
  if (!cm) return null;
  const [st, cls] = STATUS[cm.status] || STATUS.em_breve;
  const f = cm.features || {};
  return (
    <div className="col-span-2 rounded-lg border border-border bg-secondary/20 p-3 text-xs" data-testid="controller-model-card">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{manName} {cm.name}</span>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`} data-testid="controller-model-status">● {st}</span>
      </div>
      <div className="grid grid-cols-1 gap-x-4 gap-y-1 text-muted-foreground sm:grid-cols-2">
        <span>Comunicação: <b className="text-foreground">{cm.protocol}</b></span>
        <span>Face {yes(f.face)} · Cartão {yes(f.card)} · Digital {yes(f.finger)} · QR {yes(f.qrcode)}</span>
        <span>Servidor decide (anti-dupla, horário): <b className="text-foreground">{yes(cm.online_mode)}</b>{cm.min_firmware ? ` · firmware ≥ ${cm.min_firmware}` : ""}</span>
        <span>Mensagem na tela pelo servidor: <b className="text-foreground">{yes(cm.screen_message)}</b> · Pontos: {cm.max_points}</span>
      </div>
      {cm.notes && <p className="mt-2 text-muted-foreground">{cm.notes}</p>}
      {cm.status === "em_breve" && <p className="mt-2 text-amber-300" data-testid="controller-model-soon">Integração deste modelo ainda não disponível — não é possível salvar.</p>}
    </div>
  );
}

function GeneralTab({ form, setForm, sites, editId, hours, setHours, pointDirection, cat }) {
  const m = MODELS[form.model_type] || MODELS.simulado;
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const models = cat.models.filter((x) => x.manufacturer === form.manufacturer);
  const cm = cat.models.find((x) => x.id === form.catalog_model);
  const manName = cat.manufacturers.find((x) => x.id === form.manufacturer)?.name || "";
  const pick = (id) => {
    const x = cat.models.find((y) => y.id === id);
    if (!x) return;
    setForm((f) => ({ ...f, catalog_model: x.id, model_type: x.family,
      num_access_points: Math.min(f.num_access_points || 1, x.max_points, (MODELS[x.family] || MODELS.simulado).max) }));
  };
  const setMan = (v) => {
    const first = cat.models.find((y) => y.manufacturer === v && y.status !== "em_breve") || cat.models.find((y) => y.manufacturer === v);
    setForm((f) => ({ ...f, manufacturer: v }));
    if (first) pick(first.id);
  };
  return (
    <div className="grid grid-cols-2 gap-3">
      <FormRow label="Nome" className="col-span-2"><Input value={form.name} onChange={(e) => set("name")(e.target.value)} data-testid="controller-name" /></FormRow>
      <FormRow label="Fabricante">{sel(form.manufacturer, setMan, cat.manufacturers.map((x) => [x.id, x.name]), "Fabricante", "controller-manufacturer")}</FormRow>
      <FormRow label="Modelo">{sel(form.catalog_model, pick, models.map((x) => [x.id, `${x.name}${x.status === "em_breve" ? " (em breve)" : x.status === "em_teste" ? " (em teste)" : ""}`]), "Modelo", "controller-model-type")}</FormRow>
      <ModelCard cm={cm} manName={manName} />
      <FormRow label="Quantidade de pontos de acesso">
        {m.max === 1 ? <Input value="1 (fixo)" disabled data-testid="controller-num-points" /> :
          sel(String(form.num_access_points), (v) => set("num_access_points")(+v), Array.from({ length: m.max }, (_, i) => [String(i + 1), String(i + 1)]), "Qtd.", "controller-num-points")}
      </FormRow>
      <FormRow label="IP"><Input value={form.ip} onChange={(e) => set("ip")(e.target.value)} data-testid="controller-ip" /></FormRow>
      <FormRow label="Porta"><Input type="number" value={form.port} onChange={(e) => set("port")(+e.target.value)} data-testid="controller-port" /></FormRow>
      <FormRow label="Usuário"><Input value={form.username} onChange={(e) => set("username")(e.target.value)} /></FormRow>
      <FormRow label="Senha"><Input type="password" placeholder={editId ? "(inalterada)" : ""} value={form.password} onChange={(e) => set("password")(e.target.value)} /></FormRow>
      <FormRow label="Site" className="col-span-2">{sel(form.site_id, set("site_id"), sites.map((s) => [s.id, s.name]), "Selecione", "controller-site")}</FormRow>
      {form.model_type === "beward_facial" && (
        <>
          <FormRow label="Protocolo (exclusivo)">{sel(form.transport || "http", set("transport"), [["mqtt", "MQTT (broker)"], ["http", "HTTP local (via agente)"]], "Protocolo", "controller-transport")}</FormRow>
          <FormRow label="ID Equipamento (DeviceID)"><Input value={form.beward_device_id || ""} onChange={(e) => set("beward_device_id")(e.target.value)} data-testid="controller-beward-id" /></FormRow>
          <FormRow label="Quem decide o acesso" className="col-span-2">
            {sel(form.decision_mode || "servidor", set("decision_mode"), [
              ["servidor", "Servidor decide — facial em “Verificação local Aberta à distância”"],
              ["local", "Facial decide — modo “Face”"],
              ["local_remoto", "Facial ou servidor — “Face e/ou Remota”"]], "Modo", "controller-decision-mode")}
            <p className="mt-1 text-xs text-muted-foreground" data-testid="controller-decision-hint">
              Deve ser igual ao “Modo de Liberação” configurado no painel do facial.
              {(form.decision_mode || "servidor") !== "servidor" && " Neste modo anti-dupla entrada, controle de origem e reentrada temporizada não funcionam."}
            </p>
          </FormRow>
          <NoEventAlertFields form={form} setForm={setForm} hours={hours} setHours={setHours} />
          <BewardSetupPanel form={{ ...form, point_direction: pointDirection }} />
          {form.transport !== "mqtt" && <AgentTokenPanel siteId={form.site_id} />}
        </>
      )}
    </div>
  );
}

export function ControllerDialog({ open, onOpenChange, initial, sites, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [points, setPoints] = useState([]);
  const [areas, setAreas] = useState([]);
  const [hours, setHours] = useState({ days: [1, 2, 3, 4, 5], start: "07:00", end: "19:00" });
  const [cat, setCat] = useState({ manufacturers: [], models: [] });
  const editId = initial?.id;
  useEffect(() => { if (open && !cat.models.length) api.get("/equipment/catalog").then(({ data }) => setCat(data)).catch(() => {}); }, [open]); // eslint-disable-line
  // cadastro antigo (só model_type): usa o modelo padrão daquela família
  useEffect(() => {
    if (!cat.models.length || cat.models.some((x) => x.id === form.catalog_model)) return;
    const x = cat.models.find((y) => y.family === form.model_type && y.status !== "em_breve") || cat.models.find((y) => y.family === form.model_type);
    if (x) setForm((f) => ({ ...f, catalog_model: x.id, manufacturer: x.manufacturer }));
  }, [cat, form.catalog_model, form.model_type]);

  useEffect(() => {
    if (!open) return;
    api.get("/access/areas/all").then(({ data }) => setAreas(data)).catch(() => {});
    if (initial) {
      setForm({ ...EMPTY, catalog_model: "", manufacturer: "", ...initial, password: "", model_type: MODELS[initial.model_type] ? initial.model_type : "simulado", transport: initial.brand === "beward_mqtt" ? "mqtt" : "http" });
      api.get(`/equipment/controllers/${initial.id}/access-points`).then(({ data }) => setPoints(data)).catch(() => setPoints([]));
    } else { setForm(EMPTY); setPoints([]); }
  }, [open, initial]);

  useEffect(() => {
    const s = sites.find((x) => x.id === form.site_id);
    setHours(s?.business_hours || { days: [1, 2, 3, 4, 5], start: "07:00", end: "19:00" });
  }, [form.site_id, sites]);

  const n = Math.min(form.num_access_points || 1, (MODELS[form.model_type] || MODELS.simulado).max);
  const soon = cat.models.find((x) => x.id === form.catalog_model)?.status === "em_breve";
  const shown = Array.from({ length: n }, (_, i) => points[i] || newPoint(form, i));

  const save = async () => {
    if (!form.name.trim()) { toast.error("Informe o nome da controladora"); return; }
    if (soon) { toast.error("Integração deste modelo ainda não disponível"); return; }
    const body = { ...form, num_access_points: n, access_points: shown };
    try {
      if (editId) await api.put(`/equipment/controllers/${editId}`, body);
      else await api.post("/equipment/controllers", body);
      if (form.model_type === "beward_facial" && form.site_id) await api.put(`/structure/sites/${form.site_id}/business-hours`, hours);
      toast.success(`Controladora salva com ${n} ponto(s) de acesso`);
      onOpenChange(false); onSaved();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl sm:max-h-[90vh]" data-testid="controller-dialog">
        <DialogHeader><DialogTitle>{editId ? "Editar" : "Nova"} controladora</DialogTitle><DialogDescription>Cada ponto de acesso usa 1 leitora + 1 relé da controladora.</DialogDescription></DialogHeader>
        <Tabs defaultValue="general">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="general" data-testid="controller-tab-general">Dados gerais</TabsTrigger>
            <TabsTrigger value="points" data-testid="controller-tab-points">Pontos de acesso ({n})</TabsTrigger>
          </TabsList>
          <TabsContent value="general" className="pt-3"><GeneralTab form={form} setForm={setForm} sites={sites} editId={editId} hours={hours} setHours={setHours} pointDirection={shown[0]?.direction} cat={cat} /></TabsContent>
          <TabsContent value="points" className="space-y-3 pt-3">
            {shown.map((p, i) => <PointCard key={p.id || i} p={p} i={i} areas={areas} onChange={(np) => setPoints(() => { const c = [...shown]; c[i] = np; return c; })} />)}
          </TabsContent>
        </Tabs>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Voltar</Button><Button className="bg-sky-500 text-white" onClick={save} disabled={soon} data-testid="controller-save">Salvar</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
