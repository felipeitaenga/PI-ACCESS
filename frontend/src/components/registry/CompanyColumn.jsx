import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { COMPANY_TYPES } from "@/components/registry/QuickCompanyDialog";
import { AlertTriangle, Building2, CalendarCheck, ChevronDown, Plus, Search, UserCheck } from "lucide-react";

const CHIPS = [["all", "Todas"], ["propria", "Fixos"], ["terceirizada", "Terceirizada"], ["transportadora", "Transportadora"], ["visitantes", "Visitantes"]];
export const TYPE_CLS = {
  propria: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  terceirizada: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  transportadora: "border-teal-500/40 bg-teal-500/10 text-teal-300",
};

function CompanyCard({ c, active, onClick }) {
  const s = c.stats || {};
  return (
    <button type="button" onClick={onClick} data-testid={`company-card-${c.id}`}
      className={cn("w-full rounded-md border px-3 py-2.5 text-left transition-colors", active ? "border-sky-500 bg-sky-500/10" : "border-border bg-card/40 hover:border-sky-500/40")}>
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{c.name}</span>
        {c.alerts?.length > 0 && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" data-testid={`company-alert-${c.id}`} />}
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className={cn("rounded border px-1.5 py-px font-medium uppercase", TYPE_CLS[c.type])}>{COMPANY_TYPES[c.type] || c.type}</span>
        <span className="font-mono" data-testid={`company-active-${c.id}`}>{s.active ?? 0} ativos</span>
        <span className="font-mono text-emerald-400" data-testid={`company-present-${c.id}`}>{s.present ?? 0} no site</span>
      </div>
      {c.alerts?.length > 0 && <p className="mt-1 truncate text-[11px] text-amber-300/90" title={c.alerts.join(" · ")}>{c.alerts.join(" · ")}</p>}
    </button>
  );
}

function OriginCard({ o, active, onClick }) {
  return (
    <button type="button" onClick={onClick} data-testid={`host-company-card-${o.id}`}
      className={cn("w-full rounded-md border px-3 py-2.5 text-left transition-colors", active ? "border-sky-500 bg-sky-500/10" : "border-border bg-card/40 hover:border-sky-500/40")}>
      <p className="truncate text-sm font-medium">{o.name}</p>
      <p className="mt-1 text-[11px] text-muted-foreground"><span className="font-mono">{o.total} visitantes</span> · <span className="font-mono text-emerald-400">{o.present} presentes</span>{o.blacklist > 0 && <span className="text-red-400"> · {o.blacklist} lista negra</span>}</p>
    </button>
  );
}

function Pinned({ icon: Icon, label, value, active, onClick, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={cn("flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors", active ? "border-sky-500 bg-sky-500/10 text-sky-200" : "border-dashed border-border hover:border-sky-500/40")}>
      <Icon className="h-4 w-4 text-sky-400" /><span className="flex-1">{label}</span><span className="font-mono text-xs text-muted-foreground">{value}</span>
    </button>
  );
}

export function CompanyColumn({ companies, visitorData, selection, onSelect, onNewCompany, variant = "fixed" }) {
  const fixed = variant === "fixed";
  const [q, setQ] = useState("");
  const [chip, setChip] = useState(fixed ? "all" : "visitantes");
  const [grouped, setGrouped] = useState(false);
  const [closed, setClosed] = useState({});
  const own = companies.find((c) => c.type === "propria");
  const isSel = (kind, id) => selection?.kind === kind && (selection.id ?? selection.name) === id;

  const list = useMemo(() => companies.filter((c) => (chip === "all" || c.type === chip) &&
    `${c.name} ${c.trade_name || ""} ${c.cnpj || ""}`.toLowerCase().includes(q.toLowerCase())), [companies, chip, q]);
  const origins = (visitorData?.companies || []).filter((o) => o.name.toLowerCase().includes(q.toLowerCase()));
  const groups = useMemo(() => {
    const g = {};
    list.forEach((c) => { (g[c.group_name || "Sem grupo"] ||= []).push(c); });
    return Object.entries(g).sort(([a], [b]) => a.localeCompare(b));
  }, [list]);

  const card = (c) => <CompanyCard key={c.id} c={c} active={isSel("company", c.id)} onClick={() => onSelect({ kind: "company", id: c.id, company: c })} />;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="company-column">
      <div className="space-y-2 border-b border-border p-3">
        <div className="flex items-center gap-2">
          <h2 className="flex-1 font-heading text-xs font-bold uppercase tracking-widest text-muted-foreground">{fixed ? "Empresas" : "Empresas visitadas"}</h2>
          {fixed && <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={onNewCompany} data-testid="company-add-button"><Plus className="mr-1 h-3.5 w-3.5" />Empresa</Button>}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="h-9 pl-8" placeholder={fixed ? "Buscar empresa…" : "Buscar empresa visitada…"} value={q} onChange={(e) => setQ(e.target.value)} data-testid="company-search-input" />
        </div>
        <div className="flex flex-wrap gap-1">
          {fixed && CHIPS.filter(([k]) => k !== "visitantes").map(([k, l]) => (
            <button key={k} type="button" onClick={() => setChip(k)} data-testid={`company-chip-${k}`}
              className={cn("rounded-full border px-2.5 py-0.5 text-[11px] transition-colors", chip === k ? "border-sky-500 bg-sky-500/15 text-sky-300" : "border-border text-muted-foreground hover:text-foreground")}>{l}</button>
          ))}
        </div>
        {chip !== "visitantes" && (
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground"><Switch checked={grouped} onCheckedChange={setGrouped} data-testid="company-group-toggle" />Agrupar por grupo de empresas</label>
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3">
        {fixed && own && <Pinned icon={Building2} label="Funcionários fixos" value={own.stats?.active ?? 0} active={isSel("company", own.id)} onClick={() => onSelect({ kind: "company", id: own.id, company: own })} testid="pinned-own" />}
        {!fixed && <Pinned icon={CalendarCheck} label="Visitantes do dia" value={visitorData?.today ?? 0} active={selection?.kind === "visitors_today"} onClick={() => onSelect({ kind: "visitors_today", name: "Visitantes do dia" })} testid="pinned-visitors-today" />}
        <div className="h-1" />
        {chip === "visitantes" ? (
          <>
            <p className="flex items-center gap-1.5 px-1 text-[11px] uppercase tracking-wider text-muted-foreground"><UserCheck className="h-3 w-3" />Empresas visitadas</p>
            {origins.map((o) => <OriginCard key={o.id} o={o} active={isSel("visitor_host", o.id)} onClick={() => onSelect({ kind: "visitor_host", id: o.id, name: o.name })} />)}
            {origins.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Nenhuma visita registrada</p>}
          </>
        ) : grouped ? groups.map(([g, items]) => (
          <div key={g} data-testid={`company-group-${g}`}>
            <button type="button" onClick={() => setClosed((s) => ({ ...s, [g]: !s[g] }))} className="flex w-full items-center gap-1 px-1 py-1 text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground">
              <ChevronDown className={cn("h-3 w-3 transition-transform", closed[g] && "-rotate-90")} />{g}<span className="ml-auto font-mono">{items.length}</span>
            </button>
            {!closed[g] && <div className="space-y-1.5">{items.map(card)}</div>}
          </div>
        )) : list.map(card)}
        {chip !== "visitantes" && list.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Nenhuma empresa encontrada</p>}
      </div>
    </div>
  );
}
