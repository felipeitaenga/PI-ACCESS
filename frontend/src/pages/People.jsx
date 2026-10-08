import { useEffect, useRef, useState } from "react";
import { api, API, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Plus, Search, Upload, Download, Camera, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

const EMPTY = {
  name: "", matricula: "", document: "", company: "", department: "",
  role_title: "", photo: "", person_type: "colaborador", status: "ativo", consent: false,
};

function statusBadge(s) {
  const map = {
    ativo: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    inativo: "bg-slate-500/15 text-slate-400 border-slate-500/30",
    bloqueado: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  return <Badge variant="outline" className={map[s]}>{s}</Badge>;
}

export default function People() {
  const { hasRole } = useAuth();
  const [data, setData] = useState({ items: [], total: 0 });
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const fileRef = useRef();
  const webcamFileRef = useRef();
  const limit = 15;

  const load = async () => {
    const params = new URLSearchParams({ page, limit });
    if (q) params.set("q", q);
    if (status !== "all") params.set("status", status);
    const { data } = await api.get(`/people?${params}`);
    setData(data);
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, status]);
  useEffect(() => { const t = setTimeout(() => { setPage(1); load(); }, 400); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [q]);

  const canEdit = hasRole("admin", "operator", "reception");

  const save = async () => {
    try {
      if (editId) await api.put(`/people/${editId}`, form);
      else await api.post("/people", form);
      toast.success(editId ? "Pessoa atualizada" : "Pessoa cadastrada");
      setOpen(false); setForm(EMPTY); setEditId(null); load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const edit = (p) => { setForm({ ...EMPTY, ...p }); setEditId(p.id); setOpen(true); };
  const remove = async (id) => {
    if (!window.confirm("Excluir definitivamente? Isto remove a biometria (LGPD).")) return;
    await api.delete(`/people/${id}`);
    toast.success("Pessoa excluída"); load();
  };

  const onPhoto = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, photo: reader.result }));
    reader.readAsDataURL(file);
  };

  const importCsv = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/people/import/csv", fd);
      toast.success(`${data.created} pessoas importadas`);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const totalPages = Math.ceil(data.total / limit) || 1;

  return (
    <div>
      <PageHeader title="Pessoas" subtitle={`${data.total} cadastros · colaboradores e terceiros`}>
        <Button variant="outline" onClick={() => window.open(`${API}/people/export/csv`, "_blank")} data-testid="csv-export-button">
          <Download className="mr-2 h-4 w-4" /> Exportar
        </Button>
        {canEdit && (
          <>
            <input type="file" accept=".csv" ref={fileRef} className="hidden" onChange={importCsv} />
            <Button variant="outline" onClick={() => fileRef.current?.click()} data-testid="csv-import-button">
              <Upload className="mr-2 h-4 w-4" /> Importar CSV
            </Button>
            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setForm(EMPTY); setEditId(null); } }}>
              <DialogTrigger asChild>
                <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" data-testid="person-add-button">
                  <Plus className="mr-2 h-4 w-4" /> Nova pessoa
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle>{editId ? "Editar pessoa" : "Nova pessoa"}</DialogTitle></DialogHeader>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="sm:col-span-1 flex flex-col items-center gap-2">
                    {form.photo ? (
                      <img src={form.photo} alt="" className="aspect-square w-full rounded-lg object-cover" />
                    ) : (
                      <div className="flex aspect-square w-full items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                        <Camera className="h-8 w-8" />
                      </div>
                    )}
                    <input type="file" accept="image/*" ref={webcamFileRef} className="hidden" onChange={onPhoto} />
                    <input type="file" accept="image/*" capture="user" id="webcam-capture" className="hidden" onChange={onPhoto} />
                    <div className="flex w-full gap-2">
                      <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => webcamFileRef.current?.click()} data-testid="person-photo-upload">Foto</Button>
                      <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => document.getElementById("webcam-capture").click()} data-testid="person-webcam-capture">Webcam</Button>
                    </div>
                  </div>
                  <div className="sm:col-span-2 grid grid-cols-2 gap-3">
                    <Field label="Nome" className="col-span-2"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="person-name-input" /></Field>
                    <Field label="Matrícula"><Input value={form.matricula} onChange={(e) => setForm({ ...form, matricula: e.target.value })} data-testid="person-matricula-input" /></Field>
                    <Field label="Documento"><Input value={form.document} onChange={(e) => setForm({ ...form, document: e.target.value })} /></Field>
                    <Field label="Empresa"><Input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></Field>
                    <Field label="Departamento"><Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></Field>
                    <Field label="Cargo"><Input value={form.role_title} onChange={(e) => setForm({ ...form, role_title: e.target.value })} /></Field>
                    <Field label="Tipo">
                      <Select value={form.person_type} onValueChange={(v) => setForm({ ...form, person_type: v })}>
                        <SelectTrigger data-testid="person-type-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="colaborador">Colaborador</SelectItem>
                          <SelectItem value="terceiro">Terceiro</SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Status">
                      <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                        <SelectTrigger data-testid="person-status-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ativo">Ativo</SelectItem>
                          <SelectItem value="inativo">Inativo</SelectItem>
                          <SelectItem value="bloqueado">Bloqueado</SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    <label className="col-span-2 flex items-center gap-2 text-sm text-muted-foreground">
                      <input type="checkbox" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} data-testid="person-consent-checkbox" />
                      Termo de consentimento biométrico (LGPD) assinado
                    </label>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
                  <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={save} data-testid="person-save-button">Salvar</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        )}
      </PageHeader>

      <Card className="border-border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Buscar por nome, matrícula, documento..." value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" data-testid="people-search-input" />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-[160px]" data-testid="people-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos status</SelectItem>
              <SelectItem value="ativo">Ativo</SelectItem>
              <SelectItem value="inativo">Inativo</SelectItem>
              <SelectItem value="bloqueado">Bloqueado</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pessoa</TableHead>
              <TableHead>Matrícula</TableHead>
              <TableHead>Departamento</TableHead>
              <TableHead>Empresa</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>Status</TableHead>
              {canEdit && <TableHead className="text-right">Ações</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((p) => (
              <TableRow key={p.id} data-testid={`person-row-${p.id}`}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    {p.photo ? <img src={p.photo} alt="" className="h-8 w-8 rounded-full object-cover" /> : <div className="h-8 w-8 rounded-full bg-secondary" />}
                    <span className="font-medium">{p.name}</span>
                  </div>
                </TableCell>
                <TableCell className="font-mono text-sm">{p.matricula}</TableCell>
                <TableCell>{p.department}</TableCell>
                <TableCell>{p.company}</TableCell>
                <TableCell className="capitalize">{p.person_type}</TableCell>
                <TableCell>{statusBadge(p.status)}</TableCell>
                {canEdit && (
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" onClick={() => edit(p)} data-testid={`person-edit-${p.id}`}><Pencil className="h-4 w-4" /></Button>
                    {hasRole("admin") && <Button variant="ghost" size="icon" onClick={() => remove(p.id)} data-testid={`person-delete-${p.id}`} className="text-red-400"><Trash2 className="h-4 w-4" /></Button>}
                  </TableCell>
                )}
              </TableRow>
            ))}
            {data.items.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">Nenhuma pessoa encontrada.</TableCell></TableRow>}
          </TableBody>
        </Table>
        <div className="flex items-center justify-between border-t border-border p-4 text-sm">
          <span className="text-muted-foreground">Página {page} de {totalPages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="people-prev-page">Anterior</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)} data-testid="people-next-page">Próxima</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Field({ label, children, className }) {
  return (
    <div className={className}>
      <Label className="mb-1.5 block text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
