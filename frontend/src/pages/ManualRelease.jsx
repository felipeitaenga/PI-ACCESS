import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { useRealtime } from "@/context/RealtimeContext";
import { ManualReleaseDialog } from "@/components/access/ManualReleaseDialog";
import { ArrowRight, DoorOpen, Search, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";

const TYPE = { porta: "Porta", catraca: "Catraca", cancela: "Cancela", torniquete: "Torniquete", facial: "Facial" };
const fmt = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export default function ManualRelease() {
  const { hasRole } = useAuth();
  const { subscribe } = useRealtime();
  const [points, setPoints] = useState([]);
  const [ctrls, setCtrls] = useState({});
  const [recent, setRecent] = useState([]);
  const [q, setQ] = useState("");
  const [point, setPoint] = useState(null);
  const can = hasRole("admin", "operator", "reception");

  const loadRecent = useCallback(() => api.get("/events?manual=true&limit=20").then(({ data }) => setRecent(data.items || [])).catch(() => {}), []);
  useEffect(() => {
    api.get("/equipment/access-points/all").then(({ data }) => setPoints(data)).catch(() => {});
    api.get("/equipment/controllers/all").then(({ data }) => setCtrls(Object.fromEntries(data.map((c) => [c.id, c])))).catch(() => {});
    loadRecent();
    return subscribe((m) => { if (m.type === "access_event" && m.data?.manual) setRecent((r) => [m.data, ...r].slice(0, 20)); });
  }, [loadRecent, subscribe]);

  const shown = points.filter((p) => !q || `${p.description} ${p.controller_name} ${p.site_name}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-4" data-testid="page-manual-release">
      <PageHeader title="Liberação manual" subtitle="Abre qualquer ponto de bloqueio com motivo e registro do operador" />
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar ponto…" data-testid="manual-points-search" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((p) => {
          const c = ctrls[p.controller_id] || {};
          return (
            <Card key={p.id} className="flex flex-col gap-2 border-border bg-card p-4" data-testid={`manual-point-${p.id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{p.description}</p>
                  <p className="truncate text-xs text-muted-foreground">{TYPE[p.type] || p.type} · {p.direction === "saida" ? "Saída" : "Entrada"}{p.passage_mode === "confirmacao" ? " · confirma giro" : ""}</p>
                </div>
                <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[10px]", c.online ? "border-emerald-500/40 text-emerald-400" : "border-slate-500/40 text-slate-400")}>● {c.online ? "online" : "offline"}</span>
              </div>
              <p className="flex items-center gap-1 truncate text-[11px] text-muted-foreground">{p.origin_area_name || "—"}<ArrowRight className="h-3 w-3" />{p.dest_area_name || "—"} · {p.controller_name}</p>
              <Button className="mt-auto bg-amber-500 text-black hover:bg-amber-400" disabled={!can} onClick={() => setPoint(p)} data-testid={`manual-point-release-${p.id}`}>
                <DoorOpen className="mr-2 h-4 w-4" />Liberar
              </Button>
            </Card>
          );
        })}
        {shown.length === 0 && <p className="text-sm text-muted-foreground">Nenhum ponto de acesso cadastrado.</p>}
      </div>

      <Card className="border-border bg-card" data-testid="manual-recent">
        <h2 className="border-b border-border px-4 py-3 font-heading text-sm font-bold uppercase tracking-widest">Últimas liberações manuais</h2>
        {recent.length === 0 && <p className="p-4 text-sm text-muted-foreground">Nenhuma ainda.</p>}
        {recent.map((e) => (
          <div key={e.id} className="flex items-center gap-3 border-b border-border/50 px-4 py-2.5 text-sm">
            {e.captured_photo || e.person_photo ? <img src={e.captured_photo || e.person_photo} alt="" className="h-10 w-8 rounded object-cover" />
              : <div className="flex h-10 w-8 items-center justify-center rounded bg-secondary"><UserRound className="h-4 w-4" /></div>}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{e.person_name} <span className="text-xs text-muted-foreground">· {e.door_name}</span></p>
              <p className="truncate text-xs text-muted-foreground">por <b className="text-amber-300">{e.operator_name}</b> · {e.manual_reason}{e.original_reason ? ` · negado antes: ${e.original_reason}` : ""}</p>
            </div>
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{fmt(e.timestamp)}</span>
          </div>
        ))}
      </Card>
      <ManualReleaseDialog point={point} onClose={() => setPoint(null)} />
    </div>
  );
}
