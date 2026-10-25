import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ChevronDown, Check, Plus, Search, X } from "lucide-react";

export function Field({ label, required, error, hint, className, children }) {
  return (
    <div className={className}>
      {label && <Label className="mb-1.5 block text-xs font-semibold text-foreground/85">{label}{required && <span className="ml-0.5 text-sky-400">*</span>}</Label>}
      {children}
      {error ? <p className="mt-1 text-xs text-red-400" data-testid="field-error">{error}</p> : hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function Section({ title, icon: Icon, count, defaultOpen = false, children, testid }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border bg-card/40" data-testid={testid}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium transition-colors hover:bg-secondary/40" data-testid={`${testid}-toggle`}>
        {Icon && <Icon className="h-4 w-4 text-sky-400" />}
        <span>{title}</span>
        {count > 0 && <span className="rounded bg-secondary px-1.5 font-mono text-[11px] text-muted-foreground">{count}</span>}
        <ChevronDown className={cn("ml-auto h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t border-border p-4">{children}</div>}
    </div>
  );
}

export const TYPES = [
  { key: "funcionario", label: "FUNCIONÁRIO" },
  { key: "terceiro", label: "TERCEIRO" },
  { key: "visitante", label: "VISITANTE" },
];

export function TypeSelector({ value, onChange, disabled, allowed }) {
  const types = TYPES.filter((t) => !allowed || allowed.includes(t.key));
  return (
    <div className={cn("grid gap-2", types.length === 2 ? "grid-cols-2" : "grid-cols-3")} data-testid="person-type-selector">
      {types.map((t) => (
        <button key={t.key} type="button" disabled={disabled && value !== t.key} onClick={() => onChange(t.key)}
          className={cn("rounded-md border px-3 py-3 font-heading text-xs font-bold tracking-widest transition-colors sm:text-sm",
            value === t.key ? "border-sky-500 bg-sky-500/15 text-sky-300" : "border-border text-muted-foreground hover:border-sky-500/40 hover:text-foreground",
            disabled && value !== t.key && "cursor-not-allowed opacity-40")}
          data-testid={`type-btn-${t.key}`}>{t.label}</button>
      ))}
    </div>
  );
}

export function CategoryMulti({ categories, value, onChange, error, placeholder = "Buscar e selecionar categorias…" }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const close = useCallback(() => setOpen(false), []);
  useOutside(ref, close);
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  const picked = value.map((id) => categories.find((c) => c.id === id)).filter(Boolean);
  const list = categories.filter((c) => `${c.code} ${c.description || ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div ref={ref} className="relative" data-testid="category-multi">
      <div onClick={() => setOpen(true)} className={cn("flex min-h-9 cursor-text flex-wrap items-center gap-1 rounded-md border bg-field px-2 py-1 transition-[border-color] hover:border-sky-500/50 focus-within:border-sky-500", error ? "border-red-500/60" : "border-input")}>
        {picked.map((c) => (
          <span key={c.id} className="flex items-center gap-1 rounded-full border border-sky-500/40 bg-sky-500/15 py-0.5 pl-2 pr-1 text-xs text-sky-300" data-testid={`category-tag-${c.code}`}>
            {c.code}
            <button type="button" onClick={(e) => { e.stopPropagation(); toggle(c.id); }} className="rounded-full p-0.5 hover:bg-sky-500/30" data-testid={`category-tag-remove-${c.code}`}><X className="h-3 w-3" /></button>
          </span>
        ))}
        <input id={error ? "f-category_ids" : undefined} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)} placeholder={picked.length ? "Adicionar…" : placeholder}
          className="min-w-28 flex-1 bg-transparent py-1 text-sm outline-none placeholder:text-muted-foreground" data-testid="category-search-input" />
      </div>
      {open && (
        <div className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-xl" data-testid="category-options">
          {list.length === 0 && <p className="px-2 py-1.5 text-xs text-muted-foreground">Nenhuma categoria</p>}
          {list.map((c) => {
            const on = value.includes(c.id);
            return (
              <button key={c.id} type="button" onClick={() => toggle(c.id)} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-secondary" data-testid={`category-chip-${c.code}`}>
                <span className={cn("flex h-4 w-4 shrink-0 items-center justify-center rounded border", on ? "border-sky-500 bg-sky-500 text-slate-950" : "border-border")}>{on && <Check className="h-3 w-3" />}</span>
                <span className="font-mono text-xs">{c.code}</span>
                <span className="truncate text-xs text-muted-foreground">{c.description}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function useOutside(ref, cb) {
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) cb(); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, cb]);
}

export function SuggestInput({ id, value, onChange, onBlur, inputRef, className, placeholder, inputMode, kind, onPick, testid }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const close = useCallback(() => setOpen(false), []);
  useOutside(ref, close);
  useEffect(() => {
    if (!open || (value || "").trim().length < 3) { setItems([]); return undefined; }
    const t = setTimeout(() => {
      api.get(`/registry/search?q=${encodeURIComponent(value.trim())}`)
        .then(({ data }) => setItems(data.filter((r) => r.kind === kind).slice(0, 8))).catch(() => setItems([]));
    }, 300);
    return () => clearTimeout(t);
  }, [value, open, kind]);
  return (
    <div ref={ref} className="relative">
      <Input id={id} ref={inputRef} value={value} placeholder={placeholder} inputMode={inputMode} className={className} autoComplete="off"
        onFocus={() => setOpen(true)} onChange={(e) => { onChange(e); setOpen(true); }} onBlur={onBlur}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)} data-testid={testid} />
      {open && items.length > 0 && (
        <div className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-xl" data-testid={`${testid}-suggestions`}>
          <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground">Já cadastrados — clique para abrir</p>
          {items.map((r) => (
            <button key={r.id} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { setOpen(false); onPick(r); }}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-secondary" data-testid={`suggest-option-${r.id}`}>
              {r.photo ? <img src={r.photo} alt="" className="h-8 w-6 rounded object-cover" /> : <div className="h-8 w-6 rounded bg-secondary" />}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{r.name}</p>
                <p className="truncate font-mono text-[11px] text-muted-foreground">{r.document} · {r.company_name}</p>
              </div>
              {r.status === "lista negra" && <span className="rounded bg-red-500/20 px-1 text-[10px] font-bold text-red-300">LISTA NEGRA</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function CompanyCombo({ id, companies, value, onChange, onCreate, allowedTypes }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  useOutside(ref, () => setOpen(false));
  const current = companies.find((c) => c.id === value);
  const list = companies.filter((c) => (!allowedTypes || allowedTypes.includes(c.type)) && `${c.name} ${c.trade_name || ""} ${c.cnpj || ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div ref={ref} className="relative">
      <Input id={id} value={open ? q : current?.name || ""} placeholder="Buscar empresa…" onFocus={() => { setOpen(true); setQ(""); }} onChange={(e) => setQ(e.target.value)} data-testid="company-combo-input" />
      {open && (
        <div className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-xl" data-testid="company-combo-list">
          {list.map((c) => (
            <button key={c.id} type="button" onClick={() => { onChange(c); setOpen(false); }} className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-secondary" data-testid={`company-option-${c.id}`}>
              <span className="truncate">{c.name}</span><span className="text-[10px] uppercase text-muted-foreground">{c.type}</span>
            </button>
          ))}
          <button type="button" onClick={() => { setOpen(false); onCreate(q); }} className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm text-sky-400 hover:bg-secondary" data-testid="company-combo-new">
            <Plus className="h-3.5 w-3.5" /> Nova empresa{q ? ` "${q}"` : ""}
          </button>
        </div>
      )}
    </div>
  );
}

export function HostCombo({ id, hostId, hostName, onChange }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  useOutside(ref, () => setOpen(false));
  useEffect(() => {
    if (!open) return undefined;
    const t = setTimeout(() => {
      api.get(`/registry/people?status=ativo&limit=8&q=${encodeURIComponent(q)}`).then(({ data }) => setItems(data.items)).catch(() => setItems([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, open]);
  return (
    <div ref={ref} className="relative">
      <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input id={id} className="pl-9" value={open ? q : hostName || ""} placeholder="Buscar pessoa fixa…" onFocus={() => { setOpen(true); setQ(""); }} onChange={(e) => setQ(e.target.value)} data-testid="host-combo-input" />
      {open && (
        <div className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-xl" data-testid="host-combo-list">
          {items.length === 0 && <p className="px-2 py-1.5 text-xs text-muted-foreground">Nenhuma pessoa encontrada</p>}
          {items.map((p) => (
            <button key={p.id} type="button" onClick={() => { onChange(p); setOpen(false); }} className="flex w-full flex-col rounded px-2 py-1.5 text-left hover:bg-secondary" data-testid={`host-option-${p.id}`}>
              <span className="text-sm">{p.name}</span><span className="text-[11px] text-muted-foreground">{p.company_name} · {p.department || p.role_title}</span>
            </button>
          ))}
          {hostId && <p className="border-t border-border px-2 pt-1 text-[11px] text-muted-foreground">Atual: {hostName}</p>}
        </div>
      )}
    </div>
  );
}
