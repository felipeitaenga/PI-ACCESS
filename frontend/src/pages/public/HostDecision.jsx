import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Box, PButton, PField, PublicShell, errMsg, fmtDT, inputCls, pub } from "./common";

const DONE = {
  aprovado: [CheckCircle2, "text-emerald-400", "Visita aprovada"],
  recusado: [XCircle, "text-red-400", "Visita recusada"],
  expirado: [XCircle, "text-slate-400", "Solicitação expirada"],
  processando: [Loader2, "text-sky-400", "Processando…"],
};
const VIA = { anfitriao: "por você", portaria: "pela portaria", convite: "pelo convite" };

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
  if (!r) return <PublicShell title="Aprovação de visita"><Box>{err || <Loader2 className="mx-auto h-8 w-8 animate-spin text-sky-400" />}</Box></PublicShell>;
  if (r.status !== "pendente") {
    const [Icon, color, title] = DONE[r.status] || DONE.processando;
    return (
      <PublicShell title={r.company} subtitle="Aprovação de visita">
        <Box className="space-y-2 text-center">
          <Icon className={`mx-auto h-14 w-14 ${color}`} />
          <h1 className="text-xl font-bold">{title}</h1>
          <p className="text-sm text-slate-300">{r.name}</p>
          {r.decided_via && <p className="text-sm text-slate-400">Respondida {VIA[r.decided_via] || ""}{r.decided_via !== "anfitriao" && r.decided_by_name ? ` (${r.decided_by_name})` : ""}.</p>}
          <p className="text-sm text-slate-400">{fmtDT(r.start_at)} até {fmtDT(r.end_at)}</p>
        </Box>
      </PublicShell>
    );
  }
  return (
    <PublicShell title={r.company} subtitle="Aprovação de visita">
      <Box className="space-y-4">
        <div className="flex gap-4">
          {r.photo ? <img src={r.photo} alt="" className="h-40 w-30 shrink-0 rounded-lg object-cover" style={{ width: 120 }} /> : null}
          <div className="min-w-0 space-y-1 text-sm">
            <p className="text-lg font-bold leading-tight text-white">{r.name}</p>
            {r.visitor_company && <p className="text-slate-300">{r.visitor_company}</p>}
            <p className="text-slate-400">{r.doc_type?.toUpperCase()} {r.doc_number}</p>
            {r.plate && <p className="text-slate-400">Placa {r.plate}</p>}
          </div>
        </div>
        <div className="rounded-lg bg-slate-950 p-3 text-sm">
          <p>Visita a <b>{r.host_name}</b> · {r.visit_type}</p>
          <p className="text-slate-400">{fmtDT(r.start_at)} até {fmtDT(r.end_at)}</p>
        </div>
        {r.blacklist && <p className="flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200"><AlertTriangle className="h-5 w-5 shrink-0" />Esta solicitação precisa ser analisada pela portaria.</p>}
        {err && <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{err}</p>}
        {rejecting ? (
          <div className="space-y-3">
            <PField label="Motivo (opcional, será enviado ao visitante)">
              <input className={inputCls} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
            </PField>
            <PButton variant="danger" disabled={busy} onClick={() => act("reject")}>Confirmar recusa</PButton>
            <PButton variant="outline" onClick={() => setRejecting(false)}>Voltar</PButton>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <PButton variant="outline" disabled={busy} onClick={() => setRejecting(true)}>Recusar</PButton>
            <PButton disabled={busy || r.blacklist} onClick={() => act("approve")}>{busy && <Loader2 className="h-5 w-5 animate-spin" />}Aprovar</PButton>
          </div>
        )}
      </Box>
    </PublicShell>
  );
}
