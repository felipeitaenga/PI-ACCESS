import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { fmtDateTime, fromLocalInput, toLocalInput } from "@/lib/br";
import { InviteWizard } from "@/components/selfreg/InviteWizard";
import { downloadPoster, shareLink } from "@/components/selfreg/poster";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/registry/FormBits";
import { AlertTriangle, Check, FileDown, Link2, Pencil, Plus, QrCode, RefreshCw, Save, Share2, Trash2, X } from "lucide-react";
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
      <DialogContent className="max-w-lg" data-testid="selfreg-request-dialog">
        <DialogHeader><DialogTitle>Solicitação de visita</DialogTitle></DialogHeader>
        {!r ? <p className="text-sm text-muted-foreground">Carregando…</p> : (
          <div className="space-y-3 text-sm">
            <div className="flex gap-4">
              {(r.photo || r.photo_thumb) && <img src={r.photo || r.photo_thumb} alt="" className="h-40 w-[120px] rounded-md object-cover" title="Selfie enviada agora" />}
              {r.existing_photo && <img src={r.existing_photo} alt="" className="h-40 w-[120px] rounded-md object-cover ring-2 ring-amber-400" title="Foto do cadastro existente" />}
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
            {r.existing_photo !== undefined && (
              <p className="flex gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-2 text-xs text-amber-200" data-testid="selfreg-identity-check">
                <AlertTriangle className="h-4 w-4 shrink-0" />Este CPF já está cadastrado{r.existing_name ? ` (${r.existing_name})` : ""} e quem enviou não confirmou ser o dono. Compare a selfie com a foto do cadastro (borda amarela) antes de liberar; ao aprovar, nome e foto do cadastro serão substituídos.
              </p>
            )}
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

function QuickActions({ r, busy, onApprove, onOpen }) {
  if (r.status !== "pendente") return null;
  return (
    <div className="grid grid-cols-3 gap-1.5 sm:flex">
      <Button className={`${primary} h-12 sm:h-8`} disabled={busy} onClick={() => onApprove(r)} data-testid={`selfreg-quick-approve-${r.id}`}><Check className="mr-1 h-4 w-4" />Liberar</Button>
      <Button variant="outline" className="h-12 text-red-400 sm:h-8" disabled={busy} onClick={() => onOpen({ id: r.id, mode: "view" })} data-testid={`selfreg-quick-reject-${r.id}`}><X className="mr-1 h-4 w-4" />Recusar</Button>
      <Button variant="outline" className="h-12 sm:h-8" disabled={busy} onClick={() => onOpen({ id: r.id, mode: "edit" })} data-testid={`selfreg-quick-edit-${r.id}`}><Pencil className="mr-1 h-4 w-4" />Editar</Button>
    </div>
  );
}

const Thumb = ({ r, cls }) => (r.photo_thumb ? <img src={r.photo_thumb} alt="" className={`${cls} rounded-md object-cover`} /> : <div className={`${cls} rounded-md bg-secondary`} />);
const BL = ({ r }) => (r.blacklist ? <span className="ml-1 rounded bg-red-500/20 px-1 text-[10px] text-red-300">LISTA NEGRA</span> : null);

function RequestCard({ r, busy, onApprove, onOpen }) {
  return (
    <div className="space-y-3 rounded-xl border border-border p-3" data-testid={`selfreg-row-${r.id}`}>
      <button type="button" onClick={() => onOpen({ id: r.id, mode: "view" })} className="flex w-full gap-3 text-left" data-testid={`selfreg-open-${r.id}`}>
        <Thumb r={r} cls="h-20 w-16 shrink-0" />
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="truncate font-semibold leading-tight">{r.name}<BL r={r} /></p>
          <p className="truncate text-sm text-muted-foreground">{r.host_name} · {r.host_company_name}</p>
          <p className="text-xs text-muted-foreground">{fmtDateTime(r.start_at)} até {fmtDateTime(r.end_at)}</p>
          {r.visit_reason && <p className="truncate text-xs">Motivo: {r.visit_reason}</p>}
          <p className="pt-0.5"><Pill s={r.status} /> <span className="text-[11px] text-muted-foreground">{r.source}</span></p>
        </div>
      </button>
      <QuickActions r={r} busy={busy} onApprove={onApprove} onOpen={onOpen} />
    </div>
  );
}

function RequestTable({ items, busyId, onApprove, onOpen }) {
  return (
    <table className="hidden w-full text-sm sm:table" data-testid="selfreg-table">
      <thead><tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
        <th className="py-2 pr-2">Visitante</th><th className="pr-2">Anfitrião / empresa</th><th className="pr-2">Horário</th><th className="pr-2">Status</th><th /></tr></thead>
      <tbody>{items.map((r) => (
        <tr key={r.id} className="border-b border-border/60 hover:bg-secondary/40" data-testid={`selfreg-trow-${r.id}`}>
          <td className="py-2 pr-2"><button type="button" onClick={() => onOpen({ id: r.id, mode: "view" })} className="flex items-center gap-3 text-left" data-testid={`selfreg-topen-${r.id}`}>
            <Thumb r={r} cls="h-12 w-9 shrink-0" /><span><span className="font-medium">{r.name}</span><BL r={r} />{r.visit_reason && <span className="block text-xs text-muted-foreground">{r.visit_reason}</span>}</span></button></td>
          <td className="pr-2">{r.host_name}<span className="block text-xs text-muted-foreground">{r.host_company_name}</span></td>
          <td className="pr-2 text-xs">{fmtDateTime(r.start_at)}<span className="block text-muted-foreground">até {fmtDateTime(r.end_at)}</span></td>
          <td className="pr-2"><Pill s={r.status} /><span className="block text-[11px] text-muted-foreground">{r.source}</span></td>
          <td className="py-2"><div className="flex justify-end"><QuickActions r={r} busy={busyId === r.id} onApprove={onApprove} onOpen={onOpen} /></div></td>
        </tr>
      ))}</tbody>
    </table>
  );
}

function Requests() {
  const [status, setStatus] = useState("pendente");
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(null);
  const [busyId, setBusyId] = useState("");
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => api.get(`/selfreg/requests?status=${status}`).then(({ data }) => { setItems(data); setFailed(false); }).catch(() => { setFailed(true); setItems((s) => s || []); }), [status]);
  useEffect(() => { setItems(null); load(); const t = setInterval(load, 20000); return () => clearInterval(t); }, [load]);
  const quickApprove = async (r) => {
    if (r.blacklist || (r.doc_known && !r.owner_verified)) { setOpen({ id: r.id, mode: "view" }); return; }
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
          <Button key={k} size="sm" variant={status === k ? "default" : "outline"} className={`h-10 sm:h-8 ${status === k ? primary : ""}`} onClick={() => setStatus(k)} data-testid={`selfreg-filter-${k}`}>{l}</Button>
        ))}
        <span className="flex-1" />
        <Button size="sm" variant="ghost" className="h-10 w-10 sm:h-8 sm:w-8" onClick={load} aria-label="Atualizar"><RefreshCw className="h-4 w-4" /></Button>
      </div>
      {items === null && <div className="space-y-2" data-testid="selfreg-loading">{[0, 1, 2].map((i) => <div key={i} className="h-20 rounded-xl bg-secondary/60 motion-safe:animate-pulse" />)}</div>}
      {failed && <p className="mb-2 flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300" data-testid="selfreg-load-error"><AlertTriangle className="h-4 w-4" />Não foi possível carregar as solicitações.<Button size="sm" variant="outline" className="ml-auto h-9" onClick={load}>Tentar de novo</Button></p>}
      {items?.length === 0 && !failed && <p className="py-10 text-center text-sm text-muted-foreground" data-testid="selfreg-empty">Nenhuma solicitação {status === "pendente" ? "aguardando liberação" : "nesta lista"}.</p>}
      {!!items?.length && <>
        <div className="space-y-2 sm:hidden">{items.map((r) => <RequestCard key={r.id} r={r} busy={busyId === r.id} onApprove={quickApprove} onOpen={setOpen} />)}</div>
        <RequestTable items={items} busyId={busyId} onApprove={quickApprove} onOpen={setOpen} />
      </>}
      <RequestDialog id={open?.id} mode={open?.mode} onClose={() => setOpen(null)} onDone={() => { setOpen(null); load(); }} />
    </Card>
  );
}

