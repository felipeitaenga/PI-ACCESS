import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PersonCard, VisitorCard } from "@/components/registry/PeopleCards";
import { BulkBar } from "@/components/registry/BulkBar";
import { Loader2, MousePointerClick, Plus, Search } from "lucide-react";

const PAGE = 50;

function Filters({ f, setF, categories, departments }) {
  const sel = (key, ph, opts, testid) => (
    <Select value={f[key] || "all"} onValueChange={(v) => setF((s) => ({ ...s, [key]: v === "all" ? "" : v }))}>
      <SelectTrigger className="h-8 text-xs" data-testid={testid}><SelectValue placeholder={ph} /></SelectTrigger>
      <SelectContent><SelectItem value="all">{ph}</SelectItem>{opts.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
    </Select>
  );
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {sel("status", "Todos status", [["ativo", "Ativo"], ["inativo", "Inativo"], ["bloqueado", "Bloqueado"], ["vencido", "Vencido"]], "people-filter-status")}
      {sel("category_id", "Todas categorias", categories.map((c) => [c.id, c.code]), "people-filter-category")}
      {sel("department", "Todos deptos.", departments.map((d) => [d, d]), "people-filter-department")}
      {sel("present", "Presença: todos", [["true", "Presente agora"]], "people-filter-present")}
    </div>
  );
}

export function PeopleColumn({ selection, activeId, categories, refreshKey, onOpen, onNew }) {
  const isCompany = selection?.kind === "company";
  const [q, setQ] = useState("");
  const [f, setF] = useState({ status: "", category_id: "", department: "", present: "" });
  const [data, setData] = useState({ items: [], total: 0, stats: null, departments: [] });
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState([]);
  const sentinel = useRef(null);
  const key = selection ? `${selection.kind}:${selection.id || selection.name}` : "";

  const fetchPage = useCallback(async (skip) => {
    if (!selection) return;
    setLoading(true);
    try {
      if (isCompany) {
        const p = new URLSearchParams({ company_id: selection.id, q, skip, limit: PAGE, ...f });
        const { data: d } = await api.get(`/registry/people?${p}`);
        setData((old) => ({ ...d, items: skip ? [...old.items, ...d.items] : d.items }));
      } else {
        const p = new URLSearchParams({ q, ...(selection.kind === "visitors_today" ? { today_only: "true" } : { origin: selection.name }) });
        const { data: d } = await api.get(`/registry/visitors?${p}`);
        setData({ ...d, stats: null, departments: [] });
      }
    } finally { setLoading(false); }
  }, [key, q, f, isCompany]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setChecked([]); }, [key]);
  useEffect(() => { const t = setTimeout(() => fetchPage(0), 250); return () => clearTimeout(t); }, [fetchPage, refreshKey]);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !isCompany) return undefined;
    const ob = new IntersectionObserver(([e]) => { if (e.isIntersecting && !loading && data.items.length < data.total) fetchPage(data.items.length); });
    ob.observe(el);
    return () => ob.disconnect();
  }, [data, loading, fetchPage, isCompany]);

  if (!selection) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center text-sm text-muted-foreground" data-testid="people-column-empty">
        <MousePointerClick className="h-8 w-8 text-sky-400/60" />Selecione uma empresa à esquerda ou use a busca global (Ctrl+K).
      </div>
    );
  }
  const title = isCompany ? selection.company?.name : selection.name;
  const s = data.stats;
  const allChecked = data.items.length > 0 && checked.length === data.items.length;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="people-column">
      <div className="space-y-2 border-b border-border p-3">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-heading text-sm font-bold" data-testid="people-column-title">{title}</h2>
            {s ? <p className="font-mono text-[11px] text-muted-foreground" data-testid="people-column-stats"><span className="text-emerald-400">{s.active} ativos</span> · <span className="text-red-400">{s.blocked} bloq.</span> · <span className="text-sky-300">{s.present} presentes</span></p>
              : <p className="font-mono text-[11px] text-muted-foreground">{data.total} visitante(s)</p>}
          </div>
          <Button size="sm" className="h-7 bg-sky-500 px-2 text-xs text-slate-950 hover:bg-sky-400" onClick={() => onNew(selection)} data-testid="people-add-in-company"><Plus className="mr-1 h-3.5 w-3.5" />{isCompany ? "Pessoa nesta empresa" : "Visitante"}</Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="h-9 pl-8" placeholder={isCompany ? "Nome, CPF, matrícula…" : "Nome ou documento…"} value={q} onChange={(e) => setQ(e.target.value)} data-testid="people-search-input" />
        </div>
        {isCompany && <Filters f={f} setF={setF} categories={categories} departments={data.departments || []} />}
        {isCompany && data.items.length > 0 && (
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <input type="checkbox" checked={allChecked} onChange={() => setChecked(allChecked ? [] : data.items.map((p) => p.id))} data-testid="people-check-all" />
            Selecionar todos carregados ({data.items.length}/{data.total})
          </label>
        )}
      </div>
      {checked.length > 0 && <BulkBar selected={checked} items={data.items} categories={categories} onClear={() => setChecked([])} onDone={() => { setChecked([]); fetchPage(0); }} />}
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3" data-testid="people-list">
        {data.items.map((p) => isCompany ? (
          <PersonCard key={p.id} p={p} active={activeId === p.id} checked={checked.includes(p.id)}
            onCheck={(v) => setChecked((c) => (v ? [...c, p.id] : c.filter((x) => x !== p.id)))} onOpen={() => onOpen("person", p.id)} />
        ) : <VisitorCard key={p.id} v={p} active={activeId === p.id} onOpen={() => onOpen("visitor", p.id)} />)}
        {!loading && data.items.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">Nenhum registro encontrado</p>}
        <div ref={sentinel} className="h-4" />
        {loading && <p className="flex justify-center py-2"><Loader2 className="h-4 w-4 animate-spin text-sky-400" /></p>}
      </div>
    </div>
  );
}
