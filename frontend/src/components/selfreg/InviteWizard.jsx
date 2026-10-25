import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, formatApiErrorDetail } from "@/lib/api";
import { fromLocalInput, nowLocal } from "@/lib/br";
import { addHours, endOfDay, typeHours } from "@/components/visits/visitUtils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/registry/FormBits";
import { ArrowLeft, Copy, Link2, Mail, MessageCircle } from "lucide-react";
import { toast } from "sonner";

const sel = "h-11 w-full rounded-md border border-input bg-field px-3 text-base sm:h-9 sm:text-sm focus:border-sky-500 focus:outline-none";
const primary = "bg-sky-500 text-slate-950 hover:bg-sky-400";
const big = "h-12 w-full justify-center text-base";
const copy = (t, ok) => navigator.clipboard?.writeText(t).then(() => toast.success(ok), () => toast.error("Não foi possível copiar"));
const STEPS = ["Quem convida", "Quando", "Visitante"];
const EMPTY = { host_company_id: "", host_person_id: "", visit_type_id: "", start_at: "", end_at: "", end_manual: false, guest_name: "", guest_email: "", notes: "" };
const FIELD_STEP = { host_company_id: 0, host_person_id: 0, visit_type_id: 0, start_at: 1, end_at: 1, guest_email: 2 };

function HostSelect({ companyId, value, onChange }) {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => {
    if (!companyId) { setItems([]); return undefined; }
    const t = setTimeout(() => api.get(`/registry/people?status=ativo&authorize=true&limit=20&company_id=${companyId}&q=${encodeURIComponent(q)}`)
      .then(({ data }) => { const l = data.items || []; setItems(l); if (l.length === 1 && !q) onChange(l[0].id); }).catch(() => setItems([])), 250);
    return () => clearTimeout(t);
  }, [companyId, q]); // eslint-disable-line
  return (
    <div className="space-y-1.5">
      <Input className="h-11 text-base sm:h-9 sm:text-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder={companyId ? "Filtrar pelo nome…" : "Escolha a empresa"} disabled={!companyId} data-testid="invite-host-filter" />
      <select className={sel} value={value} onChange={(e) => onChange(e.target.value)} disabled={!companyId} data-testid="invite-host-select">
        <option value="">Selecione o anfitrião…</option>
        {items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    </div>
  );
}

function StepDots({ step }) {
  return (
    <div className="flex gap-1.5" data-testid="invite-steps">
      {STEPS.map((s, i) => <div key={s} className={`h-1.5 flex-1 rounded-full transition-colors duration-200 ${i <= step ? "bg-sky-500" : "bg-secondary"}`} />)}
    </div>
  );
}

function Result({ result }) {
  const [qr, setQr] = useState("");
  useEffect(() => { QRCode.toDataURL(result.link, { width: 480, margin: 1 }).then(setQr).catch(() => setQr("")); }, [result.link]);
  return (
    <div className="space-y-3 text-sm" data-testid="invite-result">
      <p className="text-base font-semibold text-emerald-300">Convite criado{result.email_sent ? " e enviado por e-mail" : ""}.</p>
      <p className="text-muted-foreground">O link só aparece agora e vale uma única vez.</p>
      <a className={`inline-flex items-center gap-2 rounded-md bg-emerald-500 font-semibold text-slate-950 hover:bg-emerald-400 ${big}`} target="_blank" rel="noreferrer" data-testid="invite-whatsapp"
        href={`https://wa.me/?text=${encodeURIComponent(result.message)}`}><MessageCircle className="h-5 w-5" />Enviar pelo WhatsApp</a>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="outline" className="h-12" onClick={() => copy(result.message, "Mensagem copiada")} data-testid="invite-copy-message"><Copy className="mr-1 h-4 w-4" />Copiar mensagem</Button>
        <Button variant="outline" className="h-12" onClick={() => copy(result.link, "Link copiado")} data-testid="invite-copy-link"><Link2 className="mr-1 h-4 w-4" />Copiar link</Button>
      </div>
      {qr && <div className="flex flex-col items-center gap-1 rounded-lg border border-border p-3"><img src={qr} alt="QR Code do convite" className="h-52 w-52 rounded bg-white p-2" data-testid="invite-qr" /><p className="text-xs text-muted-foreground">Mostre para o visitante ler com a câmera</p></div>}
      <details className="rounded-md border border-border p-2"><summary className="cursor-pointer py-1 text-xs text-muted-foreground">Ver mensagem</summary>
        <textarea readOnly value={result.message} rows={10} className="mt-2 w-full rounded-md border border-input bg-field p-2 font-mono text-xs" data-testid="invite-message" /></details>
    </div>
  );
}

