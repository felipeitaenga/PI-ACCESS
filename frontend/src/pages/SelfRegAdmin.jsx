import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { fmtDateTime, fromLocalInput, nowLocal, toLocalInput } from "@/lib/br";
import { addHours, endOfDay, typeHours } from "@/components/visits/visitUtils";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/registry/FormBits";
import { AlertTriangle, Check, Copy, Link2, Mail, Pencil, Plus, Printer, QrCode, RefreshCw, Save, Trash2, X } from "lucide-react";
import { toast } from "sonner";

const sel = "h-9 w-full rounded-md border border-input bg-field px-3 text-sm focus:border-sky-500 focus:outline-none";
const primary = "bg-sky-500 text-slate-950 hover:bg-sky-400";
const err = (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail));
const copy = (t, ok = "Link copiado") => navigator.clipboard?.writeText(t).then(() => toast.success(ok), () => toast.error("Não foi possível copiar"));
const STATUS = {
  pendente: "border-amber-500/40 text-amber-300", processando: "border-sky-500/40 text-sky-300", aprovado: "border-emerald-500/40 text-emerald-300",
  recusado: "border-red-500/40 text-red-300", expirado: "border-slate-500/40 text-slate-400", ativo: "border-sky-500/40 text-sky-300",
  usado: "border-emerald-500/40 text-emerald-300", revogado: "border-red-500/40 text-red-300",
};
const Pill = ({ s }) => <span className={`rounded-full border px-2 text-[11px] ${STATUS[s] || ""}`}>{s}</span>;
const VIA = { anfitriao: "anfitrião", portaria: "portaria", convite: "convite" };

