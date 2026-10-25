import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Loader2, Send } from "lucide-react";
import { validCpf } from "@/lib/br";
import { Alert, Box, Captcha, PButton, PField, PageSkeleton, PublicShell, StepBar, errFields, errMsg, inputCls, pub, scrollToError } from "./common";
import { CompanyPicker, CpfField, HostSearch, InviteCard, Lgpd, ReviewRow, SelfieStep, maskPhone, maskPlate } from "./SelfRegSteps";

const STEPS = ["Visita", "Seus dados", "Selfie", "Revisar e enviar"];
const FIELD_STEP = { company_id: 0, host_person_id: 0, visit_reason: 0, doc_number: 1, doc_type: 1, name: 1, phone: 1, plate: 1, email: 1, visitor_company: 1, photo: 2 };
const EMPTY = { name: "", doc_type: "cpf", doc_number: "", visitor_company: "", phone: "", plate: "", visit_reason: "", remember: false };

function validate(step, { isSite, isInvite, company, host, f, useSaved, photo, email }) {
  const e = {};
  if (step === 0) {
    if (isSite && !company) e.company_id = "Escolha a empresa";
    if (!isInvite && (!isSite || company) && !host) e.host_person_id = "Escolha quem você vai visitar";
  }
  if (step === 1 && !useSaved) {
    if (!validCpf(f.doc_number)) e.doc_number = "Digite um CPF válido";
    if (f.name.trim().length < 3) e.name = "Digite seu nome completo";
  }
  if (step === 1 && email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = "E-mail inválido";
  if (step === 2 && !useSaved && !photo) e.photo = "Tire a selfie para continuar";
  return e;
}

export default function SelfRegister({ mode }) {
  const params = useParams();
  const navigate = useNavigate();
  const ctxKey = mode === "invite" ? { invite: params.token } : { code: params.code };
  const [info, setInfo] = useState(null);
  const [fatal, setFatal] = useState("");
  const [phase, setPhase] = useState("intro");
  const [step, setStep] = useState(0);
  const [consent, setConsent] = useState(false);
  const [captcha, setCaptcha] = useState("");
  const [email, setEmail] = useState("");
  const [otpId, setOtpId] = useState("");
  const [otpMasked, setOtpMasked] = useState("");
  const [otp, setOtp] = useState("");
  const [verifyToken, setVerifyToken] = useState("");
  const [recurring, setRecurring] = useState(null);
  const [useSaved, setUseSaved] = useState(false);
  const [f, setF] = useState(EMPTY);
  const [host, setHost] = useState(null);
  const [company, setCompany] = useState(null);
  const [photo, setPhoto] = useState("");
  const [errors, setErrors] = useState({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => {
    setErrors((x) => (x[k] ? { ...x, [k]: "" } : x));
    setF((s) => ({ ...s, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e }));
  };
  const pickHost = (h) => { setErrors((x) => ({ ...x, host_person_id: "" })); setHost(h); };

  useEffect(() => {
    pub.get("/info", { params: ctxKey }).then(({ data }) => {
      setInfo(data);
      if (data.invite?.guest_email) setEmail(data.invite.guest_email);
      if (data.invite?.guest_name) setF((s) => ({ ...s, name: data.invite.guest_name }));
      if (data.companies?.length === 1) setCompany(data.companies[0]);
    }).catch((e) => setFatal(errMsg(e)));
  }, []); // eslint-disable-line
  useEffect(() => { window.scrollTo({ top: 0 }); }, [step, phase]);

  const run = async (fn) => {
    setBusy(true); setMsg(""); setErrors({});
    try { await fn(); } catch (e) {
      const fe = errFields(e);
      setErrors(fe); setMsg(Object.keys(fe).length ? "" : errMsg(e));
      const first = Object.keys(fe).map((k) => FIELD_STEP[k]).filter((s) => s !== undefined).sort((a, b) => a - b)[0];
      if (phase === "steps" && first !== undefined) setStep(first);
      scrollToError();
    } finally { setBusy(false); }
  };
  const sendOtp = () => run(async () => {
    const { data } = await pub.post("/otp", { ...ctxKey, email, captcha });
    setOtpId(data.otp_id); setOtpMasked(data.email); setOtp(""); setPhase("code");
  });
  const verify = () => run(async () => {
    const { data } = await pub.post("/verify", { ...ctxKey, otp_id: otpId, otp });
    setVerifyToken(data.verify_token); setRecurring(data.recurring); setUseSaved(!!data.recurring);
    if (data.recurring) setF((s) => ({ ...s, visitor_company: data.recurring.visitor_company || "", plate: data.recurring.plate || "", phone: data.recurring.phone || "" }));
    setPhase("steps");
  });
  const submit = () => run(async () => {
    const body = { ...ctxKey, company_id: company?.id || "", consent, captcha, verify_token: verifyToken, email, use_saved: useSaved, ...f,
      photo: useSaved ? "" : photo, host_person_id: host?.id || "" };
    const { data } = await pub.post("/submit", body);
    navigate(`/solicitacao/${data.status_token}`, { replace: true });
  });

  if (fatal) return <PublicShell title="Cadastro de visitante"><Box><p className="text-slate-200" data-testid="selfreg-fatal">{fatal}</p></Box></PublicShell>;
  if (!info) return <PublicShell title="Cadastro de visitante"><PageSkeleton /></PublicShell>;
  const isInvite = !!info.invite;
  const isSite = !!info.companies;
  const ctx = { isSite, isInvite, company, host, f, useSaved, photo, email };
  const skipSelfie = useSaved;
  const next = () => {
    const e = validate(step, ctx);
    setErrors(e); setMsg("");
    if (Object.keys(e).length) { scrollToError(); return; }
    setStep(step === 1 && skipSelfie ? 3 : step + 1);
  };
  const back = () => setStep(step === 3 && skipSelfie ? 1 : step - 1);
  const hours = isSite ? company?.duration_hours : info.duration_hours;
  const title = info.company || company?.name || info.site;
  const subtitle = `Cadastro de visitante${info.company || company ? ` · ${info.site}` : ""}`;
  const Err = () => (msg ? <Alert data-testid="selfreg-error">{msg}</Alert> : null);
  const spin = busy && <Loader2 className="h-5 w-5 motion-safe:animate-spin" />;

  if (phase !== "steps") {
    const bars = {
      intro: <PButton disabled={!consent} onClick={() => setPhase(info.otp ? "email" : "steps")} data-testid="selfreg-start">Começar</PButton>,
      email: <PButton disabled={busy || !email} onClick={sendOtp} data-testid="selfreg-send-otp">{spin}Enviar código</PButton>,
      code: <PButton disabled={busy || otp.length !== 6} onClick={verify} data-testid="selfreg-verify-otp">{spin}Confirmar</PButton>,
    };
    return (
      <PublicShell title={title} subtitle={subtitle} bar={bars[phase]}>
        {isInvite && <InviteCard invite={info.invite} />}
        <Box className="space-y-4 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200">
          {phase === "intro" && <Lgpd text={info.lgpd_text} consent={consent} setConsent={setConsent} />}
          {phase === "email" && <>
            <PField label="Seu e-mail" required error={errors.email} hint="Enviaremos um código de 6 dígitos para confirmar." htmlFor="sr-email">
              <input id="sr-email" className={inputCls} type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} placeholder="voce@empresa.com" />
            </PField>
            <Captcha siteKey={info.captcha_site_key} onToken={setCaptcha} />
          </>}
          {phase === "code" && <>
            <p className="text-sm text-slate-300">Digite o código enviado para <b>{otpMasked}</b>. Confira também a caixa de spam.</p>
            <PField label="Código" error={errors.otp} htmlFor="sr-otp">
              <input id="sr-otp" className={`${inputCls} text-center font-mono text-2xl tracking-[0.5em]`} inputMode="numeric" autoComplete="one-time-code" maxLength={6}
                value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))} />
            </PField>
            <button type="button" className="min-h-11 w-full text-sm text-sky-300 underline" onClick={() => setPhase("email")}>Reenviar ou trocar o e-mail</button>
          </>}
          <Err />
        </Box>
      </PublicShell>
    );
  }

  const bar = <>
    {step > 0 && <PButton variant="outline" className="w-14 shrink-0 px-0" onClick={back} aria-label="Voltar" data-testid="selfreg-back"><ArrowLeft className="h-5 w-5" /></PButton>}
    {step < 3 ? <PButton onClick={next} data-testid="selfreg-next">Continuar</PButton>
      : <PButton disabled={busy} onClick={submit} data-testid="selfreg-submit">{spin || <Send className="h-5 w-5" />}Enviar para aprovação</PButton>}
  </>;

  return (
    <PublicShell title={title} subtitle={subtitle} bar={bar}>
      <StepBar steps={STEPS} current={step} />
      {isInvite && step === 0 && <InviteCard invite={info.invite} />}
      <Box key={step} className="space-y-5 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-right-2 motion-safe:duration-200" data-testid={`selfreg-step-${step}`}>
        {step === 0 && <>
          <h1 className="text-lg font-bold">Sobre a visita</h1>
          {isSite && <CompanyPicker companies={info.companies} value={company} onPick={(c) => { setErrors((x) => ({ ...x, company_id: "" })); setCompany(c); setHost(null); }} error={errors.company_id} />}
          {!isInvite && (!isSite || company) && <HostSearch key={company?.id || "-"} ctxKey={{ ...ctxKey, company_id: company?.id || "" }} value={host} onPick={pickHost} error={errors.host_person_id} />}
          <PField label="Motivo da visita" hint="Opcional" htmlFor="sr-reason">
            <input id="sr-reason" className={inputCls} maxLength={200} value={f.visit_reason} onChange={set("visit_reason")} placeholder="Ex.: reunião, entrega, manutenção" data-testid="selfreg-reason-input" />
          </PField>
          {!isInvite && <p className="text-sm text-slate-400">A solicitação vai para o anfitrião. A visita começa quando ele aprovar{hours ? ` e vale por ${String(hours).replace(".", ",")} h` : ""}.</p>}
        </>}

        {step === 1 && <>
          <h1 className="text-lg font-bold">Seus dados</h1>
          {recurring && (
            <label className="flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border border-emerald-500/40 bg-emerald-500/5 px-4 py-3">
              {recurring.photo_thumb ? <img src={recurring.photo_thumb} alt="" className="h-14 w-11 rounded-lg object-cover" /> : <CheckCircle2 className="h-8 w-8 text-emerald-400" />}
              <span className="min-w-0 flex-1"><b>Olá de novo, {recurring.name.split(" ")[0]}!</b><span className="block text-sm text-slate-400">Usar meu cadastro salvo (sem nova selfie)</span></span>
              <input type="checkbox" className="h-6 w-6 accent-sky-500" checked={useSaved} onChange={(e) => setUseSaved(e.target.checked)} data-testid="selfreg-use-saved" />
            </label>
          )}
          {!useSaved && <>
            <CpfField value={f.doc_number} onChange={set("doc_number")} error={errors.doc_number} />
            <PField label="Nome completo" required error={errors.name} htmlFor="sr-name">
              <input id="sr-name" className={inputCls} autoComplete="name" autoCapitalize="words" value={f.name} onChange={set("name")} data-testid="selfreg-name-input" />
            </PField>
          </>}
          <PField label="Telefone" hint="Opcional" error={errors.phone} htmlFor="sr-phone">
            <input id="sr-phone" className={inputCls} type="tel" inputMode="tel" autoComplete="tel" value={f.phone} placeholder="(00) 00000-0000" onChange={(e) => set("phone")(maskPhone(e.target.value))} data-testid="selfreg-phone-input" />
          </PField>
          <PField label="Sua empresa" hint="Opcional" htmlFor="sr-vcomp">
            <input id="sr-vcomp" className={inputCls} autoCapitalize="words" value={f.visitor_company} onChange={set("visitor_company")} data-testid="selfreg-vcompany-input" />
          </PField>
          <PField label="Placa do veículo" hint="Se vier de carro" error={errors.plate} htmlFor="sr-plate">
            <input id="sr-plate" className={`${inputCls} uppercase`} autoCapitalize="characters" value={f.plate} placeholder="ABC1D23" onChange={(e) => set("plate")(maskPlate(e.target.value))} data-testid="selfreg-plate-input" />
          </PField>
          {!info.otp && (
            <PField label="E-mail" hint="Opcional, para receber a confirmação" error={errors.email} htmlFor="sr-email2">
              <input id="sr-email2" className={inputCls} type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} data-testid="selfreg-email-input" />
            </PField>
          )}
        </>}

        {step === 2 && <SelfieStep photo={photo} setPhoto={(p) => { setErrors((x) => ({ ...x, photo: "" })); setPhoto(p); }} error={errors.photo} />}

        {step === 3 && <>
          <h1 className="text-lg font-bold">Confira antes de enviar</h1>
          <div className="flex gap-4">
            {(useSaved ? recurring?.photo_thumb : photo) && <img src={useSaved ? recurring.photo_thumb : photo} alt="Sua foto" className="h-32 w-24 shrink-0 rounded-xl object-cover" data-testid="selfreg-review-photo" />}
            <div className="min-w-0 self-center">
              <p className="text-lg font-bold leading-tight">{useSaved ? recurring?.name : f.name}</p>
              {!useSaved && <p className="font-mono text-sm text-slate-400">CPF {f.doc_number}</p>}
              {!useSaved && <button type="button" className="mt-1 min-h-11 text-sm font-semibold text-sky-300 underline" onClick={() => setStep(2)}>Trocar foto</button>}
            </div>
          </div>
          <div>
            <ReviewRow label="Empresa visitada" value={company?.name || info.company} onEdit={isSite ? () => setStep(0) : null} testid="selfreg-review-company" />
            <ReviewRow label="Anfitrião" value={host?.name || info.invite?.host_name} onEdit={isInvite ? null : () => setStep(0)} testid="selfreg-review-host" />
            <ReviewRow label="Motivo da visita" value={f.visit_reason} onEdit={() => setStep(0)} testid="selfreg-review-reason" />
            <ReviewRow label="Telefone" value={f.phone} onEdit={() => setStep(1)} />
            <ReviewRow label="Sua empresa" value={f.visitor_company} onEdit={() => setStep(1)} />
            <ReviewRow label="Placa" value={f.plate} onEdit={() => setStep(1)} />
            <ReviewRow label="E-mail" value={email} onEdit={info.otp ? null : () => setStep(1)} />
          </div>
          {info.otp && !useSaved && (
            <label className="flex min-h-14 cursor-pointer items-start gap-3 rounded-xl border border-slate-700 px-4 py-3">
              <input type="checkbox" className="mt-0.5 h-6 w-6 shrink-0 accent-sky-500" checked={f.remember} onChange={set("remember")} />
              <span className="text-sm">Lembrar meu cadastro para as próximas visitas <span className="block text-xs text-slate-400">Sua foto fica guardada e é apagada após 12 meses sem visitas.</span></span>
            </label>
          )}
          {!info.otp && <Captcha siteKey={info.captcha_site_key} onToken={setCaptcha} />}
          {errors.consent && <Alert>{errors.consent}</Alert>}
        </>}
        <Err />
      </Box>
    </PublicShell>
  );
}
