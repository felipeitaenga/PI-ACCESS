import { useCallback, useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { fmtRemaining } from "@/components/visits/visitUtils";
import { DeviceCheckDialog } from "@/components/visits/DeviceCheckDialog";
import { LogOut, ScanFace, UserRound, Users } from "lucide-react";
import { toast } from "sonner";

export function PresentNow({ refreshKey, onChanged }) {
  const [items, setItems] = useState([]);
  const [checking, setChecking] = useState(null);
  const load = useCallback(() => api.get("/visits/present").then(({ data }) => setItems(data)).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load, refreshKey]);
  const [leaving, setLeaving] = useState(null);
  const checkout = async (v) => {
    if (leaving) { return; }
    setLeaving(v.id);
    setItems((list) => list.filter((x) => x.id !== v.id));
    try { await api.post(`/visits/${v.id}/end`); toast.success(`Check-out de ${v.visitor_name}`); onChanged?.(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setLeaving(null); load(); }
  };
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="present-now">
      <div className="flex items-center gap-2 border-b border-border p-3">
        <Users className="h-4 w-4 text-emerald-400" />
        <h2 className="flex-1 font-heading text-xs font-bold uppercase tracking-widest text-muted-foreground">Visitantes presentes agora</h2>
        <span className="font-mono text-sm text-emerald-300" data-testid="present-now-count">{items.length}</span>
      </div>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3">
        {items.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Nenhum visitante no local</p>}
        {items.map((v) => (
          <div key={v.id} className="flex items-center gap-2.5 rounded-md border border-border bg-card/40 px-2.5 py-2" data-testid={`present-now-${v.id}`}>
            {v.photo ? <img src={v.photo} alt="" className="h-12 w-9 rounded object-cover" /> : <div className="flex h-12 w-9 items-center justify-center rounded bg-secondary"><UserRound className="h-4 w-4" /></div>}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{v.visitor_name}</p>
              <p className="truncate text-[11px] text-muted-foreground">{v.visit_type_name} · {v.host_name}</p>
              <p className={`font-mono text-[11px] ${v.remaining_min < 30 ? "text-amber-400" : "text-muted-foreground"}`} data-testid={`present-now-remaining-${v.id}`}>restam {fmtRemaining(v.remaining_min)}</p>
            </div>
            <Button size="sm" variant="ghost" className="h-7 px-2" title="Verificar no facial" onClick={() => setChecking(v)} data-testid={`present-now-devcheck-${v.id}`}><ScanFace className="h-4 w-4" /></Button>
            <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => checkout(v)} data-testid={`present-now-checkout-${v.id}`}><LogOut className="mr-1 h-3.5 w-3.5" />Check-out</Button>
          </div>
        ))}
      </div>
      <DeviceCheckDialog visit={checking} onClose={() => setChecking(null)} />
    </div>
  );
}