// ---------------- Aguardando liberação ----------------
function EditFields({ e, setE }) {
  const [types, setTypes] = useState([]);
  useEffect(() => { api.get("/visits/types?active=true").then(({ data }) => setTypes(data)).catch(() => {}); }, []);
  const s = (k) => (ev) => setE({ ...e, [k]: ev.target.value });
  return (
    <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 [&_input]:min-w-0" data-testid="selfreg-edit-fields">
      <Field label="Nome completo" className="sm:col-span-2"><Input value={e.name} onChange={s("name")} data-testid="selfreg-edit-name" /></Field>
      <Field label="CPF"><Input value={e.doc_number} onChange={s("doc_number")} data-testid="selfreg-edit-docnumber" /></Field>
      <Field label="Motivo da visita"><Input value={e.visit_reason} onChange={s("visit_reason")} data-testid="selfreg-edit-reason" /></Field>
      <Field label="Empresa do visitante"><Input value={e.visitor_company} onChange={s("visitor_company")} data-testid="selfreg-edit-company" /></Field>
      <Field label="Placa"><Input value={e.plate} onChange={s("plate")} data-testid="selfreg-edit-plate" /></Field>
      <Field label="Telefone"><Input value={e.phone} onChange={s("phone")} data-testid="selfreg-edit-phone" /></Field>
      <Field label="E-mail"><Input value={e.email} onChange={s("email")} data-testid="selfreg-edit-email" /></Field>
      <Field label="Tipo da visita" className="sm:col-span-2"><select className={sel} value={e.visit_type_id} onChange={s("visit_type_id")} data-testid="selfreg-edit-type">{types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
    </div>
  );
}

const toEdit = (r) => ({ name: r.name || "", doc_type: "cpf", doc_number: r.doc_number || "", visitor_company: r.visitor_company || "", visit_reason: r.visit_reason || "",
  plate: r.plate || "", phone: r.phone || "", email: r.email || "", visit_type_id: r.visit_type_id || "" });

function RequestDialog({ id, mode, onClose, onDone }) {
  const { user } = useAuth();
  const [r, setR] = useState(null);
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [just, setJust] = useState("");
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState(null);
  useEffect(() => {
    if (!id) return;
    setR(null); setReason(""); setJust(""); setEdit(null);
    api.get(`/selfreg/requests/${id}`).then(({ data }) => { setR(data); setEnd(toLocalInput(data.end_at)); if (mode === "edit") setEdit(toEdit(data)); }).catch((e) => { err(e); onClose(); });
  }, [id]); // eslint-disable-line
  const saveEdit = async () => {
    const { data } = await api.put(`/selfreg/requests/${id}`, { ...edit, end_at: end !== toLocalInput(r.end_at) ? fromLocalInput(end) : "" });
    setR(data); setEnd(toLocalInput(data.end_at)); setEdit(toEdit(data));
    return data;
  };
  const act = async (kind) => {
    setBusy(true);
    try {
      if (kind === "save") { await saveEdit(); toast.success("Dados atualizados"); return; }
      if (kind === "approve") {
        if (edit) await saveEdit();
        const { data } = await api.post(`/selfreg/requests/${id}/approve`, { end_at: !edit && end !== toLocalInput(r.end_at) ? fromLocalInput(end) : "", blacklist_justification: just });
        const ok = data.sync.filter((s) => s.status === "ok").length;
        toast.success(`Visita liberada${data.sync.length ? ` · facial ${ok}/${data.sync.length}` : ""}`);
      } else {
        await api.post(`/selfreg/requests/${id}/reject`, { reason }); toast.success("Solicitação recusada");
      }
      onDone();
    } catch (e) { err(e); } finally { setBusy(false); }
  };
  const pending = r?.status === "pendente";
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92dvh] max-w-lg overflow-y-auto" data-testid="selfreg-request-dialog">
        <DialogHeader><DialogTitle>Solicitação de visita</DialogTitle></DialogHeader>
        {!r ? <p className="text-sm text-muted-foreground">Carregando…</p> : (
          <div className="space-y-3 text-sm">
            <div className="flex gap-4">
              {(r.photo || r.photo_thumb) && <img src={r.photo || r.photo_thumb} alt="" className="h-40 w-[120px] rounded-md object-cover" />}
              <div className="min-w-0 space-y-0.5">
                <p className="text-base font-semibold">{r.name}</p>
                {r.visitor_company && <p>{r.visitor_company}</p>}
                {r.visit_reason && <p data-testid="selfreg-request-reason">Motivo: {r.visit_reason}</p>}
                <p className="font-mono text-xs text-muted-foreground">{r.doc_type?.toUpperCase()} {r.doc_number}</p>
                {r.email && <p className="text-xs text-muted-foreground">{r.email}{r.email_verified ? " ✓" : ""}</p>}
                {r.phone && <p className="text-xs text-muted-foreground">{r.phone}</p>}
                {r.plate && <p className="text-xs">Placa {r.plate}</p>}
                {r.saved_visitor_id && <p className="text-xs text-emerald-300">Visitante recorrente (cadastro salvo)</p>}
              </div>
            </div>
            <div className="rounded-md border border-border p-2">
              <p><b>{r.host_name}</b> · {r.host_company_name}</p>
              <p className="text-xs text-muted-foreground">{r.visit_type_name} · {fmtDateTime(r.start_at)} até {fmtDateTime(r.end_at)} · via {r.source}</p>
            </div>
            {r.blacklist && (
              <div className="rounded-md border border-red-500/50 bg-red-500/10 p-2 text-red-200">
                <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />Visitante em LISTA NEGRA</p>
                {user?.role === "admin" ? (
                  <Field label="Justificativa para liberar (obrigatória)"><Input value={just} onChange={(e) => setJust(e.target.value)} /></Field>
                ) : <p className="text-xs">Somente o Administrador pode liberar.</p>}
              </div>
            )}
            {pending && edit && <EditFields e={edit} setE={setEdit} />}
            {pending ? (
              <>
                <Field label="Fim da visita" hint="Ajuste se necessário"><Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
                <Field label="Motivo da recusa (opcional)"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Enviado ao visitante" /></Field>
              </>
            ) : (
              <p className="text-muted-foreground">Status: <Pill s={r.status} /> {r.decided_via && `· ${VIA[r.decided_via] || r.decided_via}`} {r.decided_by_name && `(${r.decided_by_name})`} {r.reason && `· ${r.reason}`}</p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
          {pending && <>
            {edit ? <Button variant="outline" disabled={busy} onClick={() => act("save")} data-testid="selfreg-save-edit"><Save className="mr-1 h-4 w-4" />Salvar</Button>
              : <Button variant="outline" disabled={busy} onClick={() => setEdit(toEdit(r))} data-testid="selfreg-edit"><Pencil className="mr-1 h-4 w-4" />Editar</Button>}
            <Button variant="outline" className="text-red-400" disabled={busy} onClick={() => act("reject")} data-testid="selfreg-reject"><X className="mr-1 h-4 w-4" />Recusar</Button>
            <Button className={primary} disabled={busy} onClick={() => act("approve")} data-testid="selfreg-approve"><Check className="mr-1 h-4 w-4" />Aprovar e liberar</Button>
          </>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Requests() {
  const [status, setStatus] = useState("pendente");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(null);
  const [busyId, setBusyId] = useState("");
  const load = useCallback(() => api.get(`/selfreg/requests?status=${status}`).then(({ data }) => setItems(data)).catch(() => {}), [status]);
  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t); }, [load]);
  const quickApprove = async (r) => {
    if (r.blacklist) { setOpen({ id: r.id, mode: "view" }); return; }
    setBusyId(r.id);
    try {
      const { data } = await api.post(`/selfreg/requests/${r.id}/approve`, {});
      const ok = data.sync.filter((s) => s.status === "ok").length;
      toast.success(`${r.name} liberado(a)${data.sync.length ? ` · facial ${ok}/${data.sync.length}` : ""}`);
      load();
    } catch (e) { err(e); load(); } finally { setBusyId(""); }
  };
  return (
    <Card className="border-border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {[["pendente", "Aguardando"], ["aprovado", "Aprovadas"], ["recusado", "Recusadas"], ["expirado", "Expiradas"]].map(([k, l]) => (
          <Button key={k} size="sm" variant={status === k ? "default" : "outline"} className={status === k ? primary : ""} onClick={() => setStatus(k)}>{l}</Button>
        ))}
        <span className="flex-1" />
        <Button size="sm" variant="ghost" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
      </div>
      {items.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">Nenhuma solicitação.</p>}
      <div className="space-y-1.5">
        {items.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-3 rounded-md border border-border px-3 py-2 hover:border-sky-500/50" data-testid={`selfreg-row-${r.id}`}>
            <button type="button" onClick={() => setOpen({ id: r.id, mode: "view" })} className="flex min-w-0 flex-1 items-center gap-3 text-left" data-testid={`selfreg-open-${r.id}`}>
              {r.photo_thumb ? <img src={r.photo_thumb} alt="" className="h-12 w-9 rounded object-cover" /> : <div className="h-12 w-9 rounded bg-secondary" />}
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{r.name} {r.blacklist && <span className="ml-1 rounded bg-red-500/20 px-1 text-[10px] text-red-300">LISTA NEGRA</span>}</p>
                <p className="truncate text-xs text-muted-foreground">{r.host_name} · {r.host_company_name} · {fmtDateTime(r.start_at)} até {fmtDateTime(r.end_at)}</p>
              </div>
              <div className="text-right text-[11px] text-muted-foreground"><Pill s={r.status} /><p>{r.source}</p></div>
            </button>
            {r.status === "pendente" && (
              <div className="flex w-full gap-1.5 sm:w-auto">
                <Button size="sm" className={`${primary} flex-1 sm:flex-none`} disabled={busyId === r.id} onClick={() => quickApprove(r)} data-testid={`selfreg-quick-approve-${r.id}`}><Check className="mr-1 h-4 w-4" />Liberar</Button>
                <Button size="sm" variant="outline" className="flex-1 text-red-400 sm:flex-none" disabled={busyId === r.id} onClick={() => setOpen({ id: r.id, mode: "view" })} data-testid={`selfreg-quick-reject-${r.id}`}><X className="mr-1 h-4 w-4" />Recusar</Button>
                <Button size="sm" variant="outline" className="flex-1 sm:flex-none" disabled={busyId === r.id} onClick={() => setOpen({ id: r.id, mode: "edit" })} data-testid={`selfreg-quick-edit-${r.id}`}><Pencil className="mr-1 h-4 w-4" />Editar</Button>
              </div>
            )}
          </div>
        ))}
      </div>
      <RequestDialog id={open?.id} mode={open?.mode} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load(); }} />
    </Card>
  );
}