// ---------------- Convites ----------------

function Invites({ tick, onNew }) {
  const [items, setItems] = useState(null);
  const load = useCallback(() => api.get("/selfreg/invites").then(({ data }) => setItems(data)).catch(() => setItems([])), []);
  useEffect(() => { load(); }, [load, tick]);
  const revoke = async (i) => {
    if (!window.confirm("Revogar este convite?")) return;
    try { await api.delete(`/selfreg/invites/${i.id}`); toast.success("Convite revogado"); load(); } catch (e) { err(e); }
  };
  return (
    <Card className="border-border bg-card p-4">
      <div className="mb-3 flex items-center"><h2 className="flex-1 font-heading text-sm font-bold uppercase tracking-widest">Convites</h2>
        <Button size="sm" className={`${primary} hidden sm:inline-flex`} onClick={onNew} data-testid="invite-new"><Plus className="mr-1 h-4 w-4" />Novo convite</Button></div>
      {items === null && <div className="space-y-2">{[0, 1].map((i) => <div key={i} className="h-14 rounded-md bg-secondary/60 motion-safe:animate-pulse" />)}</div>}
      {items?.length === 0 && <p className="py-10 text-center text-sm text-muted-foreground" data-testid="invites-empty">Nenhum convite. Toque em "Convidar" para criar o primeiro.</p>}
      <div className="space-y-1.5">
        {(items || []).map((i) => (
          <div key={i.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm" data-testid={`invite-row-${i.id}`}>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{i.guest_name || i.guest_email || "Visitante"} → {i.host_name}</p>
              <p className="truncate text-xs text-muted-foreground">{i.host_company_name} · {fmtDateTime(i.start_at)} até {fmtDateTime(i.end_at)} · por {i.created_by_name || i.created_by}</p>
            </div>
            <Pill s={i.status} />
            {i.status === "ativo" && <Button size="icon" variant="ghost" className="h-11 w-11 text-red-400 sm:h-9 sm:w-9" onClick={() => revoke(i)} aria-label="Revogar convite"><Trash2 className="h-4 w-4" /></Button>}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ---------------- Links públicos ----------------
function LinkActions({ name, link, qr, onRegen, regenMsg }) {
  return (
    <div className="grid grid-cols-2 gap-2 pb-16 sm:flex sm:flex-wrap sm:pb-0">
      <Button size="sm" variant="outline" className="h-11 sm:h-8" onClick={() => copy(link)} data-testid="link-copy"><Link2 className="mr-1 h-4 w-4" />Copiar link</Button>
      <Button size="sm" variant="outline" className="h-11 sm:h-8" onClick={() => shareLink(name, link)} data-testid="link-share"><Share2 className="mr-1 h-4 w-4" />Compartilhar</Button>
      <Button size="sm" variant="outline" className="h-11 sm:h-8" disabled={!qr} onClick={() => downloadPoster(name, link, qr).catch(() => toast.error("Não foi possível gerar o cartaz"))} data-testid="link-poster"><FileDown className="mr-1 h-4 w-4" />Baixar cartaz</Button>
      <Button size="sm" variant="ghost" className="h-11 sm:h-8" title="Gerar novo link (o anterior para de funcionar)" onClick={() => window.confirm(regenMsg) && onRegen()} data-testid="link-regenerate"><RefreshCw className="mr-1 h-4 w-4 sm:mr-0" /><span className="sm:hidden">Novo link</span></Button>
    </div>
  );
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
          {c.link && c.selfreg_enabled && <LinkActions name={c.name} link={c.link} qr={qr} onRegen={() => save({ regenerate: true })} regenMsg="Gerar um novo link? O link e o QR atuais deixam de funcionar." />}
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
          {d.enabled && d.link && <LinkActions name="" link={d.link} qr={qr} onRegen={() => save({ regenerate: true })} regenMsg="Gerar um novo QR único? O atual deixa de funcionar." />}
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
  const [inviting, setInviting] = useState(false);
  const [tab, setTab] = useState("requests");
  const [tick, setTick] = useState(0);
  const newInvite = () => { setTab("invites"); setInviting(true); };
  return (
    <div className="space-y-4 pb-20 sm:pb-0" data-testid="page-selfreg">
      <div><h1 className="font-heading text-2xl font-bold tracking-tight">Autocadastro de visitantes</h1>
        <p className="mt-1 text-sm text-muted-foreground">Solicitações pelo link público e convites individuais. Vale a primeira resposta: anfitrião ou portaria.</p></div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto w-full flex-wrap justify-start sm:w-auto [&>button]:min-h-10">
          <TabsTrigger value="requests">Aguardando liberação</TabsTrigger>
          <TabsTrigger value="invites">Convites</TabsTrigger>
          {canLinks && <TabsTrigger value="links">Links públicos</TabsTrigger>}
          {user?.role === "admin" && <TabsTrigger value="settings">Configurações</TabsTrigger>}
        </TabsList>
        <TabsContent value="requests"><Requests /></TabsContent>
        <TabsContent value="invites"><Invites tick={tick} onNew={newInvite} /></TabsContent>
        {canLinks && <TabsContent value="links"><PublicLinks companies={companies} reload={loadCompanies} isAdmin={user?.role === "admin"} /></TabsContent>}
        {user?.role === "admin" && <TabsContent value="settings"><Settings /></TabsContent>}
      </Tabs>
      <Button onClick={newInvite} className={`${primary} fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-4 z-40 h-14 rounded-full px-6 text-base shadow-lg shadow-black/40 sm:hidden`} data-testid="invite-fab"><Plus className="mr-1 h-5 w-5" />Convidar</Button>
      <InviteWizard open={inviting} companies={companies} onClose={() => setInviting(false)} onSaved={() => setTick((t) => t + 1)} />
    </div>
  );
}
