import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";

// Campo único: ao tocar mostra a lista; ao digitar filtra. items: [{id, name}]
export function SearchSelect({ items, value, onChange, onQuery, placeholder, disabled, loading, testid }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef(null);
  const picked = items.find((i) => i.id === value) || (value && SearchSelect.cache[value]) || null;
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setQ(""); } };
    document.addEventListener("pointerdown", h);
    return () => document.removeEventListener("pointerdown", h);
  }, []);
  useEffect(() => { if (onQuery) onQuery(q); }, [q]); // eslint-disable-line
  const list = onQuery ? items : items.filter((i) => i.name.toLowerCase().includes(q.trim().toLowerCase()));
  const pick = (i) => { SearchSelect.cache[i.id] = i; onChange(i.id); setOpen(false); setQ(""); };
  return (
    <div ref={ref} className="relative" data-testid={testid}>
      <div className="relative">
        <input
          className="h-11 w-full rounded-md border border-input bg-field px-3 pr-16 text-base placeholder:text-muted-foreground focus:border-sky-500 focus:outline-none disabled:opacity-50 sm:h-9 sm:text-sm"
          value={open ? q : picked?.name || ""} placeholder={picked && open ? picked.name : placeholder} disabled={disabled}
          onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          autoComplete="off" data-testid={`${testid}-input`} />
        {value && !disabled && (
          <button type="button" className="absolute right-8 top-0 flex h-full w-8 items-center justify-center text-muted-foreground" onClick={() => { onChange(""); setQ(""); }} aria-label="Limpar" data-testid={`${testid}-clear`}><X className="h-4 w-4" /></button>
        )}
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      </div>
      {open && !disabled && (
        <div className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-lg" data-testid={`${testid}-list`}>
          {loading && <p className="px-3 py-2 text-sm text-muted-foreground">Carregando…</p>}
          {!loading && list.length === 0 && <p className="px-3 py-2 text-sm text-muted-foreground">Nada encontrado.</p>}
          {list.map((i) => (
            <button key={i.id} type="button" onClick={() => pick(i)}
              className="flex min-h-11 w-full items-center gap-2 rounded px-3 text-left text-base hover:bg-secondary sm:min-h-9 sm:text-sm"
              data-testid={`${testid}-option-${i.id}`}>
              <span className="flex-1">{i.name}</span>{i.id === value && <Check className="h-4 w-4 text-sky-400" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
SearchSelect.cache = {};
