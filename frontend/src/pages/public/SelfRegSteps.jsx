import { useEffect, useRef, useState } from "react";
import { Building2, Camera, ChevronDown, ChevronRight, Glasses, HardHat, Pencil, RotateCcw, Search, ShieldCheck, Sun, UserCheck } from "lucide-react";
import { CameraCapture } from "@/components/CameraCapture";
import { maskCpf, validCpf } from "@/lib/br";
import { PButton, PField, fmtDT, inputCls, pub } from "./common";

export const maskPlate = (v) => {
  const r = String(v || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);
  return /^[A-Z]{3}\d{4}$/.test(r) ? `${r.slice(0, 3)}-${r.slice(3)}` : r;
};
export const maskPhone = (v) => {
  const d = String(v || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d;
  if (d.length <= 7) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, d.length - 4)}-${d.slice(-4)}`;
};

const cardCls = "flex min-h-14 w-full items-center gap-3 rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-left transition-[border-color,background-color] duration-150 hover:border-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400";
const Initial = ({ name }) => <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sky-500/15 font-bold text-sky-300">{(name || "?")[0]}</span>;

function Picked({ icon: Icon, label, name, onChange, testid }) {
  return (
    <PField label={label} required>
      <div className="flex min-h-14 items-center gap-3 rounded-xl border border-sky-500/60 bg-sky-500/10 px-4" data-testid={testid}>
        <Icon className="h-5 w-5 shrink-0 text-sky-400" /><span className="flex-1 font-medium">{name}</span>
        <button type="button" className="min-h-11 px-2 text-sm font-semibold text-sky-300 underline" onClick={onChange}>Trocar</button>
      </div>
    </PField>
  );
}

export function HostSearch({ ctxKey, value, onPick, error }) {
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
  if (value) return <Picked icon={UserCheck} label="Quem você vai visitar" name={value.name} onChange={() => { onPick(null); setQ(""); }} testid="selfreg-host-picked" />;
  return (
    <PField label="Quem você vai visitar" required error={error} hint="Digite ao menos 3 letras do nome da pessoa" htmlFor="sr-host">
      <div className="relative">
        <Search className="absolute left-4 top-3.5 h-5 w-5 text-slate-500" />
        <input id="sr-host" className={`${inputCls} pl-11`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome da pessoa" autoComplete="off" autoCapitalize="words" data-testid="selfreg-host-input" />
      </div>
      {busy && <div className="mt-2 h-14 rounded-xl bg-slate-800/70 motion-safe:animate-pulse" />}
      {!busy && q.trim().length >= 3 && items.length === 0 && <p className="mt-2 text-sm text-slate-400">Ninguém encontrado. Confira o nome ou procure a recepção.</p>}
      <div className="mt-2 space-y-2">
        {items.map((p) => (
          <button key={p.id} type="button" onClick={() => onPick(p)} className={cardCls} data-testid={`selfreg-host-${p.id}`}>
            <Initial name={p.name} /><span className="flex-1">{p.name}</span><ChevronRight className="h-5 w-5 text-slate-500" />
          </button>
        ))}
      </div>
    </PField>
  );
}

export function CompanyPicker({ companies, value, onPick, error }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); } };
    document.addEventListener("pointerdown", h);
    return () => document.removeEventListener("pointerdown", h);
  }, []);
  const list = companies.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase()));
  if (value) return <Picked icon={Building2} label="Empresa que você vai visitar" name={value.name} onChange={() => onPick(null)} testid="selfreg-company-picked" />;
  return (
    <PField label="Empresa que você vai visitar" required error={error} hint="Toque para escolher ou digite o nome" htmlFor="sr-company">
      <div ref={ref}>
        <div className="relative">
          <Building2 className="absolute left-4 top-3.5 h-5 w-5 text-slate-500" />
          <input id="sr-company" className={`${inputCls} pl-11`} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
            placeholder="Selecione a empresa" autoComplete="off" data-testid="selfreg-company-input" />
        </div>
        {open && (
          <div className="mt-2 max-h-72 space-y-2 overflow-auto" data-testid="selfreg-company-list">
            {list.map((c) => (
              <button key={c.id} type="button" onClick={() => { onPick(c); setOpen(false); setQ(""); }} className={cardCls} data-testid={`selfreg-company-${c.id}`}>
                <Initial name={c.name} /><span className="flex-1">{c.name}</span><ChevronRight className="h-5 w-5 text-slate-500" />
              </button>
            ))}
            {list.length === 0 && <p className="text-sm text-slate-400">Nenhuma empresa encontrada.</p>}
          </div>
        )}
      </div>
    </PField>
  );
}

export function CpfField({ value, onChange, error }) {
  const bad = value.replace(/\D/g, "").length === 11 && !validCpf(value);
  return (
    <PField label="CPF" required error={error || (bad ? "CPF inválido. Confira os números." : "")} hint="Só números" htmlFor="sr-cpf">
      <input id="sr-cpf" className={inputCls} inputMode="numeric" pattern="[0-9.\-]*" autoComplete="off" value={value} placeholder="000.000.000-00"
        onChange={(e) => onChange(maskCpf(e.target.value))} data-testid="selfreg-cpf-input" />
    </PField>
  );
}

export function Lgpd({ text, consent, setConsent }) {
  const [full, setFull] = useState(false);
  const short = text.length > 220 ? `${text.slice(0, 220).trim()}…` : text;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sky-300"><ShieldCheck className="h-6 w-6" /><h1 className="text-lg font-bold text-white">Seus dados estão protegidos</h1></div>
      <p className="whitespace-pre-line text-sm leading-relaxed text-slate-300" data-testid="selfreg-lgpd-text">{full ? text : short}</p>
      {text.length > 220 && (
        <button type="button" className="flex min-h-11 items-center gap-1 text-sm font-semibold text-sky-300" onClick={() => setFull(!full)} data-testid="selfreg-lgpd-toggle">
          <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${full ? "rotate-180" : ""}`} />{full ? "Mostrar menos" : "Ler texto completo"}
        </button>
      )}
      <label className={`flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition-colors duration-150 ${consent ? "border-sky-500 bg-sky-500/10" : "border-slate-700"}`} data-testid="selfreg-consent">
        <input type="checkbox" className="h-6 w-6 shrink-0 accent-sky-500" checked={consent} onChange={(e) => setConsent(e.target.checked)} data-testid="selfreg-consent-checkbox" />
        <span className="text-sm">Li e concordo com o uso dos meus dados para controle de acesso.</span>
      </label>
    </div>
  );
}

