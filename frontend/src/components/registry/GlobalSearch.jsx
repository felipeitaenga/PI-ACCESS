import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Search, UserRound } from "lucide-react";

export function GlobalSearch({ open, onOpenChange, onPick }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [idx, setIdx] = useState(0);

  useEffect(() => { if (open) { setQ(""); setItems([]); } }, [open]);
  useEffect(() => {
    if (q.trim().length < 2) { setItems([]); return undefined; }
    const t = setTimeout(() => api.get(`/registry/search?q=${encodeURIComponent(q)}`).then(({ data }) => { setItems(data); setIdx(0); }).catch(() => setItems([])), 250);
    return () => clearTimeout(t);
  }, [q]);

  const pick = (r) => { onPick(r); onOpenChange(false); };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, items.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    if (e.key === "Enter" && items[idx]) pick(items[idx]);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl p-0" data-testid="global-search-dialog">
        <DialogHeader className="sr-only"><DialogTitle>Busca global de pessoas</DialogTitle><DialogDescription>Busque por nome, CPF, documento, matrícula, cartão ou placa</DialogDescription></DialogHeader>
        <div className="relative border-b border-border p-3">
          <Search className="absolute left-6 top-6 h-4 w-4 text-muted-foreground" />
          <Input autoFocus className="h-11 pl-10 text-base" placeholder="Nome, CPF, documento, matrícula, cartão ou placa…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} data-testid="global-search-input" />
        </div>
        <div className="max-h-[50vh] overflow-y-auto p-2" data-testid="global-search-results">
          {q.trim().length >= 2 && items.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">Nenhum resultado</p>}
          {items.map((r, i) => (
            <button key={`${r.kind}-${r.id}`} type="button" onMouseEnter={() => setIdx(i)} onClick={() => pick(r)} data-testid={`global-search-result-${r.id}`}
              className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2 text-left", i === idx ? "bg-sky-500/15" : "hover:bg-secondary")}>
              {r.photo ? <img src={r.photo} alt="" className="h-10 w-8 rounded object-cover" /> : <div className="flex h-10 w-8 items-center justify-center rounded bg-secondary"><UserRound className="h-4 w-4" /></div>}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{r.name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{r.company_name} · {r.document}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-wider text-sky-300">{r.person_type}</p>
                <p className="text-[11px] text-muted-foreground">{r.match}</p>
              </div>
            </button>
          ))}
        </div>
        <p className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">↑↓ navegar · Enter abrir cadastro · Esc fechar</p>
      </DialogContent>
    </Dialog>
  );
}
