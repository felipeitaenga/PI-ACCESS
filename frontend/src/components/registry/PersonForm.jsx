import { useEffect, useRef, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { LgpdEraseButton } from "@/components/registry/LgpdEraseButton";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PhotoBlock } from "@/components/registry/PhotoBlock";
import { TypeSelector } from "@/components/registry/FormBits";
import { CommonFields, EmployeeFields, ThirdFields, VisitorFields } from "@/components/registry/FormFields";
import { CredentialsSection, DocumentsSection, HistorySection, VehiclesSection } from "@/components/registry/Sections";
import { QuickCompanyDialog } from "@/components/registry/QuickCompanyDialog";
import { SyncStatus } from "@/components/registry/SyncStatus";
import { emptyForm, mapPerson, mapVisitor, personBody, validate, visitPayload } from "@/components/registry/formState";
import { useDocSettings } from "@/components/visits/visitUtils";
import { AlertOctagon, AlertTriangle, Eraser, LogIn, LogOut, Save, SaveAll, Trash2 } from "lucide-react";
import { toast } from "sonner";

const KEEP = ["name", "cpf", "doc_type", "doc_number", "phone", "email", "birth", "photo", "notes"];

export function PersonForm({ request, companies, categories, departments, onSaved, onCompanyCreated, allowedTypes }) {
  const { hasRole } = useAuth();
  const docSettings = useDocSettings();
  const [form, setForm] = useState(() => emptyForm(request?.type || "funcionario"));
  const [snap, setSnap] = useState(() => JSON.stringify(form));
  const [editId, setEditId] = useState(null);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [sync, setSync] = useState(null);
  const [companyDlg, setCompanyDlg] = useState({ open: false, name: "" });
  const nameRef = useRef(null);
  const lastNonce = useRef(request?.kind === "new" && !request.company_id && !request.origin_company && !request.photo ? request.nonce : null);
  const dirty = JSON.stringify(form) !== snap;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const visitor = form.person_type === "visitante";
  const canEdit = hasRole("admin", "operator", "reception");

  const reset = (f, id = null) => {
    setForm(f); setSnap(JSON.stringify(f)); setEditId(id); setErrors({});
    setTimeout(() => nameRef.current?.focus(), 60);
  };
  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setErrors((e) => (e[k] ? { ...e, [k]: undefined } : e)); };

  const run = async (req) => {
    try {
      if (req.kind === "new") {
        const comp = companies.find((c) => c.id === req.company_id);
        reset(emptyForm(req.type, { company_id: req.company_id || "", origin_company: req.origin_company || "", photo: req.photo || "", category_ids: comp?.default_category_id ? [comp.default_category_id] : [] }));
        if (req.photo) toast.info("Foto capturada pelo facial carregada — preencha o cadastro");
      } else if (req.kind === "person") {
        const { data } = await api.get(`/registry/people/${req.id}`);
        reset(mapPerson(data), data.id);
      } else if (req.kind === "visitor") {
        const { data } = await api.get(`/registry/visitors/${req.id}`);
        reset(mapVisitor(data), data.id);
      } else if (req.kind === "lookup") {
        const { data } = await api.get(`/registry/visitors/lookup?document=${encodeURIComponent(req.document)}`);
        if (data.found) { reset(mapVisitor(data.visitor), data.visitor.id); toast.info("Visitante já cadastrado — dados e foto reaproveitados"); }
        else { reset(emptyForm("visitante", { document: req.document })); toast.info("Documento não encontrado — preencha o novo visitante"); }
      }
      setSync(null);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  useEffect(() => {
    if (!request || request.nonce === lastNonce.current) return;
    lastNonce.current = request.nonce;
    if (dirtyRef.current && !window.confirm("Há alterações não salvas neste cadastro. Descartar e continuar?")) return;
    run(request);
  }, [request]); // eslint-disable-line react-hooks/exhaustive-deps

  const changeType = (t) => {
    if (t === form.person_type) return;
    const keep = Object.fromEntries(KEEP.map((k) => [k, form[k]]));
    const comp = companies.find((c) => c.id === form.company_id);
    const keepComp = t !== "visitante" && comp && (t === "terceiro" ? comp.type !== "propria" : true);
    setForm(emptyForm(t, { ...keep, ...(keepComp ? { company_id: form.company_id, category_ids: form.category_ids } : {}) }));
    setErrors({});
  };

  const onDocBlur = async () => {
    if (!visitor || form.visitor_id || form.document.trim().length < 4) return;
    try {
      const { data } = await api.get(`/registry/visitors/lookup?document=${encodeURIComponent(form.document.trim())}`);
      if (!data.found) return;
      const m = mapVisitor(data.visitor);
      setForm((f) => ({ ...m, host_id: f.host_id || m.host_id, host_name: f.host_name || m.host_name, reason: f.reason || m.reason }));
      setEditId(data.visitor.id);
      toast.info("Visitante já cadastrado — dados e foto reaproveitados");
    } catch { /* lookup opcional */ }
  };

  const focusFirst = (e) => { const k = Object.keys(e)[0]; if (k) document.getElementById(`f-${k}`)?.focus(); };

  const save = async (mode = "save") => {
    if (saving || !canEdit) return;
    const e = validate(form, docSettings);
    setErrors(e);
    if (Object.keys(e).length) { toast.error("Verifique os campos destacados"); focusFirst(e); return; }
    setSaving(true); setSync({ status: "sending", devices: [] });
    try {
      let data;
      if (visitor) ({ data } = await api.post("/registry/visits", visitPayload(form, mode === "checkin")));
      else if (editId) ({ data } = await api.put(`/registry/people/${editId}`, personBody(form)));
      else ({ data } = await api.post("/registry/people", personBody(form)));
      setSync({ status: "done", devices: data.sync || [] });
      const fails = (data.sync || []).filter((s) => s.status === "erro").length;
      toast.success(visitor ? (mode === "checkin" ? "Visita salva e check-in realizado" : "Visita salva") : editId ? "Cadastro atualizado" : "Cadastro salvo");
      if (fails) toast.warning(`Falha de sincronização em ${fails} equipamento(s)`);
      onSaved();
      if (mode === "new") {
        reset(emptyForm(form.person_type, visitor ? { origin_company: form.origin_company } : { company_id: form.company_id, category_ids: form.category_ids }));
      } else if (visitor) {
        const r = await api.get(`/registry/visitors/${data.visitor.id}`);
        reset(mapVisitor(r.data), r.data.id);
      } else {
        const r = await api.get(`/registry/people/${data.person.id}`);
        reset(mapPerson(r.data), r.data.id);
      }
    } catch (er) {
      const d = er.response?.data?.detail;
      if (d?.fields) { setErrors(d.fields); focusFirst(d.fields); }
      toast.error(formatApiErrorDetail(d));
      setSync(null);
    } finally { setSaving(false); }
  };
  const saveRef = useRef(save);
  saveRef.current = save;

  useEffect(() => {
    const h = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveRef.current("save"); } };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const clear = () => {
    if (dirty && !window.confirm("Descartar as alterações não salvas?")) return;
    reset(emptyForm(form.person_type)); setSync(null);
  };

  const remove = async () => {
    if (!window.confirm(`Excluir o cadastro de ${form.name}? (exclusão lógica, auditada)`)) return;
    try { await api.delete(`/registry/people/${editId}`); toast.success("Cadastro excluído"); reset(emptyForm(form.person_type)); onSaved(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  const visitAction = async (action) => {
    try {
      await api.post(`/registry/visits/${form.visit_id}/${action}`);
      toast.success(action === "checkin" ? "Check-in realizado" : "Check-out realizado");
      onSaved();
      const r = await api.get(`/registry/visitors/${form.visitor_id}`);
      reset(mapVisitor(r.data), r.data.id);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="person-form">
      <FormHeader form={form} editId={editId} dirty={dirty} set={set} onDelete={hasRole("admin", "operator") ? remove : null} visitAction={visitAction}
        lgpd={hasRole("admin") && editId ? <LgpdEraseButton kind={form.person_type === "visitante" ? "visitor" : "person"} id={form.person_type === "visitante" ? (form.visitor_id || editId) : editId} name={form.name} onDone={() => { reset(emptyForm(form.person_type)); onSaved(); }} /> : null} />
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
        <TypeSelector value={form.person_type} onChange={changeType} disabled={!!editId} allowed={allowedTypes} />
        {form.blacklist && (
          <div className="flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300" data-testid="blacklist-alert">
            <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" /><div><b>VISITANTE EM LISTA NEGRA.</b> {form.blacklist_reason || "Acesso proibido."} Não é possível agendar visita nem fazer check-in.</div>
          </div>
        )}
        {form.status === "vencido" && (
          <div className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300" data-testid="expired-alert">
            <AlertTriangle className="h-4 w-4" />Acesso bloqueado automaticamente: {form.status_reason || "vencimento"}. Renove a validade/documento e salve.
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[150px_1fr]">
          <div className="mx-auto w-[150px] sm:mx-0"><PhotoBlock photo={form.photo} onChange={(v) => set("photo", v)} /></div>
          <CommonFields f={form} set={set} errors={errors} companies={companies} nameRef={nameRef} onDocBlur={onDocBlur} docSettings={docSettings}
            onPick={editId ? null : (r) => run({ kind: r.kind, id: r.id })}
            onCreateCompany={(name) => setCompanyDlg({ open: true, name })} />
        </div>
        <div>
          <h3 className="mb-3 font-heading text-xs font-bold uppercase tracking-widest text-sky-400">{visitor ? "Visita" : "Vínculo e acesso"}</h3>
          {form.person_type === "funcionario" && <EmployeeFields f={form} set={set} errors={errors} categories={categories} departments={departments} />}
          {form.person_type === "terceiro" && <ThirdFields f={form} set={set} errors={errors} categories={categories} />}
          {visitor && <VisitorFields f={form} set={set} errors={errors} categories={categories} />}
        </div>
        {!visitor && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={form.consent} onChange={(e) => set("consent", e.target.checked)} data-testid="f-consent" />
            Termo de consentimento biométrico (LGPD) assinado
          </label>
        )}
        <div className="space-y-2">
          {!visitor && <CredentialsSection f={form} set={set} errors={errors} />}
          {!visitor && <VehiclesSection f={form} set={set} />}
          {!visitor && <DocumentsSection f={form} set={set} errors={errors} defaultOpen={form.person_type === "terceiro"} />}
          {(editId || form.history.length > 0) && <HistorySection f={form} />}
        </div>
      </div>
      <div className="sticky bottom-0 border-t border-border bg-card/95 p-3 backdrop-blur" data-testid="form-footer">
        <SyncStatus sync={sync} />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="mr-auto hidden font-mono text-[11px] text-muted-foreground sm:inline">Ctrl+S salva</span>
          <Button variant="outline" size="sm" onClick={clear} data-testid="form-clear-button"><Eraser className="mr-1.5 h-4 w-4" />Limpar/Novo</Button>
          <Button variant="outline" size="sm" disabled={saving || !canEdit || form.blacklist} onClick={() => save("new")} data-testid="form-save-new-button"><SaveAll className="mr-1.5 h-4 w-4" />Salvar e novo</Button>
          {visitor && <Button variant="outline" size="sm" disabled={saving || !canEdit || form.blacklist || form.visit_status === "presente"} onClick={() => save("checkin")} className="border-emerald-500/40 text-emerald-300" data-testid="form-save-checkin-button"><LogIn className="mr-1.5 h-4 w-4" />Salvar e fazer check-in</Button>}
          <Button size="sm" disabled={saving || !canEdit || form.blacklist} onClick={() => save("save")} className="bg-sky-500 text-slate-950 hover:bg-sky-400" data-testid="form-save-button"><Save className="mr-1.5 h-4 w-4" />{saving ? "Salvando…" : "Salvar"}</Button>
        </div>
      </div>
      <QuickCompanyDialog open={companyDlg.open} initialName={companyDlg.name} categories={categories}
        onOpenChange={(o) => setCompanyDlg((s) => ({ ...s, open: o }))}
        onCreated={(c) => { onCompanyCreated(c); set("company_id", c.id); if (c.default_category_id && !form.category_ids.length) set("category_ids", [c.default_category_id]); }} />
    </div>
  );
}

function FormHeader({ form, editId, dirty, set, onDelete, visitAction, lgpd }) {
  const visitor = form.person_type === "visitante";
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{editId ? "Edição" : "Novo cadastro"}</p>
        <h2 className="truncate font-heading text-base font-bold" data-testid="form-title">{editId ? form.name : visitor ? "Novo visitante" : "Nova pessoa"}</h2>
      </div>
      {dirty && <span className="rounded border border-amber-500/40 px-2 py-0.5 text-[11px] text-amber-300" data-testid="form-dirty-badge">não salvo</span>}
      {visitor && form.visit_status && <span className="rounded border border-sky-500/40 px-2 py-0.5 text-[11px] uppercase text-sky-300" data-testid="form-visit-status">{form.visit_status}</span>}
      {visitor && form.visit_status === "agendado" && !form.blacklist && <Button size="sm" variant="outline" onClick={() => visitAction("checkin")} data-testid="form-checkin-button"><LogIn className="mr-1 h-4 w-4" />Check-in</Button>}
      {visitor && form.visit_status === "presente" && <Button size="sm" variant="outline" onClick={() => visitAction("checkout")} data-testid="form-checkout-button"><LogOut className="mr-1 h-4 w-4" />Check-out</Button>}
      {!visitor && editId && (
        <Select value={form.status === "vencido" ? "vencido" : form.status} onValueChange={(v) => set("status", v)}>
          <SelectTrigger className="h-8 w-[130px]" data-testid="form-status-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ativo">Ativo</SelectItem><SelectItem value="inativo">Inativo</SelectItem>
            <SelectItem value="bloqueado">Bloqueado</SelectItem><SelectItem value="vencido" disabled>Vencido (auto)</SelectItem>
          </SelectContent>
        </Select>
      )}
      {!visitor && editId && onDelete && <Button size="icon" variant="ghost" className="text-red-400" onClick={onDelete} data-testid="form-delete-button"><Trash2 className="h-4 w-4" /></Button>}
      {lgpd}
    </div>
  );
}
