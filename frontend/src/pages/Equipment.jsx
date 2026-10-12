import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, StatusDot } from "@/components/common";
import { ControllerDialog, MODELS } from "@/components/equipment/ControllerDialog";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, Cpu, Wifi, RefreshCw, Pencil, Trash2, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const ago = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

function BewardHealth({ d }) {
  if (d.model_type !== "beward_facial") return null;
  return (
    <div className="mt-2 space-y-1 text-[11px]" data-testid={`beward-health-${d.id}`}>
      <div className="flex justify-between text-muted-foreground"><span>Modo</span><span className="font-mono text-foreground">{d.brand === "beward_mqtt" ? "MQTT" : "HTTP local (agente)"} · ID {d.beward_device_id || "—"}</span></div>
      <div className="flex justify-between text-muted-foreground"><span>Último heartbeat</span><span className="font-mono text-foreground">{ago(d.last_heartbeat)}</span></div>
      <div className="flex justify-between text-muted-foreground"><span>Último evento</span><span className="font-mono text-foreground">{ago(d.last_event_at)}</span></div>
      {d.no_event_alerted && <p className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-300" data-testid={`beward-no-event-${d.id}`}>Facial online sem eventos de acesso: verifique &apos;Evento de Identificação = enviar com imagem&apos; no painel do equipamento.</p>}
      {d.direction_mismatch && <p className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-300" data-testid={`beward-direction-${d.id}`}>Sentido divergente: facial envia {d.direction_mismatch.device?.toUpperCase()} e o ponto está como {d.direction_mismatch.point?.toUpperCase()}.</p>}
    </div>
  );
}

function ControllerCard({ d, points, canEdit, isAdmin, syncing, onTest, onSync, onEdit, onRemove }) {
  return (
    <Card className="border-border bg-card p-4" data-testid={`controller-card-${d.id}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><Cpu className="h-5 w-5" /></div>
          <div><div className="font-semibold">{d.name}</div><div className="text-xs text-muted-foreground" data-testid={`controller-model-${d.id}`}>{MODELS[d.model_type]?.label || d.model}</div></div>
        </div>
        <div className="flex items-center gap-1.5 text-xs"><StatusDot online={d.online} /><span className={cn(d.online ? "text-emerald-400" : "text-slate-500")}>{d.online ? "Online" : "Offline"}</span></div>
      </div>
      <dl className="mt-3 space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between"><span>IP</span><span className="font-mono text-foreground">{d.ip}:{d.port}</span></div>
        <div className="flex justify-between"><span>Pontos de acesso</span><span className="font-mono text-foreground" data-testid={`controller-points-count-${d.id}`}>{d.num_access_points ?? points.length}</span></div>
        <div className="flex justify-between"><span>Firmware</span><span className="font-mono text-foreground">{d.firmware || "—"}</span></div>
      </dl>
      <BewardHealth d={d} />
      <div className="mt-3 space-y-1">
        {points.map((p) => (
          <div key={p.id} className="flex items-center gap-1.5 rounded border border-border/60 px-2 py-1 text-[11px]" data-testid={`controller-point-${p.id}`}>
            <span className="font-mono text-sky-300">P{p.reader}</span><span className="flex-1 truncate">{p.description}</span>
            <span className="hidden items-center gap-1 text-muted-foreground sm:flex">{p.origin_area_name}<ArrowRight className="h-3 w-3" />{p.dest_area_name}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 flex gap-2">
        <Button variant="outline" size="sm" className="flex-1" onClick={onTest} data-testid={`controller-test-${d.id}`}><Wifi className="mr-1 h-3.5 w-3.5" /> Testar</Button>
        {canEdit && <Button variant="outline" size="sm" className="flex-1" disabled={syncing} onClick={onSync} data-testid={`controller-sync-${d.id}`}><RefreshCw className={cn("mr-1 h-3.5 w-3.5", syncing && "animate-spin")} /> Sincronizar</Button>}
        {canEdit && <Button variant="ghost" size="icon" onClick={onEdit} data-testid={`controller-edit-${d.id}`}><Pencil className="h-4 w-4" /></Button>}
        {isAdmin && <Button variant="ghost" size="icon" className="text-red-400" onClick={onRemove} data-testid={`controller-delete-${d.id}`}><Trash2 className="h-4 w-4" /></Button>}
      </div>
    </Card>
  );
}

export function Controllers() {
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");
  const [items, setItems] = useState([]);
  const [points, setPoints] = useState([]);
  const [sites, setSites] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [dlg, setDlg] = useState({ open: false, initial: null });
  const [syncing, setSyncing] = useState(null);

  const load = async () => {
    const [c, s, j, p] = await Promise.all([api.get("/equipment/controllers?limit=100"), api.get("/structure/sites"), api.get("/equipment/sync-jobs"), api.get("/equipment/access-points/all")]);
    setItems(c.data.items); setSites(s.data); setJobs(j.data); setPoints(p.data);
  };
  useEffect(() => { load(); }, []);

  const test = async (id) => { const { data } = await api.post(`/equipment/controllers/${id}/test`); toast[data.ok ? "success" : "error"](data.ok ? `Comunicação OK${data.clock ? (data.clock.ok ? " · data/hora do facial ajustada" : " · não foi possível ajustar a data/hora") : ""}` : (data.status?.error || "Sem comunicação")); load(); };
  const sync = async (id) => { setSyncing(id); try { const { data } = await api.post(`/equipment/controllers/${id}/sync`); toast.success(`Sincronizado: ${data.success}/${data.total} pessoas`); load(); } finally { setSyncing(null); } };
  const remove = async (id) => { if (!window.confirm("Excluir a controladora?")) return; await api.delete(`/equipment/controllers/${id}`); load(); };

  return (
    <div>
      <PageHeader title="Controladoras" subtitle="Equipamentos e seus pontos de acesso (1 leitora + 1 relé por ponto)">
        {canEdit && <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={() => setDlg({ open: true, initial: null })} data-testid="controller-add"><Plus className="mr-2 h-4 w-4" /> Nova controladora</Button>}
      </PageHeader>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((d) => (
          <ControllerCard key={d.id} d={d} points={points.filter((p) => p.controller_id === d.id).sort((a, b) => a.reader - b.reader)}
            canEdit={canEdit} isAdmin={hasRole("admin")} syncing={syncing === d.id}
            onTest={() => test(d.id)} onSync={() => sync(d.id)} onEdit={() => setDlg({ open: true, initial: d })} onRemove={() => remove(d.id)} />
        ))}
      </div>
      {jobs.length > 0 && (
        <Card className="mt-6 border-border bg-card p-5">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Últimas sincronizações</h2>
          {jobs.slice(0, 6).map((j) => (
            <div key={j.id} className="flex items-center justify-between rounded-md border border-border/50 px-3 py-2 text-sm">
              <span className="font-medium">{j.device_name}</span>
              <span className="text-muted-foreground font-mono text-xs">TZ:{j.totals?.time_zones ?? "-"} Áreas:{j.totals?.areas ?? "-"} Pontos:{j.totals?.portals ?? "-"} Regras:{j.totals?.access_rules ?? "-"} Pessoas:{j.success}/{j.total}</span>
            </div>
          ))}
        </Card>
      )}
      <ControllerDialog open={dlg.open} initial={dlg.initial} sites={sites} onOpenChange={(o) => setDlg((s) => ({ ...s, open: o }))} onSaved={load} />
    </div>
  );
}
