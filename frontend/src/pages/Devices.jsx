import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, StatusDot } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Cpu, RefreshCw, Wifi, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const EMPTY = {
  name: "", brand: "simulado", model: "", ip: "", port: 80, username: "admin",
  password: "", connection_mode: "direct", reader_type: "entrada",
  site_id: "", area_id: "", door_id: "",
};

export default function Devices() {
  const { hasRole } = useAuth();
  const [devices, setDevices] = useState([]);
  const [brands, setBrands] = useState([]);
  const [sites, setSites] = useState([]);
  const [areas, setAreas] = useState([]);
  const [doors, setDoors] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [syncing, setSyncing] = useState(null);

  const load = async () => {
    const [d, b, s, j] = await Promise.all([
      api.get("/devices"), api.get("/devices/brands"),
      api.get("/structure/sites"), api.get("/devices/sync-jobs/list"),
    ]);
    setDevices(d.data); setBrands(b.data); setSites(s.data); setJobs(j.data);
    const [ar, dr] = await Promise.all([api.get("/structure/areas"), api.get("/structure/doors")]);
    setAreas(ar.data); setDoors(dr.data);
  };
  useEffect(() => { load(); }, []);

  const canEdit = hasRole("admin", "operator");

  const save = async () => {
    try {
      if (editId) await api.put(`/devices/${editId}`, form);
      else await api.post("/devices", form);
      toast.success(editId ? "Dispositivo atualizado" : "Dispositivo cadastrado");
      setOpen(false); setForm(EMPTY); setEditId(null); load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const test = async (id) => {
    try {
      const { data } = await api.post(`/devices/${id}/test`);
      toast[data.ok ? "success" : "error"](data.ok ? "Comunicação OK" : "Sem comunicação");
      load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const sync = async (id) => {
    setSyncing(id);
    try {
      const { data } = await api.post(`/devices/${id}/sync`);
      toast.success(`Sincronizado: ${data.success}/${data.total} pessoas`);
      load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
    finally { setSyncing(null); }
  };

  const edit = (d) => { setForm({ ...EMPTY, ...d, password: "" }); setEditId(d.id); setOpen(true); };
  const remove = async (id) => { if (!window.confirm("Excluir dispositivo?")) return; await api.delete(`/devices/${id}`); toast.success("Excluído"); load(); };

  return (
    <div>
      <PageHeader title="Dispositivos" subtitle="Leitoras e controladoras · status via heartbeat">
        {canEdit && (
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setForm(EMPTY); setEditId(null); } }}>
            <DialogTrigger asChild>
              <Button className="bg-sky-500 hover:bg-sky-600 text-white" data-testid="device-add-button">
                <Plus className="mr-2 h-4 w-4" /> Novo dispositivo
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl">
              <DialogHeader><DialogTitle>{editId ? "Editar dispositivo" : "Novo dispositivo"}</DialogTitle></DialogHeader>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Nome" className="col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="device-name-input" /></Field>
                <Field label="Marca">
                  <Select value={form.brand} onValueChange={(v) => setForm({ ...form, brand: v })}>
                    <SelectTrigger data-testid="device-brand-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{brands.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}</SelectContent>
                  </Select>
                </Field>
                <Field label="Modelo"><Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></Field>
                <Field label="IP"><Input value={form.ip} onChange={(e) => setForm({ ...form, ip: e.target.value })} data-testid="device-ip-input" /></Field>
                <Field label="Porta"><Input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: +e.target.value })} /></Field>
                <Field label="Usuário"><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>
                <Field label="Senha"><Input type="password" placeholder={editId ? "(inalterada)" : ""} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
                <Field label="Modo conexão">
                  <Select value={form.connection_mode} onValueChange={(v) => setForm({ ...form, connection_mode: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="direct">Acesso direto</SelectItem><SelectItem value="agent">Via agente edge</SelectItem></SelectContent>
                  </Select>
                </Field>
                <Field label="Tipo leitora">
                  <Select value={form.reader_type} onValueChange={(v) => setForm({ ...form, reader_type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="entrada">Entrada</SelectItem><SelectItem value="saida">Saída</SelectItem></SelectContent>
                  </Select>
                </Field>
                <Field label="Site">
                  <Select value={form.site_id} onValueChange={(v) => setForm({ ...form, site_id: v })}>
                    <SelectTrigger data-testid="device-site-select"><SelectValue placeholder="Selecione" /></SelectTrigger>
                    <SelectContent>{sites.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
                  </Select>
                </Field>
                <Field label="Porta/Ponto">
                  <Select value={form.door_id} onValueChange={(v) => setForm({ ...form, door_id: v })}>
                    <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                    <SelectContent>{doors.filter((d) => !form.site_id || d.site_id === form.site_id).map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent>
                  </Select>
                </Field>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
                <Button className="bg-sky-500 hover:bg-sky-600 text-white" onClick={save} data-testid="device-save-button">Salvar</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {devices.map((d) => (
          <Card key={d.id} className="border-border bg-card p-4" data-testid={`device-card-${d.id}`}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><Cpu className="h-5 w-5" /></div>
                <div>
                  <div className="font-semibold">{d.name}</div>
                  <div className="text-xs text-muted-foreground capitalize">{d.brand} · {d.model || "—"}</div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-xs" data-testid="device-status-filter">
                <StatusDot online={d.online} /><span className={cn(d.online ? "text-emerald-400" : "text-slate-500")}>{d.online ? "Online" : "Offline"}</span>
              </div>
            </div>
            <dl className="mt-3 space-y-1 text-xs text-muted-foreground">
              <div className="flex justify-between"><span>IP</span><span className="font-mono text-foreground">{d.ip}:{d.port}</span></div>
              <div className="flex justify-between"><span>Conexão</span><span className="text-foreground">{d.connection_mode === "agent" ? "Via agente" : "Direto"}</span></div>
              <div className="flex justify-between"><span>Firmware</span><span className="font-mono text-foreground">{d.firmware || "—"}</span></div>
            </dl>
            <div className="mt-4 flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={() => test(d.id)} data-testid={`device-test-${d.id}`}><Wifi className="mr-1 h-3.5 w-3.5" /> Testar</Button>
              {canEdit && <Button variant="outline" size="sm" className="flex-1" disabled={syncing === d.id} onClick={() => sync(d.id)} data-testid={`device-sync-${d.id}`}><RefreshCw className={cn("mr-1 h-3.5 w-3.5", syncing === d.id && "animate-spin")} /> Sincronizar</Button>}
              {canEdit && <Button variant="ghost" size="icon" onClick={() => edit(d)}><Pencil className="h-4 w-4" /></Button>}
              {hasRole("admin") && <Button variant="ghost" size="icon" className="text-red-400" onClick={() => remove(d.id)}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          </Card>
        ))}
      </div>

      {jobs.length > 0 && (
        <Card className="mt-6 border-border bg-card p-5">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Log de sincronização</h2>
          <div className="space-y-2">
            {jobs.slice(0, 8).map((j) => (
              <div key={j.id} className="flex items-center justify-between rounded-md border border-border/50 px-3 py-2 text-sm">
                <span className="font-medium">{j.device_name}</span>
                <span className="text-muted-foreground">{j.success}/{j.total} pessoas · {j.errors?.length || 0} erros</span>
                <span className="text-xs font-mono text-muted-foreground">{new Date(j.started_at).toLocaleString("pt-BR")}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Field({ label, children, className }) {
  return <div className={className}><Label className="mb-1.5 block text-xs text-muted-foreground">{label}</Label>{children}</div>;
}
