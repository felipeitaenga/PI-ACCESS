import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Bell, BellRing, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Box, PButton, PublicShell, errMsg, fmtDT, pub } from "./common";

const VIEW = {
  aprovado: { icon: CheckCircle2, color: "text-emerald-400", title: "Visita aprovada", text: "Na chegada, olhe para o leitor facial na entrada. Se não liberar, procure a recepção." },
  recusado: { icon: XCircle, color: "text-red-400", title: "Visita não aprovada", text: "Em caso de dúvida, procure a recepção." },
  expirado: { icon: XCircle, color: "text-slate-400", title: "Solicitação expirada", text: "Ela não foi respondida a tempo. Faça uma nova solicitação ou procure a recepção." },
};

const b64ToBytes = (s) => {
  const p = "=".repeat((4 - (s.length % 4)) % 4);
  const raw = atob((s + p).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

function alertUser(ok) {
  try { navigator.vibrate?.(ok ? [200, 100, 200, 100, 400] : [500]); } catch { /* */ }
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    (ok ? [660, 880, 1100] : [440, 330]).forEach((f, i) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
      const t = ctx.currentTime + i * 0.18; g.gain.setValueAtTime(0.25, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.17);
      o.start(t); o.stop(t + 0.18);
    });
  } catch { /* */ }
}

function PushOptIn({ token }) {
  const [state, setState] = useState("idle");
  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone;
  useEffect(() => { if (supported && Notification.permission === "granted") { enable(); } }, []); // eslint-disable-line
  const enable = async () => {
    setState("busy");
    try {
      const { data } = await pub.get("/push-key");
      if (!data.enabled) { setState("off"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const cache = await caches.open("piaccess-selfreg");
      await cache.put("/__last_status", new Response(window.location.href));
      if ((await Notification.requestPermission()) !== "granted") { setState("denied"); return; }
      const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(data.key) });
      await pub.post(`/push/${token}`, sub.toJSON());
      setState("on");
    } catch { setState("error"); }
  };
  if (state === "off") return null;
  if (!supported) {
    return ios && !standalone ? <p className="text-xs text-slate-400" data-testid="push-ios-hint">Para ser avisado mesmo com o navegador fechado no iPhone: toque em Compartilhar › "Adicionar à Tela de Início" e abra por lá.</p> : null;
  }
  if (state === "on") return <p className="flex items-center justify-center gap-2 text-sm text-emerald-300" data-testid="push-on"><BellRing className="h-4 w-4" />Você será avisado no celular quando responderem.</p>;
  return (
    <div className="space-y-1">
      <PButton variant="outline" onClick={enable} disabled={state === "busy"} data-testid="push-enable"><Bell className="h-5 w-5" />Avisar-me no celular</PButton>
      {state === "denied" && <p className="text-xs text-amber-300">Notificações bloqueadas no navegador. Libere nas configurações do site.</p>}
      {state === "error" && <p className="text-xs text-amber-300">Não foi possível ativar o aviso neste navegador. Deixe esta página aberta.</p>}
    </div>
  );
}

function Waiting({ s, token }) {
  return (
    <Box className="space-y-5 text-center" data-testid="selfreg-waiting">
      <div className="relative mx-auto h-24 w-24">
        <div className="absolute inset-0 rounded-full border-4 border-slate-800" />
        <div className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-sky-400 border-r-sky-400/60" style={{ animationDuration: "1.1s" }} />
        <div className="absolute inset-3 animate-pulse rounded-full bg-sky-500/10" />
      </div>
      <div>
        <h1 className="text-xl font-bold">Aguardando aprovação</h1>
        <p className="mt-1 text-sm text-slate-300">{s.name}, sua solicitação foi enviada para <b>{s.host_name}</b>.</p>
      </div>
      <p className="text-sm leading-relaxed text-slate-400">Aguarde aqui: esta tela se atualiza sozinha. Se fechar, avisamos por e-mail{("PushManager" in window) ? " ou no celular" : ""}.</p>
      <PushOptIn token={token} />
    </Box>
  );
}

export default function SelfStatus() {
  const { token } = useParams();
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const prev = useRef(null);
  useEffect(() => {
    let alive = true;
    const load = () => pub.get(`/status/${token}`).then(({ data }) => {
      if (!alive) { return; }
      if (prev.current === "pendente" && data.status !== "pendente") { alertUser(data.status === "aprovado"); }
      prev.current = data.status;
      setS(data);
    }).catch((e) => alive && setErr(errMsg(e)));
    load();
    const t = setInterval(() => { if (prev.current === null || prev.current === "pendente") { load(); } }, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [token]);
  if (err && !s) return <PublicShell title="Solicitação de visita"><Box>{err}</Box></PublicShell>;
  if (!s) return <PublicShell title="Solicitação de visita"><div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-sky-400" /></div></PublicShell>;
  if (s.status === "pendente") return <PublicShell title={s.company} subtitle="Solicitação de visita"><Waiting s={s} token={token} /></PublicShell>;
  const v = VIEW[s.status] || VIEW.expirado;
  const Icon = v.icon;
  return (
    <PublicShell title={s.company} subtitle="Solicitação de visita">
      <Box className="space-y-3 text-center animate-in fade-in zoom-in-95 duration-500" data-testid={`selfreg-status-${s.status}`}>
        <Icon className={`mx-auto h-16 w-16 ${v.color}`} />
        <h1 className="text-xl font-bold">{v.title}</h1>
        <p className="text-sm text-slate-300">{s.name}, visita a <b>{s.host_name}</b></p>
        {s.status === "aprovado" && <p className="text-sm text-slate-400">{fmtDT(s.start_at)} até {fmtDT(s.end_at)}</p>}
        <p className="text-sm leading-relaxed text-slate-300">{v.text}</p>
      </Box>
    </PublicShell>
  );
}
