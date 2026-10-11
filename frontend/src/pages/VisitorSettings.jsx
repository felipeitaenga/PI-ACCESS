import { useCallback, useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, CategoryMulti } from "@/components/registry/FormBits";
import { Pencil, Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";

const EMPTY = { name: "", category_ids: [], default_hours: "8", require_escort: false, require_photo: false, active: true };
const Toggle = ({ label, checked, onChange, testid }) => (
  <label className="flex items-center gap-2 text-sm"><Switch checked={checked} onCheckedChange={onChange} data-testid={testid} />{label}</label>
);

function TypeDialog({ item, categories, onClose, onSaved }) {
  const [f, setF] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  useEffect(() => { if (item) { setF({ ...EMPTY, ...item, default_hours: String(item.default_hours ?? 8).replace(".", ",") }); setErrors({}); } }, [item]);
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    const body = { ...f, default_hours: String(f.default_hours).replace(",", ".") };
    try {
      if (item.id) await api.put(`/visits/types/${item.id}`, body); else await api.post("/visits/types", body);
      toast.success("Tipo de visita salvo"); onSaved();
    } catch (e) { const d = e.response?.data?.detail; if (d?.fields) setErrors(d.fields); toast.error(formatApiErrorDetail(d)); }
  };
  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="visit-type-dialog">
        <DialogHeader><DialogTitle>{item?.id ? "Editar tipo de visita" : "Novo tipo de visita"}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Field label="Nome" required error={errors.name}><Input value={f.name} onChange={(e) => set("name")(e.target.value)} placeholder="Visita comercial, Entrega…" data-testid="visit-type-name" /></Field>
          <Field label="Categorias de acesso" required error={errors.category_ids}><CategoryMulti categories={categories} value={f.category_ids} onChange={set("category_ids")} /></Field>
          <Field label="Duração padrão (horas)" required error={errors.default_hours} hint="Aceita decimais, ex.: 0,5"><Input value={f.default_hours} onChange={(e) => set("default_hours")(e.target.value.replace(/[^0-9.,]/g, ""))} className="w-32 font-mono" data-testid="visit-type-hours" /></Field>
          <div className="flex flex-wrap gap-5 pt-1">
            <Toggle label="Exigir escort" checked={f.require_escort} onChange={set("require_escort")} testid="visit-type-escort" />
            <Toggle label="Exigir foto" checked={f.require_photo} onChange={set("require_photo")} testid="visit-type-photo" />
            <Toggle label="Ativo" checked={f.active} onChange={set("active")} testid="visit-type-active" />
          </div>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancelar</Button><Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={save} data-testid="visit-type-save">Salvar</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function VisitTypes({ categories }) {
  const [items, setItems] = useState([]);
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => api.get("/visits/types").then(({ data }) => setItems(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const code = (id) => categories.find((c) => c.id === id)?.code || "?";
  const remove = async (t) => {
    if (!window.confirm(`Excluir o tipo "${t.name}"?`)) return;
    await api.delete(`/visits/types/${t.id}`); toast.success("Tipo excluído"); load();
  };
  return (
    <Card className="border-border bg-card p-4" data-testid="visit-types-card">
      <div className="mb-3 flex items-center"><h2 className="flex-1 font-heading text-sm font-bold uppercase tracking-widest">Tipos de visita</h2>
        <Button size="sm" className="bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={() => setEdit({ ...EMPTY })} data-testid="visit-type-new"><Plus className="mr-1 h-4 w-4" />Novo tipo</Button></div>
      <div className="space-y-1.5">
        {items.map((t) => (
          <div key={t.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2" data-testid={`visit-type-row-${t.id}`}>
            <span className="min-w-40 font-medium">{t.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{String(t.default_hours).replace(".", ",")} h</span>
            {t.category_ids.map((c) => <span key={c} className="rounded-full border border-sky-500/40 px-2 text-[11px] text-sky-300">{code(c)}</span>)}
            {t.require_escort && <span className="text-[11px] text-amber-300">escort</span>}
            {t.require_photo && <span className="text-[11px] text-amber-300">foto</span>}
            {!t.active && <span className="text-[11px] text-red-300">inativo</span>}
            <span className="flex-1" />
            <Button size="icon" variant="ghost" onClick={() => setEdit(t)} data-testid={`visit-type-edit-${t.id}`}><Pencil className="h-4 w-4" /></Button>
            <Button size="icon" variant="ghost" className="text-red-400" onClick={() => remove(t)} data-testid={`visit-type-delete-${t.id}`}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
      </div>
      <TypeDialog item={edit} categories={categories} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
    </Card>
  );
}

function DocSettings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/visits/settings").then(({ data }) => setS({ ...data, default_hours: String(data.default_hours).replace(".", ",") })).catch(() => {}); }, []);
  if (!s) return null;
  const set = (k) => (v) => setS((x) => ({ ...x, [k]: v }));
  const save = async () => {
    try { await api.put("/visits/settings", { ...s, default_hours: String(s.default_hours).replace(",", ".") }); toast.success("Configurações salvas"); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  return (
    <Card className="border-border bg-card p-4" data-testid="visitor-doc-settings">
      <h2 className="mb-3 font-heading text-sm font-bold uppercase tracking-widest">Validação de documentos</h2>
      <div className="space-y-3 text-sm">
        <Toggle label="Validar CPF (máscara 000.000.000-00 e dígitos verificadores)" checked={s.validate_cpf} onChange={set("validate_cpf")} testid="setting-validate-cpf" />
        <Toggle label="Validar RG (somente números/X, 5 a 14 caracteres)" checked={s.validate_rg} onChange={set("validate_rg")} testid="setting-validate-rg" />
        <p className="text-xs text-muted-foreground">Passaporte e Outro: texto livre (passaporte em maiúsculas).</p>
        <Field label="Duração padrão geral da visita (horas)" hint="Usada quando o tipo não definir"><Input value={s.default_hours} onChange={(e) => set("default_hours")(e.target.value.replace(/[^0-9.,]/g, ""))} className="w-32 font-mono" data-testid="setting-default-hours" /></Field>
        <Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={save} data-testid="visitor-settings-save"><Save className="mr-2 h-4 w-4" />Salvar</Button>
      </div>
    </Card>
  );
}

export default function VisitorSettings() {
  const [categories, setCategories] = useState([]);
  useEffect(() => { api.get("/access/categories/all").then(({ data }) => setCategories(data.filter((c) => c.enabled !== false))).catch(() => {}); }, []);
  return (
    <div className="space-y-4" data-testid="page-visitor-settings">
      <div><h1 className="font-heading text-2xl font-bold tracking-tight" data-testid="page-title">Visitantes</h1>
        <p className="mt-1 text-sm text-muted-foreground">Tipos de visita, duração padrão e validação de documentos</p></div>
      <div className="grid gap-4 xl:grid-cols-[1fr_420px]"><VisitTypes categories={categories} /><DocSettings /></div>
    </div>
  );
}
