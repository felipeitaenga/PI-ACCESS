import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CalendarClock, Mail, Plus, RefreshCw, XCircle } from "lucide-react";
import { toast } from "sonner";

const primary = "bg-sky-500 text-slate-950 hover:bg-sky-400";
const hm = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const dayKey = (iso) => new Date(iso).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit" });
const short = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export default function Schedules() {
  const navigate = useNavigate();
  const [visits, setVisits] = useState([]);
  const [invites, setInvites] = useState([]);
  const [days, setDays] = useState(7);
  const load = useCallback(() => {
    api.get(`/visits/scheduled?days=${days}`).then(({ data }) => setVisits(data)).catch(() => {});
    api.get("/selfreg/invites").then(({ data }) => setInvites(data.filter((i) => i.status === "ativo"))).catch(() => {});
  }, [days]);
  useEffect(() => { load(); }, [load]);
  const groups = useMemo(() => {
    const m = new Map();
    visits.forEach((v) => { const k = dayKey(v.start_at); m.set(k, [...(m.get(k) || []), v]); });
    return [...m.entries()];
  }, [visits]);
  const cancel = async (v) => {
    if (!window.confirm(`Cancelar a visita de ${v.visitor_name}?`)) return;
    try { await api.post(`/visits/${v.id}/cancel`); toast.success("Visita cancelada"); load(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  return (
    <div className="space-y-4" data-testid="page-schedules">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1">
          <h1 className="font-heading text-2xl font-bold tracking-tight">Agendamentos</h1>
          <p className="mt-1 text-sm text-muted-foreground">Visitas marcadas para os próximos dias e convites aguardando o cadastro do visitante</p>
        </div>
        <Button variant="outline" onClick={() => navigate("/autocadastro")}><Mail className="mr-1 h-4 w-4" />Convidar visitante</Button>
        <Button className={primary} onClick={() => navigate("/cadastro/visitantes")}><Plus className="mr-1 h-4 w-4" />Nova visita</Button>
      </div>

      <Card className="border-border bg-card p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 className="flex-1 font-heading text-sm font-bold uppercase tracking-widest">Visitas agendadas</h2>
          {[[1, "Hoje/amanhã"], [7, "7 dias"], [30, "30 dias"]].map(([d, l]) => (
            <Button key={d} size="sm" variant={days === d ? "default" : "outline"} className={days === d ? primary : ""} onClick={() => setDays(d)}>{l}</Button>
          ))}
          <Button size="sm" variant="ghost" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
        </div>
        {groups.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-8 text-sm text-muted-foreground"><CalendarClock className="h-8 w-8" />Nenhuma visita agendada no período.</div>
        )}
        <div className="space-y-4">
          {groups.map(([day, items]) => (
            <div key={day}>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-sky-300">{day}</p>
              <div className="space-y-1.5">
                {items.map((v) => (
                  <div key={v.id} className="flex items-center gap-3 rounded-md border border-border px-3 py-2" data-testid={`schedule-${v.id}`}>
                    <div className="w-24 shrink-0 font-mono text-sm">{hm(v.start_at)}–{hm(v.end_at)}</div>
                    {v.photo ? <img src={v.photo} alt="" className="h-10 w-8 rounded object-cover" /> : <div className="h-10 w-8 rounded bg-secondary" />}
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{v.visitor_name}{v.visitor_company ? <span className="text-muted-foreground"> · {v.visitor_company}</span> : null}</p>
                      <p className="truncate text-xs text-muted-foreground">{v.host_name} · {v.host_company_name} · {v.visit_type_name}{v.origin?.startsWith("autocadastro") ? " · autocadastro" : ""}</p>
                    </div>
                    <Button size="icon" variant="ghost" className="text-red-400" title="Cancelar visita" onClick={() => cancel(v)}><XCircle className="h-4 w-4" /></Button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="border-border bg-card p-4">
        <h2 className="mb-3 font-heading text-sm font-bold uppercase tracking-widest">Convites aguardando cadastro</h2>
        {invites.length === 0 && <p className="py-4 text-center text-sm text-muted-foreground">Nenhum convite pendente.</p>}
        <div className="space-y-1.5">
          {invites.map((i) => (
            <div key={i.id} className="flex items-center gap-3 rounded-md border border-border px-3 py-2 text-sm">
              <div className="w-28 shrink-0 font-mono text-xs">{short(i.start_at)}</div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{i.guest_name || i.guest_email || "Visitante"} → {i.host_name}</p>
                <p className="truncate text-xs text-muted-foreground">{i.host_company_name} · até {short(i.end_at)} · convite vale até {short(i.expires_at)}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