const TIPS = [[Sun, "Lugar bem iluminado"], [HardHat, "Sem boné ou chapéu"], [Glasses, "Sem óculos"]];
export function SelfieStep({ photo, setPhoto, error }) {
  const [cam, setCam] = useState(false);
  return (
    <div className="space-y-4" data-field-error={error ? "true" : undefined}>
      <h1 className="text-lg font-bold">Tire uma selfie</h1>
      <p className="text-sm text-slate-300">Ela será usada para você entrar pelo leitor facial. Encaixe o rosto inteiro no oval, de frente.</p>
      <div className="grid grid-cols-3 gap-2">
        {TIPS.map(([Icon, t]) => (
          <div key={t} className="flex flex-col items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900 p-3 text-center text-xs text-slate-300"><Icon className="h-6 w-6 text-sky-400" />{t}</div>
        ))}
      </div>
      <button type="button" onClick={() => setCam(true)} className="mx-auto flex aspect-[3/4] w-48 items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed border-slate-700 bg-slate-950" data-testid="selfreg-selfie-preview">
        {photo ? <img src={photo} alt="Sua selfie" className="h-full w-full object-cover" /> : <span className="flex flex-col items-center gap-2 text-sm text-slate-400"><Camera className="h-10 w-10 text-slate-500" />Toque para abrir a câmera</span>}
      </button>
      {error && <p className="text-center text-sm text-red-400" role="alert">{error}</p>}
      <PButton variant={photo ? "outline" : "primary"} onClick={() => setCam(true)} data-testid="selfreg-take-selfie">
        {photo ? <><RotateCcw className="h-5 w-5" />Tirar outra</> : <><Camera className="h-5 w-5" />Abrir câmera</>}
      </PButton>
      <CameraCapture open={cam} onClose={() => setCam(false)} onCapture={setPhoto} />
    </div>
  );
}

export function ReviewRow({ label, value, onEdit, testid }) {
  if (!value) return null;
  return (
    <div className="flex items-center gap-3 border-b border-slate-800 py-3 last:border-0" data-testid={testid}>
      <div className="min-w-0 flex-1"><p className="text-xs text-slate-400">{label}</p><p className="break-words">{value}</p></div>
      {onEdit && <button type="button" onClick={onEdit} className="flex h-11 w-11 items-center justify-center rounded-lg text-sky-300 hover:bg-slate-800" aria-label={`Editar ${label}`}><Pencil className="h-4 w-4" /></button>}
    </div>
  );
}

export const InviteCard = ({ invite }) => (
  <div className="mb-4 rounded-2xl border border-sky-500/40 bg-sky-500/5 p-4" data-testid="selfreg-invite-card">
    <p className="text-sm text-slate-300">Convite de <b className="text-white">{invite.host_name}</b></p>
    <p className="text-sm text-slate-400">{fmtDT(invite.start_at)} até {fmtDT(invite.end_at)}</p>
  </div>
);
