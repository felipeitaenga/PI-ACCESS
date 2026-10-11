import { useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CalendarPlus, Download, Lock, RefreshCw, Tags, Unlock, X } from "lucide-react";
import { toast } from "sonner";

function exportCsv(items) {
  const cols = ["name", "matricula", "cpf", "company_name", "department", "status", "valid_until"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cols.join(";"), ...items.map((p) => cols.map((c) => esc(p[c])).join(";"))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
  a.download = "pessoas.csv";
  a.click();
}

export function BulkBar({ selected, items, categories, onDone, onClear }) {
  const [dlg, setDlg] = useState(null);
  const [cat, setCat] = useState("");
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async (action, extra = {}) => {
    setBusy(true);
    try {
      const { data } = await api.post("/registry/people/bulk", { ids: selected, action, ...extra });
      toast.success(`${data.affected} pessoa(s) atualizada(s) · sincronizadas ${data.synced}${data.sync_errors ? ` · ${data.sync_errors} com erro` : ""}`);
      setDlg(null); onDone();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-border bg-sky-500/10 px-3 py-2" data-testid="bulk-bar">
      <span className="mr-1 font-mono text-xs text-sky-200" data-testid="bulk-count">{selected.length} selec.</span>
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setDlg("cat")} data-testid="bulk-category"><Tags className="mr-1 h-3.5 w-3.5" />Categoria</Button>
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={busy} onClick={() => run("block")} data-testid="bulk-block"><Lock className="mr-1 h-3.5 w-3.5" />Bloquear</Button>
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={busy} onClick={() => run("unblock")} data-testid="bulk-unblock"><Unlock className="mr-1 h-3.5 w-3.5" />Desbloquear</Button>
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setDlg("renew")} data-testid="bulk-renew"><CalendarPlus className="mr-1 h-3.5 w-3.5" />Renovar</Button>
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={busy} onClick={() => run("sync")} data-testid="bulk-sync"><RefreshCw className="mr-1 h-3.5 w-3.5" />Sincronizar</Button>
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => exportCsv(items.filter((p) => selected.includes(p.id)))} data-testid="bulk-export"><Download className="mr-1 h-3.5 w-3.5" />Exportar</Button>
      <Button size="icon" variant="ghost" className="ml-auto h-7 w-7" onClick={onClear} data-testid="bulk-clear"><X className="h-3.5 w-3.5" /></Button>
      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent className="max-w-sm" data-testid="bulk-dialog">
          <DialogHeader>
            <DialogTitle>{dlg === "cat" ? "Trocar categoria" : "Renovar validade"}</DialogTitle>
            <DialogDescription>Aplica a {selected.length} pessoa(s) e sincroniza com os equipamentos.</DialogDescription>
          </DialogHeader>
          {dlg === "cat" ? (
            <Select value={cat} onValueChange={setCat}><SelectTrigger data-testid="bulk-category-select"><SelectValue placeholder="Nova categoria" /></SelectTrigger>
              <SelectContent>{categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.code}</SelectItem>)}</SelectContent></Select>
          ) : <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid="bulk-renew-date" />}
          <Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" disabled={busy || (dlg === "cat" ? !cat : !date)}
            onClick={() => (dlg === "cat" ? run("set_category", { category_ids: [cat] }) : run("renew", { valid_until: date }))} data-testid="bulk-confirm">Aplicar</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
