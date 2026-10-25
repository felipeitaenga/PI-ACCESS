import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { AlertTriangle, Check, CheckCircle2, Clock, Loader2, X, XCircle } from "lucide-react";
import { Alert, Box, PButton, PField, PageSkeleton, PublicShell, errMsg, fmtDT, inputCls, pub } from "./common";

const DONE = {
  aprovado: [CheckCircle2, "text-emerald-400", "bg-emerald-500/15 ring-emerald-500/40", "Visita aprovada"],
  recusado: [XCircle, "text-red-400", "bg-red-500/15 ring-red-500/40", "Visita recusada"],
  expirado: [Clock, "text-slate-300", "bg-slate-500/15 ring-slate-500/40", "Solicitação expirada"],
  processando: [Loader2, "text-sky-400", "bg-sky-500/15 ring-sky-500/40", "Processando…"],
};
const VIA = { anfitriao: "por você", portaria: "pela portaria", convite: "pelo convite" };

function Done({ r }) {
  const [Icon, color, ring, title] = DONE[r.status] || DONE.processando;
  return (
    <Box className="space-y-3 py-6 text-center motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-95 motion-safe:duration-300" data-testid={`host-decision-${r.status}`}>
      <div className={`mx-auto flex h-24 w-24 items-center justify-center rounded-full ring-4 ${ring}`}><Icon className={`h-14 w-14 ${color} ${r.status === "processando" ? "motion-safe:animate-spin" : ""}`} /></div>
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="text-slate-300">{r.name}</p>
      {r.decided_via && <p className="text-sm text-slate-400">Respondida {VIA[r.decided_via] || ""}{r.decided_via !== "anfitriao" && r.decided_by_name ? ` (${r.decided_by_name})` : ""}.</p>}
      <p className="text-sm text-slate-400">{fmtDT(r.start_at)} até {fmtDT(r.end_at)}</p>
      {r.status === "aprovado" && <p className="text-sm text-emerald-200">O visitante já foi avisado e entra pelo leitor facial.</p>}
    </Box>
  );
}

export default function HostDecision() {
  const { token } = useParams();
  const [r, setR] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  useEffect(() => { pub.get(`/decision/${token}`).then(({ data }) => setR(data)).catch((e) => setErr(errMsg(e))); }, [token]);
  const act = async (action) => {
    setBusy(true); setErr("");
    try { const { data } = await pub.post(`/decision/${token}`, { action, reason }); setR(data); }
    catch (e) { setErr(errMsg(e)); pub.get(`/decision/${token}`).then(({ data }) => setR(data)).catch(() => {}); }
    finally { setBusy(false); }
  };
  if (!r) return <PublicShell title="Aprovação de visita">{err ? <Box data-testid="host-decision-error">{err}</Box> : <PageSkeleton />}</PublicShell>;
  if (r.status !== "pendente") return <PublicShell title={r.company} subtitle="Aprovação de visita"><Done r={r} /></PublicShell>;
  const spin = busy && <Loader2 className="h-5 w-5 motion-safe:animate-spin" />;
  const bar = rejecting ? <>
    <PButton variant="outline" className="w-1/3" onClick={() => setRejecting(false)} data-testid="host-decision-back">Voltar</PButton>
    <PButton variant="danger" disabled={busy} onClick={() => act("reject")} data-testid="host-decision-confirm-reject">{spin}Confirmar recusa</PButton>
  </> : <>
    <PButton variant="outline" className="min-h-14 text-red-300" disabled={busy} onClick={() => setRejecting(true)} data-testid="host-decision-reject"><X className="h-5 w-5" />Recusar</PButton>
    <PButton variant="success" className="min-h-14" disabled={busy || r.blacklist} onClick={() => act("approve")} data-testid="host-decision-approve">{spin || <Check className="h-5 w-5" />}Aprovar</PButton>
  </>;
  return (
    <PublicShell title={r.company} subtitle="Aprovação de visita" bar={bar}>
      <Box className="space-y-4">
        {r.blacklist && <Alert tone="warn" data-testid="host-decision-blacklist"><AlertTriangle className="mr-1 inline h-4 w-4" />Esta solicitação precisa ser analisada pela portaria.</Alert>}
        {r.identity_check && <Alert tone="warn" data-testid="host-decision-identity"><AlertTriangle className="mr-1 inline h-4 w-4" />Este CPF já tinha cadastro. Confira se a foto é mesmo da pessoa que você espera antes de aprovar.</Alert>}
        {r.photo ? <img src={r.photo} alt={`Foto de ${r.name}`} className="mx-auto aspect-[3/4] w-full max-w-[220px] rounded-2xl object-cover" data-testid="host-decision-photo" /> : null}
        <div className="text-center">
          <p className="text-2xl font-bold leading-tight text-white" data-testid="host-decision-name">{r.name}</p>
          {r.visitor_company && <p className="text-slate-300">{r.visitor_company}</p>}
          <p className="font-mono text-sm text-slate-400">{r.doc_type?.toUpperCase()} {r.doc_number}{r.plate ? ` · Placa ${r.plate}` : ""}</p>
        </div>
        {r.visit_reason && <div className="rounded-xl bg-slate-950 p-3"><p className="text-xs text-slate-400">Motivo da visita</p><p data-testid="host-decision-reason">{r.visit_reason}</p></div>}
        <div className="rounded-xl bg-slate-950 p-3">
          <p>Visita a <b>{r.host_name}</b> · {r.visit_type}</p>
          <p className="text-sm text-slate-400"><Clock className="mr-1 inline h-4 w-4 text-sky-400" />{fmtDT(r.start_at)} até {fmtDT(r.end_at)}</p>
        </div>
        {err && <Alert>{err}</Alert>}
        {rejecting && (
          <PField label="Motivo da recusa (opcional, será enviado ao visitante)" htmlFor="hd-reason">
            <input id="hd-reason" className={inputCls} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} data-testid="host-decision-reason-input" />
          </PField>
        )}
      </Box>
    </PublicShell>
  );
}
