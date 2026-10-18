import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Building2, Camera, CheckCircle2, Loader2, Search, ShieldCheck, UserCheck } from "lucide-react";
import { CameraCapture } from "@/components/CameraCapture";
import { maskCpf, validCpf } from "@/lib/br";
import { Box, Captcha, PButton, PField, PublicShell, errFields, errMsg, fmtDT, inputCls, pub } from "./common";

const maskPlate = (v) => {
  const r = String(v || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);
  return /^[A-Z]{3}\d{4}$/.test(r) ? `${r.slice(0, 3)}-${r.slice(3)}` : r;
};
const maskPhone = (v) => {
  const d = String(v || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d;
  if (d.length <= 7) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, d.length - 4)}-${d.slice(-4)}`;
};

function HostSearch({ ctxKey, value, onPick, error }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (value || q.trim().length < 3) { setItems([]); return undefined; }
    const t = setTimeout(() => {
      setBusy(true);
      pub.post("/hosts", { ...ctxKey, q }).then(({ data }) => setItems(data)).catch(() => setItems([])).finally(() => setBusy(false));
    }, 400);
    return () => clearTimeout(t);
  }, [q, value]); // eslint-disable-line
  if (value) {
    return (
      <PField label="Quem você vai visitar" required>
        <div className="flex items-center gap-2 rounded-lg border border-sky-500/50 bg-sky-500/10 px-3 py-2.5">
          <UserCheck className="h-5 w-5 text-sky-400" /><span className="flex-1">{value.name}</span>
          <button type="button" className="text-sm text-sky-300 underline" onClick={() => { onPick(null); setQ(""); }}>trocar</button>
        </div>
      </PField>
    );
  }
  return (
    <PField label="Quem você vai visitar" required error={error} hint="Digite ao menos 3 letras do nome da pessoa">
      <div className="relative">
        <Search className="absolute left-3 top-3 h-5 w-5 text-slate-500" />
        <input className={`${inputCls} pl-10`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome da pessoa" autoComplete="off" />
      </div>
      {busy && <p className="mt-2 text-xs text-slate-400">Buscando…</p>}
      {!busy && q.trim().length >= 3 && items.length === 0 && <p className="mt-2 text-xs text-slate-400">Ninguém encontrado. Confira o nome ou procure a recepção.</p>}
      <div className="mt-2 space-y-1.5">
        {items.map((p) => (
          <button key={p.id} type="button" onClick={() => onPick(p)} className="w-full rounded-lg border border-slate-700 px-3 py-2.5 text-left hover:border-sky-500">{p.name}</button>
        ))}
      </div>
    </PField>
  );
}

function CompanyPicker({ companies, value, onPick, error }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); } };
    document.addEventListener("pointerdown", h);
    return () => document.removeEventListener("pointerdown", h);
  }, []);
  const list = companies.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase()));
  if (value) {
    return (
      <PField label="Empresa que você vai visitar" required>
        <div className="flex items-center gap-2 rounded-lg border border-sky-500/50 bg-sky-500/10 px-3 py-2.5">
          <Building2 className="h-5 w-5 text-sky-400" /><span className="flex-1">{value.name}</span>
          <button type="button" className="text-sm text-sky-300 underline" onClick={() => onPick(null)}>trocar</button>
        </div>
      </PField>
    );
  }
  return (
    <PField label="Empresa que você vai visitar" required error={error} hint="Toque para escolher ou digite o nome">
      <div ref={ref}>
      <div className="relative">
        <Building2 className="absolute left-3 top-3 h-5 w-5 text-slate-500" />
        <input className={`${inputCls} pl-10`} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          placeholder="Selecione a empresa" autoComplete="off" data-testid="selfreg-company-input" />
      </div>
      {open && (
        <div className="mt-2 max-h-64 space-y-1.5 overflow-auto" data-testid="selfreg-company-list">
          {list.map((c) => (
            <button key={c.id} type="button" onClick={() => { onPick(c); setOpen(false); setQ(""); }} className="w-full rounded-lg border border-slate-700 px-3 py-2.5 text-left hover:border-sky-500" data-testid={`selfreg-company-${c.id}`}>{c.name}</button>
          ))}
          {list.length === 0 && <p className="text-xs text-slate-400">Nenhuma empresa encontrada.</p>}
        </div>
      )}
      </div>
    </PField>
  );
}

function CpfField({ ctxKey, verifyToken, value, onChange, error, onFound }) {
  const [found, setFound] = useState(null);
  const digits = value.replace(/\D/g, "");
  const bad = digits.length === 11 && !validCpf(value);
  useEffect(() => {
    setFound(null); onFound(null);
    if (digits.length !== 11 || !validCpf(value)) { return; }
    pub.post("/lookup", { ...ctxKey, verify_token: verifyToken, doc_number: digits }).then(({ data }) => { setFound(data.found ? data.greeting : ""); onFound(data.found ? data.greeting : ""); }).catch(() => {});
  }, [digits]); // eslint-disable-line
  return (
    <PField label="CPF" required error={error || (bad ? "CPF inválido — confira os números" : "")} hint="Digite seu CPF">
      <input className={inputCls} inputMode="numeric" autoComplete="off" value={value} placeholder="000.000.000-00"
        onChange={(e) => onChange(maskCpf(e.target.value))} data-testid="selfreg-cpf-input" />
      {found && <p className="mt-2 flex items-center gap-2 text-sm text-emerald-300" data-testid="selfreg-cpf-found"><CheckCircle2 className="h-4 w-4" />Encontramos seu cadastro, {found}. Seus dados serão usados.</p>}
    </PField>
  );
}

function Selfie({ photo, setPhoto, error }) {
  const [cam, setCam] = useState(false);
  return (
    <PField label="Foto do rosto (selfie)" required error={error} hint="Tire a foto agora pela câmera: de frente, sem óculos escuros, boné ou máscara, em local bem iluminado.">
      <div className="flex items-center gap-3">
        <div className="flex h-32 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-700 bg-slate-950">
          {photo ? <img src={photo} alt="Sua foto" className="h-full w-full object-cover" /> : <Camera className="h-8 w-8 text-slate-600" />}
        </div>
        <div className="flex flex-1 flex-col gap-2">
          <PButton onClick={() => setCam(true)} data-testid="selfreg-take-selfie"><Camera className="h-5 w-5" />{photo ? "Tirar outra" : "Tirar selfie"}</PButton>
        </div>
      </div>
      <CameraCapture open={cam} onClose={() => setCam(false)} onCapture={setPhoto} />
    </PField>
  );
}

export default function SelfRegister({ mode }) {
  const params = useParams();
  const navigate = useNavigate();
  const ctxKey = mode === "invite" ? { invite: params.token } : { code: params.code };
  const [info, setInfo] = useState(null);
  const [fatal, setFatal] = useState("");
  const [step, setStep] = useState("intro");
  const [consent, setConsent] = useState(false);
  const [captcha, setCaptcha] = useState("");
  const [email, setEmail] = useState("");
  const [otpId, setOtpId] = useState("");
  const [otpMasked, setOtpMasked] = useState("");
  const [otp, setOtp] = useState("");
  const [verifyToken, setVerifyToken] = useState("");
  const [recurring, setRecurring] = useState(null);
  const [useSaved, setUseSaved] = useState(false);
  const [f, setF] = useState({ name: "", doc_type: "cpf", doc_number: "", visitor_company: "", phone: "", plate: "", visit_reason: "", remember: false });
  const [known, setKnown] = useState(null);
  const [host, setHost] = useState(null);
  const [company, setCompany] = useState(null);
  const [photo, setPhoto] = useState("");
  const [errors, setErrors] = useState({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e }));

  useEffect(() => {
    pub.get("/info", { params: ctxKey }).then(({ data }) => {
      setInfo(data);
      if (data.invite?.guest_email) setEmail(data.invite.guest_email);
      if (data.invite?.guest_name) setF((s) => ({ ...s, name: data.invite.guest_name }));
    }).catch((e) => setFatal(errMsg(e)));
  }, []); // eslint-disable-line

  const run = async (fn) => {
    setBusy(true); setMsg(""); setErrors({});
    try { await fn(); } catch (e) { setErrors(errFields(e)); setMsg(errMsg(e)); } finally { setBusy(false); }
  };
  const sendOtp = () => run(async () => {
    const { data } = await pub.post("/otp", { ...ctxKey, email, captcha });
    setOtpId(data.otp_id); setOtpMasked(data.email); setOtp(""); setStep("code");
  });
  const verify = () => run(async () => {
    const { data } = await pub.post("/verify", { ...ctxKey, otp_id: otpId, otp });
    setVerifyToken(data.verify_token); setRecurring(data.recurring); setUseSaved(!!data.recurring);
    if (data.recurring) setF((s) => ({ ...s, visitor_company: data.recurring.visitor_company || "", plate: data.recurring.plate || "", phone: data.recurring.phone || "" }));
    setStep("form");
  });
  const submit = () => run(async () => {
    const body = { ...ctxKey, company_id: company?.id || "", consent, captcha, verify_token: verifyToken, email, use_saved: useSaved, ...f,
      photo: useSaved ? "" : photo, host_person_id: host?.id || "" };
    const { data } = await pub.post("/submit", body);
    navigate(`/solicitacao/${data.status_token}`, { replace: true });
  });

  if (fatal) return <PublicShell title="Cadastro de visitante"><Box><p className="text-slate-200">{fatal}</p></Box></PublicShell>;
  if (!info) return <PublicShell title="Cadastro de visitante"><div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-sky-400" /></div></PublicShell>;
  const isInvite = !!info.invite;
  const isSite = !!info.companies;
  const hostKey = { ...ctxKey, company_id: company?.id || "" };
  const hours = isSite ? company?.duration_hours : info.duration_hours;
  const Err = () => (msg ? <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{msg}</p> : null);

  return (
    <PublicShell title={info.company || company?.name || info.site} subtitle={`Cadastro de visitante${info.company || company ? ` · ${info.site}` : ""}`}>
      {isInvite && (
        <Box className="mb-4 border-sky-500/40">
          <p className="text-sm text-slate-300">Convite de <b className="text-white">{info.invite.host_name}</b></p>
          <p className="text-sm text-slate-400">{fmtDT(info.invite.start_at)} até {fmtDT(info.invite.end_at)}</p>
        </Box>
      )}

      {step === "intro" && (
        <Box className="space-y-4">
          <div className="flex items-center gap-2 text-sky-300"><ShieldCheck className="h-5 w-5" /><span className="font-semibold">Seus dados (LGPD)</span></div>
          <p className="whitespace-pre-line text-sm leading-relaxed text-slate-300">{info.lgpd_text}</p>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 h-5 w-5 accent-sky-500" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>Li e concordo com o uso dos meus dados para controle de acesso.</span>
          </label>
          <PButton disabled={!consent} onClick={() => setStep(info.otp ? "email" : "form")}>Começar</PButton>
        </Box>
      )}

      {step === "email" && (
        <Box className="space-y-4">
          <PField label="Seu e-mail" required error={errors.email} hint="Enviaremos um código de 6 dígitos para confirmar.">
            <input className={inputCls} type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} placeholder="voce@empresa.com" />
          </PField>
          <Captcha siteKey={info.captcha_site_key} onToken={setCaptcha} />
          <Err />
          <PButton disabled={busy || !email} onClick={sendOtp}>{busy && <Loader2 className="h-5 w-5 animate-spin" />}Enviar código</PButton>
        </Box>
      )}

      {step === "code" && (
        <Box className="space-y-4">
          <p className="text-sm text-slate-300">Digite o código enviado para <b>{otpMasked}</b>. Confira também a caixa de spam.</p>
          <PField label="Código" error={errors.otp}>
            <input className={`${inputCls} text-center font-mono text-2xl tracking-[0.5em]`} inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          </PField>
          <Err />
          <PButton disabled={busy || otp.length !== 6} onClick={verify}>{busy && <Loader2 className="h-5 w-5 animate-spin" />}Confirmar</PButton>
          <button type="button" className="w-full text-sm text-sky-300 underline" onClick={() => setStep("email")}>Reenviar ou trocar o e-mail</button>
        </Box>
      )}

      {step === "form" && (
        <div className="space-y-4">
          {recurring && (
            <Box className="border-emerald-500/40">
              <div className="flex items-center gap-3">
                {recurring.photo_thumb ? <img src={recurring.photo_thumb} alt="" className="h-14 w-11 rounded object-cover" /> : <CheckCircle2 className="h-8 w-8 text-emerald-400" />}
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">Olá de novo, {recurring.name.split(" ")[0]}!</p>
                  <p className="text-xs text-slate-400">{recurring.doc_type?.toUpperCase()} {recurring.doc_number}</p>
                </div>
              </div>
              <label className="mt-3 flex items-center gap-3 text-sm">
                <input type="checkbox" className="h-5 w-5 accent-sky-500" checked={useSaved} onChange={(e) => setUseSaved(e.target.checked)} />
                Usar meu cadastro salvo (sem nova selfie)
              </label>
            </Box>
          )}

          {!isInvite && <Box className="space-y-4">
            {isSite && <CompanyPicker companies={info.companies} value={company} onPick={(c) => { setCompany(c); setHost(null); }} error={errors.company_id} />}
            {(!isSite || company) && <HostSearch key={company?.id || "-"} ctxKey={hostKey} value={host} onPick={setHost} error={errors.host_person_id} />}
            <p className="text-xs text-slate-400">A solicitação vai agora para o anfitrião. A visita começa quando ele aprovar{hours ? ` e vale por ${String(hours).replace(".", ",")} h` : ""}.</p>
          </Box>}

          {!useSaved && (
            <Box className="space-y-4">
              <CpfField ctxKey={ctxKey} verifyToken={verifyToken} value={f.doc_number} onChange={set("doc_number")} error={errors.doc_number} onFound={setKnown} />
              {!known && (
                <PField label="Nome completo" required error={errors.name}>
                  <input className={inputCls} autoComplete="name" value={f.name} onChange={set("name")} data-testid="selfreg-name-input" />
                </PField>
              )}
              <Selfie photo={photo} setPhoto={setPhoto} error={errors.photo} />
            </Box>
          )}

          <Box className="space-y-4">
            <PField label="Motivo da visita" hint="Opcional">
              <input className={inputCls} maxLength={200} value={f.visit_reason} onChange={set("visit_reason")} placeholder="Ex.: reunião, entrega, manutenção" data-testid="selfreg-reason-input" />
            </PField>
            <PField label="Sua empresa" hint={known ? "Opcional — em branco mantém a do seu cadastro" : "Opcional"}>
              <input className={inputCls} value={f.visitor_company} onChange={set("visitor_company")} />
            </PField>
            <div className="grid grid-cols-2 gap-2">
              <PField label="Telefone" hint="Opcional" error={errors.phone}>
                <input className={inputCls} inputMode="tel" autoComplete="tel" value={f.phone} onChange={(e) => set("phone")(maskPhone(e.target.value))} />
              </PField>
              <PField label="Placa" hint="Se vier de carro" error={errors.plate}>
                <input className={`${inputCls} uppercase`} value={f.plate} onChange={(e) => set("plate")(maskPlate(e.target.value))} />
              </PField>
            </div>
            {!info.otp && (
              <PField label="E-mail" hint="Opcional — para receber a confirmação" error={errors.email}>
                <input className={inputCls} type="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} />
              </PField>
            )}
            {info.otp && !useSaved && (
              <label className="flex items-start gap-3 text-sm">
                <input type="checkbox" className="mt-0.5 h-5 w-5 accent-sky-500" checked={f.remember} onChange={set("remember")} />
                <span>Lembrar meu cadastro para as próximas visitas <span className="block text-xs text-slate-400">Sua foto fica guardada e é apagada após 12 meses sem visitas.</span></span>
              </label>
            )}
            {!info.otp && <Captcha siteKey={info.captcha_site_key} onToken={setCaptcha} />}
          </Box>

          {Object.keys(errors).length > 0 && errors.consent && <p className="text-sm text-red-400">{errors.consent}</p>}
          <Err />
          <PButton disabled={busy} onClick={submit}>{busy && <Loader2 className="h-5 w-5 animate-spin" />}Enviar para aprovação</PButton>
        </div>
      )}
    </PublicShell>
  );
}
