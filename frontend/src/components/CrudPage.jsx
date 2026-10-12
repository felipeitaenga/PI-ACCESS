import { useEffect, useState, useCallback } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Search, MoreHorizontal, Pencil, Trash2, ChevronLeft, ChevronRight, CheckCircle2, XCircle, Download } from "lucide-react";
import { toast } from "sonner";

export function enabledBadge(v) {
  return v !== false
    ? <Badge variant="outline" className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">Habilitado</Badge>
    : <Badge variant="outline" className="bg-slate-500/15 text-slate-400 border-slate-500/30">Desabilitado</Badge>;
}

export default function CrudPage({
  title, subtitle, endpoint, columns, formFields, renderForm, defaultForm = {},
  searchPlaceholder = "Pesquisar...", writeRoles = ["admin", "operator"], onLoaded,
  beforeSave, extraActions,
}) {
  const { hasRole } = useAuth();
  const canEdit = hasRole(...writeRoles);
  const [data, setData] = useState({ items: [], total: 0 });
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(15);
  const [selected, setSelected] = useState(new Set());
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(defaultForm);
  const [editId, setEditId] = useState(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page, limit });
    if (q) params.set("q", q);
    const { data } = await api.get(`${endpoint}?${params}`);
    setData(data);
    setSelected(new Set());
    if (onLoaded) onLoaded(data);
  }, [endpoint, page, limit, q, onLoaded]);

  useEffect(() => { load(); }, [page, limit]); // eslint-disable-line
  useEffect(() => { const t = setTimeout(() => { setPage(1); load(); }, 400); return () => clearTimeout(t); }, [q]); // eslint-disable-line

  const totalPages = Math.max(1, Math.ceil(data.total / limit));

  const openNew = () => { setForm({ ...defaultForm }); setEditId(null); setOpen(true); };
  const openEdit = (row) => { setForm({ ...defaultForm, ...row }); setEditId(row.id); setOpen(true); };

  const save = async () => {
    try {
      const payload = beforeSave ? beforeSave(form) : form;
      if (editId) await api.put(`${endpoint}/${editId}`, payload);
      else await api.post(endpoint, payload);
      toast.success(editId ? "Registro atualizado" : "Registro criado");
      setOpen(false); load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const remove = async (id) => {
    if (!window.confirm("Excluir este registro?")) return;
    await api.delete(`${endpoint}/${id}`); toast.success("Excluído"); load();
  };

  const bulk = async (action) => {
    const ids = [...selected];
    if (!ids.length) { toast.error("Selecione ao menos um item"); return; }
    if (action === "export") { exportCsv(data.items.filter((i) => selected.has(i.id))); return; }
    await api.post(`${endpoint}/bulk`, { ids, action });
    toast.success(`${ids.length} itens atualizados`); load();
  };

  const exportCsv = (rows) => {
    const cols = columns.filter((c) => c.key);
    const header = cols.map((c) => c.label).join(";");
    const lines = rows.map((r) => cols.map((c) => `"${String(r[c.key] ?? "").replace(/"/g, '""')}"`).join(";"));
    const blob = new Blob(["\uFEFF" + [header, ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `${title}.csv`; a.click();
  };

  const allChecked = data.items.length > 0 && data.items.every((i) => selected.has(i.id));
  const toggleAll = () => {
    const next = new Set(selected);
    if (allChecked) data.items.forEach((i) => next.delete(i.id));
    else data.items.forEach((i) => next.add(i.id));
    setSelected(next);
  };
  const toggle = (id) => { const n = new Set(selected); n.has(id) ? n.delete(id) : n.add(id); setSelected(n); };

  return (
    <div>
      <PageHeader title={title} subtitle={subtitle}>
        {extraActions}
        {canEdit && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" data-testid="bulk-actions-button"><MoreHorizontal className="mr-2 h-4 w-4" /> Mais ações</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => bulk("enable")}><CheckCircle2 className="mr-2 h-4 w-4" /> Habilitar</DropdownMenuItem>
              <DropdownMenuItem onClick={() => bulk("disable")}><XCircle className="mr-2 h-4 w-4" /> Desabilitar</DropdownMenuItem>
              <DropdownMenuItem onClick={() => bulk("delete")} className="text-red-400"><Trash2 className="mr-2 h-4 w-4" /> Excluir</DropdownMenuItem>
              <DropdownMenuItem onClick={() => bulk("export")}><Download className="mr-2 h-4 w-4" /> Exportar CSV</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {canEdit && <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={openNew} data-testid="crud-add-button"><Plus className="mr-2 h-4 w-4" /> Novo</Button>}
      </PageHeader>

      <Card className="border-border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input placeholder={searchPlaceholder} value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" data-testid="crud-search-input" />
          </div>
          <Button variant="outline" onClick={load} data-testid="crud-search-button"><Search className="mr-2 h-4 w-4" /> Pesquisar</Button>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {canEdit && <TableHead className="w-10"><Checkbox checked={allChecked} onCheckedChange={toggleAll} data-testid="select-all-checkbox" /></TableHead>}
                {columns.map((c) => <TableHead key={c.key || c.label}>{c.label}</TableHead>)}
                {canEdit && <TableHead className="text-right">Ações</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((row) => (
                <TableRow key={row.id} data-testid={`crud-row-${row.id}`}>
                  {canEdit && <TableCell><Checkbox checked={selected.has(row.id)} onCheckedChange={() => toggle(row.id)} data-testid={`row-check-${row.id}`} /></TableCell>}
                  {columns.map((c) => <TableCell key={c.key || c.label}>{c.render ? c.render(row) : String(row[c.key] ?? "")}</TableCell>)}
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(row)} data-testid={`crud-edit-${row.id}`}><Pencil className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="icon" className="text-red-400" onClick={() => remove(row.id)} data-testid={`crud-delete-${row.id}`}><Trash2 className="h-4 w-4" /></Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
              {data.items.length === 0 && <TableRow><TableCell colSpan={columns.length + 2} className="py-10 text-center text-muted-foreground">Nenhum registro encontrado.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-4 text-sm">
          <span className="text-muted-foreground">{data.total} registros · {selected.size} selecionados</span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(1)} data-testid="page-first">Primeira</Button>
            <Button variant="outline" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
            <span className="px-3 font-mono">{page} / {totalPages}</span>
            <Button variant="outline" size="icon" className="h-8 w-8" disabled={page >= totalPages} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(totalPages)} data-testid="page-last">Última</Button>
            <Button variant={limit > 15 ? "default" : "outline"} size="sm" onClick={() => setLimit(limit > 15 ? 15 : 500)} data-testid="page-all">Ver todas</Button>
          </div>
        </div>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto scrollbar-thin">
          <DialogHeader><DialogTitle>{editId ? "Editar" : "Novo"} — {title}</DialogTitle></DialogHeader>
          {renderForm ? renderForm(form, setForm) : (
            <GenericForm fields={formFields || []} form={form} setForm={setForm} />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} data-testid="crud-cancel-button">Voltar</Button>
            <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={save} data-testid="crud-save-button">Salvar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function FormRow({ label, children, className = "" }) {
  return (
    <div className={className}>
      <label className="mb-1.5 block text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

function GenericForm({ fields, form, setForm }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {fields.map((f) => (
        <FormRow key={f.key} label={f.label} className={f.full ? "col-span-2" : ""}>
          {f.type === "custom" ? f.render(form, setForm) : f.type === "select" ? (
            <Select value={form[f.key] ?? ""} onValueChange={(v) => setForm({ ...form, [f.key]: v })}>
              <SelectTrigger data-testid={`field-${f.key}`}><SelectValue placeholder="Selecione" /></SelectTrigger>
              <SelectContent>{(f.options || []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
            </Select>
          ) : f.type === "checkbox" ? (
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={!!form[f.key]} onCheckedChange={(v) => setForm({ ...form, [f.key]: !!v })} data-testid={`field-${f.key}`} /> {f.hint || "Sim"}
            </label>
          ) : (
            <Input type={f.type || "text"} value={form[f.key] ?? ""} data-testid={`field-${f.key}`}
              onChange={(e) => setForm({ ...form, [f.key]: f.type === "number" ? +e.target.value : e.target.value })} />
          )}
        </FormRow>
      ))}
    </div>
  );
}
