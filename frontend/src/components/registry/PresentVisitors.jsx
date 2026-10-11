import { useCallback, useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { fmtDateTime } from "@/lib/br";
import { LogOut, UserRound, Users } from "lucide-react";
import { toast } from "sonner";

export function PresentVisitors({ refreshKey, onOpen, onChanged }) {
  const [items, setItems] = useState([]);
  const load = useCallback(() => api.get("/registry/visits/present").then(({ data }) => setItems(data)).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load, refreshKey]);

  const checkout = async (v) => {
    try { await api.post(`/registry/visits/${v.id}/checkout`); toast.success(`Check-out de ${v.visitor_name}`); load(); onChanged(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="present-visitors">
      <div className="flex items-center gap-2 border-b border-border p-3">
        <Users className="h-4 w-4 text-emerald-400" />
        <h2 className="flex-1 font-heading text-xs font-bold uppercase tracking-widest text-muted-foreground">Visitantes presentes agora</h2>
        <span className="font-mono text-sm text-emerald-300" data-testid="present-visitors-count">{items.length}</span>
      </div>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3">
        {items.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Nenhum visitante no site</p>}
        {items.map((v) => (
          <div key={v.id} className="flex items-center gap-2.5 rounded-md border border-border bg-card/40 px-2.5 py-2" data-testid={`present-visit-${v.id}`}>
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2.5 text-left" onClick={() => onOpen("visitor", v.visitor_id)} data-testid={`present-open-${v.id}`}>
              {v.photo ? <img src={v.photo} alt="" className="h-12 w-9 rounded object-cover" /> : <div className="flex h-12 w-9 items-center justify-center rounded bg-secondary"><UserRound className="h-4 w-4" /></div>}
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{v.visitor_name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{v.origin_company} → {v.host_name}</p>
                <p className="font-mono text-[11px] text-muted-foreground">entrada {fmtDateTime(v.checkin_at)}{v.overstay && <span className="ml-1 text-amber-400">· excedeu</span>}</p>
              </div>
            </button>
            <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => checkout(v)} data-testid={`present-checkout-${v.id}`}><LogOut className="mr-1 h-3.5 w-3.5" />Check-out</Button>
          </div>
        ))}
      </div>
    </div>
  );
}
