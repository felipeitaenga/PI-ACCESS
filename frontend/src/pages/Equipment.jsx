import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, StatusDot } from "@/components/common";
import CrudPage, { FormRow } from "@/components/CrudPage";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Plus, Cpu, Wifi, RefreshCw, Pencil, Trash2, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const CTRL_EMPTY = { name: "", brand: "simulado", model: "", ip: "", port: 80, username: "admin", password: "", site_id: "", num_readers: 2, num_relays: 2, num_inputs: 2 };

export function Controllers() {
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");
  const [items, setItems] = useState([]);
  const [sites, setSites] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(CTRL_EMPTY);
  const [editId, setEditId] = useState(null);
  const [syncing, setSyncing] = useState(null);

  const load = async () => {
    const [c, s, j] = await Promise.all([api.get("/equipment/controllers?limit=100"), api.get("/structure/sites"), api.get("/equipment/sync-jobs")]);
    setItems(c.data.items); setSites(s.data); setJobs(j.data);
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      if (editId) await api.put(`/equipment/controllers/${editId}`, form);
      else await api.post("/equipment/controllers", form);
      toast.success("Controladora salva"); setOpen(false); setForm(CTRL_EMPTY); setEditId(null); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const test = async (id) => { const { data } = await api.post(`/equipment/controllers/${id}/test`); toast[data.ok ? "success" : "error"](data.ok ? "Comunicação OK" : "Sem comunicação"); load(); };
  const sync = async (id) => { setSyncing(id); try { const { data } = await api.post(`/equipment/controllers/${id}/sync`); toast.success(`Sincronizado: ${data.success}/${data.total} pessoas`); load(); } finally { setSyncing(null); } };
  const edit = (c) => { setForm({ ...CTRL_EMPTY, ...c, password: "" }); setEditId(c.id); setOpen(true); };
  const remove = async (id) => { if (!window.confirm("Excluir?")) return; await api.delete(`/equipment/controllers/${id}`); load(); };

  return (
    <div>
      <PageHeader title="Controladoras" subtitle="Equipamentos de controle · status por heartbeat">
        {canEdit && <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={() => { setForm(CTRL_EMPTY); setEditId(null); setOpen(true); }} data-testid="controller-add"><Plus className="mr-2 h-4 w-4" /> Nova controladora</Button>}
      </PageHeader>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((d) => (
          <Card key={d.id} className="border-border bg-card p-4" data-testid={`controller-card-${d.id}`}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><Cpu className="h-5 w-5" /></div>
                <div><div className="font-semibold">{d.name}</div><div className="text-xs text-muted-foreground capitalize">{d.brand} · {d.model}</div></div>
              </div>
              <div className="flex items-center gap-1.5 text-xs"><StatusDot online={d.online} /><span className={cn(d.online ? "text-emerald-400" : "text-slate-500")}>{d.online ? "Online" : "Offline"}</span></div>
            </div>
            <dl className="mt-3 space-y-1 text-xs text-muted-foreground">
              <div className="flex justify-between"><span>IP</span><span className="font-mono text-foreground">{d.ip}:{d.port}</span></div>
              <div className="flex justify-between"><span>Leitoras / Relés</span><span className="font-mono text-foreground">{d.num_readers} / {d.num_relays}</span></div>
              <div className="flex justify-between"><span>Firmware</span><span className="font-mono text-foreground">{d.firmware || "—"}</span></div>
            </dl>
            <div className="mt-4 flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => test(d.id)} data-testid={`controller-test-${d.id}`}><Wifi className="mr-1 h-3.5 w-3.5" /> Testar</Button>
              {canEdit && <Button variant="outline" size="sm" className="flex-1" disabled={syncing === d.id} onClick={() => sync(d.id)} data-testid={`controller-sync-${d.id}`}><RefreshCw className={cn("mr-1 h-3.5 w-3.5", syncing === d.id && "animate-spin")} /> Sincronizar</Button>}
              {canEdit && <Button variant="ghost" size="icon" onClick={() => edit(d)}><Pencil className="h-4 w-4" /></Button>}
              {hasRole("admin") && <Button variant="ghost" size="icon" className="text-red-400" onClick={() => remove(d.id)}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          </Card>
        ))}
      </div>
      {jobs.length > 0 && (
        <Card className="mt-6 border-border bg-card p-5">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Últimas sincronizações</h2>
          {jobs.slice(0, 6).map((j) => (
            <div key={j.id} className="flex items-center justify-between rounded-md border border-border/50 px-3 py-2 text-sm">
              <span className="font-medium">{j.device_name}</span>
              <span className="text-muted-foreground font-mono text-xs">TZ:{j.totals?.time_zones} Áreas:{j.totals?.areas} Pontos:{j.totals?.portals} Regras:{j.totals?.access_rules} Pessoas:{j.success}/{j.total}</span>
            </div>
          ))}
        </Card>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader><DialogTitle>{editId ? "Editar" : "Nova"} controladora</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <FormRow label="Nome" className="col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="controller-name" /></FormRow>
            <FormRow label="Marca / Driver">
              <Select value={form.brand} onValueChange={(v) => setForm({ ...form, brand: v })}>
                <SelectTrigger data-testid="controller-brand"><SelectValue /></SelectTrigger>
                <SelectContent>{["simulado", "beward_http", "beward_mqtt", "controlid", "hikvision", "intelbras", "zkteco"].map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
            <FormRow label="Modelo"><Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></FormRow>
            <FormRow label="IP"><Input value={form.ip} onChange={(e) => setForm({ ...form, ip: e.target.value })} data-testid="controller-ip" /></FormRow>
            <FormRow label="Porta"><Input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: +e.target.value })} /></FormRow>
            <FormRow label="Usuário"><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></FormRow>
            <FormRow label="Senha"><Input type="password" placeholder={editId ? "(inalterada)" : ""} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></FormRow>
            <FormRow label="Site">
              <Select value={form.site_id} onValueChange={(v) => setForm({ ...form, site_id: v })}>
                <SelectTrigger data-testid="controller-site"><SelectValue placeholder="Selecione" /></SelectTrigger>
                <SelectContent>{sites.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
            <FormRow label="Leitoras"><Input type="number" value={form.num_readers} onChange={(e) => setForm({ ...form, num_readers: +e.target.value })} /></FormRow>
            <FormRow label="Relés"><Input type="number" value={form.num_relays} onChange={(e) => setForm({ ...form, num_relays: +e.target.value })} /></FormRow>
            {String(form.brand).startsWith("beward") && (
              <>
                <FormRow label="Device ID / SN (Beward)"><Input value={form.beward_device_id || ""} onChange={(e) => setForm({ ...form, beward_device_id: e.target.value })} data-testid="controller-beward-id" /></FormRow>
                <FormRow label="Modo de decisão">
                  <Select value={form.decision_mode || "servidor"} onValueChange={(v) => setForm({ ...form, decision_mode: v })}>
                    <SelectTrigger data-testid="controller-decision-mode"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="servidor">Decisão no servidor (OpendoorWay=3)</SelectItem>
                      <SelectItem value="local">Decisão local (0)</SelectItem>
                      <SelectItem value="local_remoto">Local + remoto (2)</SelectItem>
                    </SelectContent>
                  </Select>
                </FormRow>
              </>
            )}
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Voltar</Button><Button className="bg-sky-500 text-slate-950" onClick={save} data-testid="controller-save">Salvar</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function AccessPoints() {
  const [ctrls, setCtrls] = useState([]);
  const [areas, setAreas] = useState([]);
  useEffect(() => {
    api.get("/equipment/controllers/all").then(({ data }) => setCtrls(data));
    api.get("/access/areas/all").then(({ data }) => setAreas(data));
  }, []);
  const sel = (val, set, options, ph, tid) => (
    <Select value={val || ""} onValueChange={set}>
      <SelectTrigger data-testid={tid}><SelectValue placeholder={ph} /></SelectTrigger>
      <SelectContent>{options.map((o) => <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>)}</SelectContent>
    </Select>
  );
  const renderForm = (form, setForm) => (
    <div className="grid grid-cols-2 gap-3">
      <FormRow label="Descrição" className="col-span-2"><Input value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="ap-desc" /></FormRow>
      <FormRow label="Controladora">{sel(form.controller_id, (v) => setForm({ ...form, controller_id: v }), ctrls.map((c) => ({ id: c.id, label: c.name })), "Controladora", "ap-controller")}</FormRow>
      <FormRow label="Tipo">{sel(form.type, (v) => setForm({ ...form, type: v }), [{ id: "porta", label: "Porta" }, { id: "catraca", label: "Catraca" }, { id: "cancela", label: "Cancela" }, { id: "torniquete", label: "Torniquete" }, { id: "facial", label: "Facial" }], "Tipo", "ap-type")}</FormRow>
      <FormRow label="Leitora nº"><Input type="number" value={form.reader || 1} onChange={(e) => setForm({ ...form, reader: +e.target.value })} /></FormRow>
      <FormRow label="Relé nº"><Input type="number" value={form.relay || 1} onChange={(e) => setForm({ ...form, relay: +e.target.value })} /></FormRow>
      <FormRow label="Área de ORIGEM">{sel(form.origin_area_id, (v) => setForm({ ...form, origin_area_id: v }), areas.map((a) => ({ id: a.id, label: a.description })), "Origem", "ap-origin")}</FormRow>
      <FormRow label="Área de DESTINO">{sel(form.dest_area_id, (v) => setForm({ ...form, dest_area_id: v }), areas.map((a) => ({ id: a.id, label: a.description })), "Destino", "ap-dest")}</FormRow>
      <FormRow label="Sentido">{sel(form.direction, (v) => setForm({ ...form, direction: v }), [{ id: "entrada", label: "Entrada" }, { id: "saida", label: "Saída" }], "Sentido", "ap-direction")}</FormRow>
      <FormRow label="Tempo de relé (s)"><Input type="number" value={form.relay_time || 5} onChange={(e) => setForm({ ...form, relay_time: +e.target.value })} /></FormRow>
      <FormRow label="Tempo porta aberta (s)"><Input type="number" value={form.door_open_time || 20} onChange={(e) => setForm({ ...form, door_open_time: +e.target.value })} /></FormRow>
    </div>
  );
  return (
    <CrudPage title="Pontos de acesso" subtitle="Leitora + relé + sentido origem → destino" endpoint="/equipment/access-points"
      defaultForm={{ description: "", type: "porta", reader: 1, relay: 1, direction: "entrada", relay_time: 5, door_open_time: 20 }}
      renderForm={renderForm}
      columns={[
        { key: "description", label: "Ponto", render: (r) => <span className="font-medium">{r.description}</span> },
        { key: "controller_name", label: "Controladora" },
        { label: "Fluxo", render: (r) => <span className="flex items-center gap-1 text-xs"><Badge variant="outline">{r.origin_area_name}</Badge><ArrowRight className="h-3 w-3 text-sky-400" /><Badge variant="outline" className="bg-sky-500/10 text-sky-400 border-sky-500/30">{r.dest_area_name}</Badge></span> },
        { label: "Sentido", render: (r) => <span className="capitalize">{r.direction}</span> },
        { key: "type", label: "Tipo", render: (r) => <span className="capitalize">{r.type}</span> },
      ]} />
  );
}
