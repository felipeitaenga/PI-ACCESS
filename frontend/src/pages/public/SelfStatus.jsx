import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { Box, PublicShell, errMsg, fmtDT, pub } from "./common";

const VIEW = {
  pendente: { icon: Clock, color: "text-amber-300", title: "Aguardando aprovação", text: "Sua solicitação foi enviada. Você receberá um e-mail assim que for respondida. Pode deixar esta página aberta: ela se atualiza sozinha." },
  aprovado: { icon: CheckCircle2, color: "text-emerald-400", title: "Visita aprovada", text: "No horário da visita, olhe para o leitor facial na entrada. Se não liberar, procure a recepção." },
  recusado: { icon: XCircle, color: "text-red-400", title: "Visita não aprovada", text: "Em caso de dúvida, procure a recepção." },
  expirado: { icon: XCircle, color: "text-slate-400", title: "Solicitação expirada", text: "Ela não foi respondida a tempo. Faça uma nova solicitação ou procure a recepção." },
};

export default function SelfStatus() {
  const { token } = useParams();
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () => pub.get(`/status/${token}`).then(({ data }) => alive && setS(data)).catch((e) => alive && setErr(errMsg(e)));
    load();
    const t = setInterval(() => { if (!s || s.status === "pendente") load(); }, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [token, s?.status]); // eslint-disable-line
  if (err && !s) return <PublicShell title="Solicitação de visita"><Box>{err}</Box></PublicShell>;
  if (!s) return <PublicShell title="Solicitação de visita"><div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-sky-400" /></div></PublicShell>;
  const v = VIEW[s.status] || VIEW.pendente;
  const Icon = v.icon;
  return (
    <PublicShell title={s.company} subtitle="Solicitação de visita">
      <Box className="space-y-3 text-center">
        <Icon className={`mx-auto h-14 w-14 ${v.color}`} />
        <h1 className="text-xl font-bold">{v.title}</h1>
        <p className="text-sm text-slate-300">{s.name}, visita a <b>{s.host_name}</b></p>
        <p className="text-sm text-slate-400">{fmtDT(s.start_at)} até {fmtDT(s.end_at)}</p>
        <p className="text-sm leading-relaxed text-slate-300">{v.text}</p>
      </Box>
    </PublicShell>
  );
}