export function InviteWizard({ open, companies, onClose, onSaved }) {
  const [types, setTypes] = useState(null);
  const [f, setF] = useState(EMPTY);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setF({ ...EMPTY, start_at: nowLocal(), host_company_id: companies.length === 1 ? companies[0].id : "" }); setErrors({}); setResult(null); setStep(0); setTypes(null);
    api.get("/visits/types?active=true").then(({ data }) => {
      setTypes(data);
      if (data.length === 1) setF((s) => ({ ...s, visit_type_id: data[0].id }));
    }).catch(() => setTypes([]));
  }, [open]); // eslint-disable-line
  useEffect(() => {
    if (open && companies.length === 1) setF((s) => (s.host_company_id ? s : { ...s, host_company_id: companies[0].id }));
  }, [companies, open]);
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  useEffect(() => {
    if (f.end_manual || !f.start_at) return;
    const t = (types || []).find((x) => x.id === f.visit_type_id);
    setF((s) => ({ ...s, end_at: addHours(s.start_at, typeHours(t, null)) }));
  }, [f.start_at, f.visit_type_id, f.end_manual, types]);
  const manualEnd = (v) => setF((s) => ({ ...s, end_at: v, end_manual: true }));
  const check = () => {
    const e = {};
    if (step === 0) {
      if (!f.host_company_id) e.host_company_id = "Selecione a empresa visitada";
      if (!f.host_person_id) e.host_person_id = "Selecione o anfitrião";
      if (!f.visit_type_id) e.visit_type_id = "Selecione o tipo da visita";
    }
    if (step === 1 && (!f.start_at || !f.end_at)) e.start_at = "Informe início e fim";
    setErrors(e);
    return !Object.keys(e).length;
  };
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/selfreg/invites", { ...f, start_at: fromLocalInput(f.start_at), end_at: fromLocalInput(f.end_at) });
      setResult(data); onSaved();
    } catch (e) {
      const fe = e.response?.data?.detail?.fields || {};
      setErrors(fe);
  const first = Object.keys(fe).map((k) => FIELD_STEP[k]).filter((s) => s !== undefined).sort((a, b) => a - b)[0];
      if (first !== undefined) setStep(first);
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };
  const noTypes = types && !types.length;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" onOpenAutoFocus={(e) => e.preventDefault()} data-testid="invite-dialog">
        <DialogHeader>
          <DialogTitle>Convidar visitante</DialogTitle>
          {!result && <><p className="text-xs text-muted-foreground">Passo {step + 1} de 3 · {STEPS[step]}</p><StepDots step={step} /></>}
        </DialogHeader>
        {result ? <Result result={result} /> : (
          <div key={step} className="grid gap-4 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200">
            {step === 0 && <>
              {noTypes && <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-300" data-testid="invite-no-types">Nenhum tipo de visita liberado para sua empresa. Peça ao Administrador para marcar em Empresas › editar empresa › "Tipos de visita que a empresa pode usar".</p>}
              <Field label="Empresa visitada" required error={errors.host_company_id}>
                <select className={sel} value={f.host_company_id} onChange={(e) => setF((s) => ({ ...s, host_company_id: e.target.value, host_person_id: "" }))} data-testid="invite-company-select">
                  <option value="">Selecione…</option>{companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Anfitrião" required error={errors.host_person_id}><HostSelect key={f.host_company_id} companyId={f.host_company_id} value={f.host_person_id} onChange={set("host_person_id")} /></Field>
              <Field label="Tipo da visita" required error={errors.visit_type_id}>
                <select className={sel} value={f.visit_type_id} onChange={(e) => set("visit_type_id")(e.target.value)} disabled={noTypes} data-testid="invite-type-select">
                  <option value="">{types === null ? "Carregando…" : "Selecione…"}</option>{(types || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </Field>
            </>}
            {step === 1 && <>
              <Field label="Início" required error={errors.start_at}><Input type="datetime-local" className="h-11 text-base sm:h-9 sm:text-sm" value={f.start_at} onChange={(e) => set("start_at")(e.target.value)} data-testid="invite-start" /></Field>
              <Field label="Fim da visita" required error={errors.end_at} hint={f.end_manual ? "Alterado manualmente" : "Calculado pela duração do tipo de visita"}>
                <Input type="datetime-local" className="h-11 text-base sm:h-9 sm:text-sm" value={f.end_at} onChange={(e) => manualEnd(e.target.value)} data-testid="invite-end" />
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <Button type="button" variant="outline" className="h-11" onClick={() => manualEnd(addHours(f.end_at || f.start_at, 1))} data-testid="invite-plus1">+1h</Button>
                  <Button type="button" variant="outline" className="h-11" onClick={() => manualEnd(addHours(f.end_at || f.start_at, 4))} data-testid="invite-plus4">+4h</Button>
                  <Button type="button" variant="outline" className="h-11" onClick={() => manualEnd(endOfDay(f.start_at))} data-testid="invite-eod">Fim do dia</Button>
                </div>
                {f.end_manual && <Button type="button" variant="ghost" className="mt-1 h-10 text-xs" onClick={() => setF((s) => ({ ...s, end_manual: false }))}>Usar duração do tipo</Button>}
              </Field>
            </>}
            {step === 2 && <>
              <Field label="Nome do visitante" hint="Opcional"><Input className="h-11 text-base sm:h-9 sm:text-sm" autoCapitalize="words" value={f.guest_name} onChange={(e) => set("guest_name")(e.target.value)} data-testid="invite-guest-name" /></Field>
              <Field label="E-mail do visitante" error={errors.guest_email} hint="Se informado, o convite é enviado por e-mail"><Input className="h-11 text-base sm:h-9 sm:text-sm" type="email" inputMode="email" value={f.guest_email} onChange={(e) => set("guest_email")(e.target.value)} data-testid="invite-guest-email" /></Field>
              <Field label="Observações" hint="Vai na mensagem do convite (ex.: trazer EPI, portaria 2)"><Input className="h-11 text-base sm:h-9 sm:text-sm" value={f.notes} maxLength={300} onChange={(e) => set("notes")(e.target.value)} data-testid="invite-notes" /></Field>
              <p className="text-xs text-muted-foreground" data-testid="invite-approval-note">Quando o visitante concluir o cadastro, a solicitação vai para aprovação do anfitrião ou da portaria.</p>
            </>}
          </div>
        )}
        <DialogFooter>
          {result ? <Button variant="outline" onClick={onClose} data-testid="invite-close">Fechar</Button> : <>
            {step > 0 ? <Button variant="outline" onClick={() => setStep(step - 1)} data-testid="invite-back"><ArrowLeft className="mr-1 h-4 w-4" />Voltar</Button>
              : <Button variant="outline" onClick={onClose} data-testid="invite-cancel">Cancelar</Button>}
            {step < 2 ? <Button className={primary} disabled={noTypes} onClick={() => check() && setStep(step + 1)} data-testid="invite-next">Continuar</Button>
              : <Button className={primary} onClick={save} disabled={busy || noTypes} data-testid="invite-save"><Mail className="mr-1 h-4 w-4" />Criar convite</Button>}
          </>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