// ---------------- Convites ----------------
function HostSelect({ companyId, value, onChange }) {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => {
    if (!companyId) { setItems([]); return undefined; }
    const t = setTimeout(() => api.get(`/registry/people?status=ativo&authorize=true&limit=20&company_id=${companyId}&q=${encodeURIComponent(q)}`)
      .then(({ data }) => setItems(data.items || [])).catch(() => setItems([])), 250);
    return () => clearTimeout(t);
  }, [companyId, q]);
  return (
    <div className="space-y-1">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={companyId ? "Filtrar pelo nome…" : "Escolha a empresa"} disabled={!companyId} />
      <select className={sel} value={value} onChange={(e) => onChange(e.target.value)} disabled={!companyId}>
        <option value="">Selecione o anfitrião…</option>
        {items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    </div>
  );
}

function InviteDialog({ open, companies, onClose, onSaved }) {
  const [types, setTypes] = useState([]);
  const E = { host_company_id: "", host_person_id: "", visit_type_id: "", start_at: nowLocal(), end_at: "", end_manual: false, guest_name: "", guest_email: "", notes: "", auto_approve: true };
  const [f, setF] = useState(E);
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null);
  useEffect(() => {
    if (!open) return;
    setF({ ...E, host_company_id: companies.length === 1 ? companies[0].id : "" }); setErrors({}); setResult(null);
    api.get("/visits/types?active=true").then(({ data }) => setTypes(data)).catch(() => {});
  }, [open]); // eslint-disable-line
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  // fim = início + duração do tipo, até a pessoa alterar manualmente
  useEffect(() => {
    if (f.end_manual || !f.start_at) return;
    const t = types.find((x) => x.id === f.visit_type_id);
    setF((s) => ({ ...s, end_at: addHours(s.start_at, typeHours(t, null)) }));
  }, [f.start_at, f.visit_type_id, f.end_manual, types]);
  const manualEnd = (v) => setF((s) => ({ ...s, end_at: v, end_manual: true }));
  const save = async () => {
    try {
      const { data } = await api.post("/selfreg/invites", { ...f, start_at: fromLocalInput(f.start_at), end_at: fromLocalInput(f.end_at) });
      setResult(data); onSaved();
    } catch (e) { setErrors(e.response?.data?.detail?.fields || {}); err(e); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="invite-dialog">
        <DialogHeader><DialogTitle>Convidar visitante</DialogTitle></DialogHeader>
        {result ? (
          <div className="space-y-3 text-sm">
            <p className="text-emerald-300">Convite criado{result.email_sent ? " e enviado por e-mail" : ""}.</p>
            <p className="text-muted-foreground">Envie a mensagem ao visitante (WhatsApp, e-mail…). O link só aparece agora e vale uma única vez.</p>
            <textarea readOnly value={result.message} rows={11} className="w-full rounded-md border border-input bg-field p-2 font-mono text-xs" data-testid="invite-message" />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => copy(result.message, "Mensagem copiada")} data-testid="invite-copy-message"><Copy className="mr-1 h-4 w-4" />Copiar mensagem</Button>
              <Button variant="outline" onClick={() => copy(result.link)} data-testid="invite-copy-link"><Link2 className="mr-1 h-4 w-4" />Copiar só o link</Button>
              <a className="inline-flex items-center gap-1 self-center text-sky-300 underline" target="_blank" rel="noreferrer" data-testid="invite-whatsapp"
                href={`https://wa.me/?text=${encodeURIComponent(result.message)}`}>Enviar pelo WhatsApp</a>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Empresa visitada" required error={errors.host_company_id} className="sm:col-span-2">
              <select className={sel} value={f.host_company_id} onChange={(e) => setF((s) => ({ ...s, host_company_id: e.target.value, host_person_id: "" }))}>
                <option value="">Selecione…</option>{companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Anfitrião" required error={errors.host_person_id} className="sm:col-span-2"><HostSelect companyId={f.host_company_id} value={f.host_person_id} onChange={set("host_person_id")} /></Field>
            <Field label="Tipo da visita" required error={errors.visit_type_id}>
              <select className={sel} value={f.visit_type_id} onChange={(e) => set("visit_type_id")(e.target.value)}>
                <option value="">Selecione…</option>{types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Início" required error={errors.start_at}><Input type="datetime-local" value={f.start_at} onChange={(e) => set("start_at")(e.target.value)} /></Field>
            <Field label="Fim da visita" required error={errors.end_at} className="sm:col-span-2" hint={f.end_manual ? "Alterado manualmente" : "Calculado pela duração do tipo de visita"}>
              <Input type="datetime-local" value={f.end_at} onChange={(e) => manualEnd(e.target.value)} data-testid="invite-end" />
              <div className="mt-1 flex flex-wrap gap-1">
                {[["+1h", 1], ["+4h", 4]].map(([l, h]) => (
                  <Button key={l} type="button" size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => manualEnd(addHours(f.end_at || f.start_at, h))}>{l}</Button>
                ))}
                <Button type="button" size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => manualEnd(endOfDay(f.start_at))}>Fim do dia</Button>
                {f.end_manual && <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setF((s) => ({ ...s, end_manual: false }))}>Usar duração do tipo</Button>}
              </div>
            </Field>
            <Field label="Nome do visitante" hint="Opcional"><Input value={f.guest_name} onChange={(e) => set("guest_name")(e.target.value)} /></Field>
            <Field label="E-mail do visitante" error={errors.guest_email} hint="Se informado, o convite é enviado por e-mail"><Input type="email" value={f.guest_email} onChange={(e) => set("guest_email")(e.target.value)} /></Field>
            <Field label="Observações" className="sm:col-span-2" hint="Vai na mensagem do convite (ex.: trazer EPI, portaria 2)"><Input value={f.notes} maxLength={300} onChange={(e) => set("notes")(e.target.value)} data-testid="invite-notes" /></Field>
            <label className="flex items-start gap-2 text-sm sm:col-span-2"><Switch checked={f.auto_approve} onCheckedChange={set("auto_approve")} />
              <span>Liberar automaticamente quando o visitante concluir o cadastro<span className="block text-xs text-muted-foreground">Desligado: a solicitação vai para aprovação. Lista negra sempre vai para a portaria.</span></span></label>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
          {!result && <Button className={primary} onClick={save} data-testid="invite-save"><Mail className="mr-1 h-4 w-4" />Criar convite</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Invites({ companies }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const load = useCallback(() => api.get("/selfreg/invites").then(({ data }) => setItems(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const revoke = async (i) => {
    if (!window.confirm("Revogar este convite?")) return;
    try { await api.delete(`/selfreg/invites/${i.id}`); toast.success("Convite revogado"); load(); } catch (e) { err(e); }
  };
  return (
    <Card className="border-border bg-card p-4">
      <div className="mb-3 flex items-center"><h2 className="flex-1 font-heading text-sm font-bold uppercase tracking-widest">Convites</h2>
        <Button size="sm" className={primary} onClick={() => setOpen(true)} data-testid="invite-new"><Plus className="mr-1 h-4 w-4" />Novo convite</Button></div>
      {items.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">Nenhum convite.</p>}
      <div className="space-y-1.5">
        {items.map((i) => (
          <div key={i.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{i.guest_name || i.guest_email || "Visitante"} → {i.host_name}</p>
              <p className="truncate text-xs text-muted-foreground">{i.host_company_name} · {fmtDateTime(i.start_at)} até {fmtDateTime(i.end_at)} · por {i.created_by_name || i.created_by}{i.auto_approve ? " · liberação automática" : ""}</p>
            </div>
            <Pill s={i.status} />
            {i.status === "ativo" && <Button size="icon" variant="ghost" className="text-red-400" onClick={() => revoke(i)}><Trash2 className="h-4 w-4" /></Button>}
          </div>
        ))}
      </div>
      <InviteDialog open={open} companies={companies} onClose={() => setOpen(false)} onSaved={load} />
    </Card>
  );
}

// ---------------- Links públicos ----------------
const esc = (t) => String(t || "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
function printQr(name, link, qr) {
  const company = esc(name), url = esc(link);
  const w = window.open("", "_blank", "width=600,height=800");
  if (!w) return;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${company}</title><style>
    body{font-family:Arial,sans-serif;text-align:center;padding:40px;color:#0f172a}h1{font-size:30px;margin:0 0 8px}
    h2{font-size:20px;font-weight:normal;margin:0 0 24px;color:#334155}img{width:340px;height:340px}
    ol{text-align:left;display:inline-block;font-size:17px;line-height:1.7}p.u{font-size:12px;color:#64748b;word-break:break-all}</style></head>
    <body><h1>Visitante? Faça seu cadastro</h1>${company ? `<h2>${company}</h2>` : "<h2>&nbsp;</h2>"}<img src="${qr}" alt="QR"/>
    <ol><li>Aponte a câmera do celular para o QR Code</li><li>Preencha seus dados e tire uma selfie</li><li>Aguarde a aprovação e entre pelo leitor facial</li></ol>
    <p class="u">${url}</p><script>window.onload=function(){window.print()}</script></body></html>`);
  w.document.close();
}

function CompanyLink({ c, types, onChange }) {
  const [qr, setQr] = useState("");
  const [vt, setVt] = useState(c.selfreg_visit_type_id || "");
  useEffect(() => { setVt(c.selfreg_visit_type_id || ""); }, [c.selfreg_visit_type_id]);
  useEffect(() => { if (c.link && c.selfreg_enabled) QRCode.toDataURL(c.link, { width: 600, margin: 1 }).then(setQr).catch(() => setQr("")); else setQr(""); }, [c.link, c.selfreg_enabled]);
  const save = async (body) => {
    try { await api.put(`/selfreg/companies/${c.id}`, { enabled: c.selfreg_enabled, visit_type_id: vt, ...body }); onChange(); toast.success("Link atualizado"); }
    catch (e) { err(e); }
  };
  const allowed = c.allowed_visit_type_ids?.length ? types.filter((t) => c.allowed_visit_type_ids.includes(t.id)) : types;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-border p-3" data-testid={`selfreg-company-${c.id}`}>
      {qr ? <img src={qr} alt="QR" className="h-20 w-20 rounded bg-white p-1" /> : <div className="flex h-20 w-20 items-center justify-center rounded bg-secondary"><QrCode className="h-8 w-8 text-muted-foreground" /></div>}
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center gap-2"><span className="font-medium">{c.name}</span>
          <label className="ml-auto flex items-center gap-2 text-xs"><Switch checked={!!c.selfreg_enabled} onCheckedChange={(v) => save({ enabled: v })} />Ativo</label></div>
        <div className="flex flex-wrap items-center gap-2">
          <select className={`${sel} max-w-56`} value={vt} onChange={(e) => setVt(e.target.value)} onBlur={() => vt !== (c.selfreg_visit_type_id || "") && save({ visit_type_id: vt })}>
            <option value="">Tipo de visita do link…</option>{allowed.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          {c.link && c.selfreg_enabled && <>
            <Button size="sm" variant="outline" onClick={() => copy(c.link)}><Link2 className="mr-1 h-4 w-4" />Copiar link</Button>
            <Button size="sm" variant="outline" onClick={() => printQr(c.name, c.link, qr)} disabled={!qr}><Printer className="mr-1 h-4 w-4" />Imprimir QR</Button>
            <Button size="sm" variant="ghost" title="Gerar novo link (o anterior para de funcionar)" onClick={() => window.confirm("Gerar um novo link? O link e o QR atuais deixam de funcionar.") && save({ regenerate: true })}><RefreshCw className="h-4 w-4" /></Button>
          </>}
        </div>
        {c.link && c.selfreg_enabled && <p className="truncate font-mono text-[11px] text-muted-foreground">{c.link}</p>}
      </div>
    </div>
  );
}

function SiteLink({ onChange }) {
  const [d, setD] = useState(null);
  const [qr, setQr] = useState("");
  const load = useCallback(() => api.get("/selfreg/site-link").then(({ data }) => setD(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (d?.link && d.enabled) QRCode.toDataURL(d.link, { width: 600, margin: 1 }).then(setQr).catch(() => setQr("")); else setQr(""); }, [d?.link, d?.enabled]);
  if (!d) return null;
  const save = async (body) => {
    try { setD((await api.put("/selfreg/site-link", { enabled: d.enabled, ...body })).data); toast.success("QR único atualizado"); onChange?.(); } catch (e) { err(e); }
  };
  return (
    <Card className="border-sky-500/40 bg-card p-4" data-testid="selfreg-site-link">
      <div className="flex flex-wrap items-start gap-4">
        {qr ? <img src={qr} alt="QR" className="h-28 w-28 rounded bg-white p-1" /> : <div className="flex h-28 w-28 items-center justify-center rounded bg-secondary"><QrCode className="h-10 w-10 text-muted-foreground" /></div>}
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <h2 className="flex-1 font-heading text-sm font-bold uppercase tracking-widest">QR único do local</h2>
            <label className="flex items-center gap-2 text-xs"><Switch checked={d.enabled} onCheckedChange={(v) => save({ enabled: v })} />Ativo</label>
          </div>
          <p className="text-xs text-muted-foreground">Um só QR na recepção: o visitante escolhe a empresa e depois o anfitrião. Aparecem só as empresas ativas abaixo ({d.companies.length}).</p>
          {d.enabled && d.link && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => copy(d.link)}><Link2 className="mr-1 h-4 w-4" />Copiar link</Button>
              <Button size="sm" variant="outline" onClick={() => printQr("", d.link, qr)} disabled={!qr}><Printer className="mr-1 h-4 w-4" />Imprimir QR</Button>
              <Button size="sm" variant="ghost" title="Gerar novo link" onClick={() => window.confirm("Gerar um novo QR único? O atual deixa de funcionar.") && save({ regenerate: true })}><RefreshCw className="h-4 w-4" /></Button>
            </div>
          )}
          {d.enabled && d.companies.length === 0 && <p className="text-xs text-amber-300">Ative ao menos uma empresa abaixo (com tipo de visita).</p>}
          {d.enabled && d.link && <p className="truncate font-mono text-[11px] text-muted-foreground">{d.link}</p>}
        </div>
      </div>
    </Card>
  );
}

function PublicLinks({ companies, reload, isAdmin }) {
  const [types, setTypes] = useState([]);
  const [tick, setTick] = useState(0);
  useEffect(() => { api.get("/visits/types?active=true").then(({ data }) => setTypes(data)).catch(() => {}); }, []);
  const changed = () => { reload(); setTick((t) => t + 1); };
  return (
    <div className="space-y-4">
      {isAdmin && <SiteLink key={tick} />}
      <Card className="border-border bg-card p-4">
        <h2 className="mb-1 font-heading text-sm font-bold uppercase tracking-widest">Empresas no autocadastro</h2>
        <p className="mb-3 text-xs text-muted-foreground">Ative a empresa e escolha o tipo de visita. Ela passa a aparecer no QR único e ganha também um QR próprio (para a recepção dela). O visitante busca o anfitrião pelo nome (no máximo 3 resultados) e a visita só é liberada após aprovação.</p>
        <div className="space-y-2">{companies.map((c) => <CompanyLink key={c.id} c={c} types={types} onChange={changed} />)}</div>
      </Card>
    </div>
  );
}

// ---------------- Configurações ----------------
function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/selfreg/settings").then(({ data }) => setS(data)).catch(() => {}); }, []);
  if (!s) return null;
  const set = (k) => (v) => setS((x) => ({ ...x, [k]: v }));
  const num = (k) => <Input value={s[k]} onChange={(e) => set(k)(e.target.value.replace(/\D/g, ""))} className="w-28 font-mono" />;
  const save = async () => { try { setS(await api.put("/selfreg/settings", s).then((r) => r.data)); toast.success("Configurações salvas"); } catch (e) { err(e); } };
  return (
    <Card className="space-y-4 border-border bg-card p-4">
      {!s.email_enabled && <p className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm text-amber-200"><AlertTriangle className="h-4 w-4 shrink-0" />E-mail (SMTP) não configurado neste servidor: sem confirmação por código, sem avisos e sem "lembrar cadastro". As solicitações aparecem só na fila da portaria.</p>}
      <div className="flex flex-wrap gap-6 text-sm">
        <label className="flex items-center gap-2"><Switch checked={s.enabled} onCheckedChange={set("enabled")} />Autocadastro habilitado</label>
        <label className="flex items-center gap-2"><Switch checked={s.require_otp} onCheckedChange={set("require_otp")} />Confirmar e-mail com código</label>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Validade do convite (horas)">{num("invite_hours")}</Field>
        <Field label="Prazo para aprovar (horas)">{num("approval_hours")}</Field>
        <Field label="Agendar com até (dias)">{num("max_days_ahead")}</Field>
        <Field label="Apagar face do visitante após (dias)" hint="Contados do fim da última visita · 0 = nunca">{num("visitor_retention_days")}</Field>
        <Field label="Visitante recorrente: apagar após (meses sem visita)">{num("recurring_months")}</Field>
      </div>
      <Field label="Texto de consentimento (LGPD)"><Textarea rows={6} value={s.lgpd_text} onChange={(e) => set("lgpd_text")(e.target.value)} /></Field>
      <Button className={primary} onClick={save}><Save className="mr-2 h-4 w-4" />Salvar</Button>
    </Card>
  );
}

export default function SelfRegAdmin() {
  const { user } = useAuth();
  const [companies, setCompanies] = useState([]);
  const loadCompanies = useCallback(() => api.get("/selfreg/companies").then(({ data }) => setCompanies(data)).catch(() => {}), []);
  useEffect(() => { loadCompanies(); }, [loadCompanies]);
  const canLinks = ["admin", "company_manager"].includes(user?.role);
  return (
    <div className="space-y-4" data-testid="page-selfreg">
      <div><h1 className="font-heading text-2xl font-bold tracking-tight">Autocadastro de visitantes</h1>
        <p className="mt-1 text-sm text-muted-foreground">Solicitações pelo link público e convites individuais. Vale a primeira resposta: anfitrião ou portaria.</p></div>
      <Tabs defaultValue="requests">
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="requests">Aguardando liberação</TabsTrigger>
          <TabsTrigger value="invites">Convites</TabsTrigger>
          {canLinks && <TabsTrigger value="links">Links públicos</TabsTrigger>}
          {user?.role === "admin" && <TabsTrigger value="settings">Configurações</TabsTrigger>}
        </TabsList>
        <TabsContent value="requests"><Requests /></TabsContent>
        <TabsContent value="invites"><Invites companies={companies} /></TabsContent>
        {canLinks && <TabsContent value="links"><PublicLinks companies={companies} reload={loadCompanies} isAdmin={user?.role === "admin"} /></TabsContent>}
        {user?.role === "admin" && <TabsContent value="settings"><Settings /></TabsContent>}
      </Tabs>
    </div>
  );
}
