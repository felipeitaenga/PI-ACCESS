import { useMemo, useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useRealtime } from "@/context/RealtimeContext";
import { PassageTag, ResultBadge } from "@/components/common";
import { useOpenRecord } from "@/components/registry/useRegistryData";
import { CaptureActions } from "@/components/registry/CaptureActions";
import { cn } from "@/lib/utils";
import { Activity, UserRound } from "lucide-react";

const FILTERS = [["all", "Todos"], ["fixo", "Fixos"], ["visitante", "Visitantes"]];
const typeOf = (e) => (e.person_type === "visitante" ? "visitante" : e.person_id ? "fixo" : "sistema");
const TYPE_CLS = { fixo: "border-sky-500/40 text-sky-300", visitante: "border-amber-500/40 text-amber-300", sistema: "border-slate-500/40 text-slate-400" };
const time = (iso) => new Date(iso).toLocaleTimeString("pt-BR");

function EventRow({ e, onOpen }) {
  const t = typeOf(e);
  const photo = e.captured_photo || e.person_photo;
  const canOpen = t !== "sistema";
  return (
    <div role={canOpen ? "button" : undefined} tabIndex={canOpen ? 0 : undefined} title={canOpen ? "Abrir cadastro" : undefined}
      onClick={canOpen ? () => onOpen(t === "visitante" ? "visitor" : "person", e.person_id) : undefined}
      className={cn("flex items-center gap-2.5 rounded-md border border-border bg-card/40 px-2.5 py-2 animate-in fade-in slide-in-from-top-1 duration-500", canOpen && "cursor-pointer transition-colors hover:border-sky-500/50 hover:bg-secondary/50")} data-testid={`live-event-${e.id}`}>
      {photo ? <img src={photo} alt="" className="h-11 w-9 shrink-0 rounded object-cover" /> : <div className="flex h-11 w-9 shrink-0 items-center justify-center rounded bg-secondary"><UserRound className="h-4 w-4" /></div>}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium">{e.person_name}</span>
          <span className={cn("shrink-0 rounded border px-1 text-[9px] font-bold uppercase", TYPE_CLS[t])} data-testid={`live-event-type-${e.id}`}>{t}</span>
        </div>
        <p className="truncate text-[11px] text-muted-foreground">{e.door_name}{e.company_name ? ` · ${e.company_name}` : ""}</p>
        {e.access_result === "denied" && e.reason && <p className="truncate text-[11px] text-red-400">{e.reason}</p>}
        {!canOpen && <CaptureActions photo={e.captured_photo} className="mt-1" testPrefix={`live-event-capture-${e.id}`} />}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <ResultBadge result={e.access_result} />
        <PassageTag passage={e.passage} />
        <span className="font-mono text-[10px] text-muted-foreground">{time(e.timestamp)}</span>
      </div>
    </div>
  );
}

export function LiveAccessFeed() {
  const { events, connected, patch } = useRealtime();
  const [seed, setSeed] = useState([]);
  const [filter, setFilter] = useState("all");
  const openRecord = useOpenRecord();
  useEffect(() => { api.get("/events?limit=30").then(({ data }) => setSeed(data.items || [])).catch(() => {}); }, []);
  const list = useMemo(() => {
    const seen = new Set();
    return [...events, ...seed].filter((e) => !seen.has(e.id) && seen.add(e.id)).map(patch)
      .filter((e) => filter === "all" || typeOf(e) === filter).slice(0, 60);
  }, [events, seed, filter]);

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="live-access-feed">
      <div className="flex items-center gap-2 border-b border-border p-3">
        <Activity className="h-4 w-4 text-sky-400" />
        <h2 className="flex-1 font-heading text-xs font-bold uppercase tracking-widest text-muted-foreground">Acessos em tempo real</h2>
        <span className={cn("flex items-center gap-1 text-[10px] font-mono", connected ? "text-emerald-400" : "text-slate-500")} data-testid="live-feed-status">
          <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "animate-pulse bg-emerald-500" : "bg-slate-500")} />{connected ? "AO VIVO" : "OFFLINE"}
        </span>
      </div>
      <div className="flex gap-1 px-3 pt-2">
        {FILTERS.map(([k, l]) => (
          <button key={k} type="button" onClick={() => setFilter(k)} data-testid={`live-filter-${k}`}
            className={cn("rounded-full border px-2.5 py-0.5 text-[11px] transition-colors", filter === k ? "border-sky-500 bg-sky-500/15 text-sky-300" : "border-border text-muted-foreground hover:text-foreground")}>{l}</button>
        ))}
      </div>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3" data-testid="live-feed-list">
        {list.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Aguardando eventos…</p>}
        {list.map((e) => <EventRow key={e.id} e={e} onOpen={openRecord} />)}
      </div>
    </div>
  );
}
