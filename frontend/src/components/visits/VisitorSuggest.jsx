import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { UserRound } from "lucide-react";

export function VisitorSuggest({ value, onChange, onPick, className, testid, field, inputMode }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [hi, setHi] = useState(-1);
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  useEffect(() => {
    if (!open || (value || "").trim().length < 3) { setItems([]); return undefined; }
    const t = setTimeout(() => api.get(`/visits/visitor-search?q=${encodeURIComponent(value.trim())}`)
      .then(({ data }) => { setItems(data); setHi(-1); }).catch(() => setItems([])), 250);
    return () => clearTimeout(t);
  }, [value, open]);
  const pick = (v) => { setOpen(false); setItems([]); onPick(v.id); };
  const onKey = (e) => {
    if (e.key === "Escape") setOpen(false);
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((i) => Math.min(i + 1, items.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setHi((i) => Math.max(i - 1, 0)); }
    if (e.key === "Enter") { e.preventDefault(); pick(items[Math.max(hi, 0)]); }
  };
  return (
    <div ref={ref} className="relative">
      <Input value={value} onChange={(e) => { onChange(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={onKey}
        autoComplete="off" inputMode={inputMode} className={className} data-testid={testid} />
      {open && items.length > 0 && (
        <div className="absolute z-30 mt-1 max-h-72 w-full min-w-72 overflow-auto rounded-md border border-border bg-popover p-1 shadow-xl" data-testid={`${testid}-suggestions`}>
          <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground">Visitantes cadastrados · Enter preenche</p>
          {items.map((v, i) => (
            <button key={v.id} type="button" onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setHi(i)} onClick={() => pick(v)}
              className={cn("flex w-full items-center gap-2 rounded px-2 py-1.5 text-left", i === Math.max(hi, 0) ? "bg-secondary" : "hover:bg-secondary")}
              data-testid={`${field}-suggestion-${v.id}`}>
              {v.photo_thumb ? <img src={v.photo_thumb} alt="" className="h-8 w-6 rounded object-cover" /> : <div className="flex h-8 w-6 items-center justify-center rounded bg-secondary"><UserRound className="h-3 w-3" /></div>}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{v.name}</p>
                <p className="truncate font-mono text-[11px] text-muted-foreground">{(v.doc_type || "doc").toUpperCase()} {v.doc_number}{v.origin_company ? ` · ${v.origin_company}` : ""}</p>
              </div>
              {v.blacklist && <span className="rounded bg-red-500/20 px-1 text-[10px] font-bold text-red-300">LISTA NEGRA</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
