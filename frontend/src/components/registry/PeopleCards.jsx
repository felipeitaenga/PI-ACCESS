import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { Car, CreditCard, KeyRound, QrCode, ScanFace, UserRound } from "lucide-react";

const STATUS_DOT = { ativo: "bg-emerald-500", inativo: "bg-slate-500", bloqueado: "bg-red-500", vencido: "bg-amber-500" };
const CRED_ICON = { facial: ScanFace, cartao: CreditCard, qrcode: QrCode, pin: KeyRound, placa: Car };
const VISIT_CLS = { presente: "text-emerald-400", agendado: "text-sky-300", finalizado: "text-muted-foreground", expirada: "text-amber-400" };

function Thumb({ src }) {
  return src ? <img src={src} alt="" className="h-12 w-9 shrink-0 rounded object-cover" loading="lazy" /> : (
    <div className="flex h-12 w-9 shrink-0 items-center justify-center rounded bg-secondary"><UserRound className="h-4 w-4 text-muted-foreground" /></div>
  );
}

export function PersonCard({ p, active, checked, onCheck, onOpen }) {
  return (
    <div className={cn("flex items-center gap-2.5 rounded-md border px-2.5 py-2 transition-colors", active ? "border-sky-500 bg-sky-500/10" : "border-border bg-card/40 hover:border-sky-500/40")} data-testid={`person-card-${p.id}`}>
      <Checkbox checked={checked} onCheckedChange={onCheck} data-testid={`person-check-${p.id}`} />
      <button type="button" className="flex min-w-0 flex-1 items-center gap-2.5 text-left" onClick={onOpen} data-testid={`person-open-${p.id}`}>
        <Thumb src={p.photo_thumb} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className={cn("h-2 w-2 shrink-0 rounded-full", STATUS_DOT[p.status] || "bg-slate-500")} title={p.status} data-testid={`person-status-${p.id}`} />
            <span className="truncate text-sm font-medium">{p.name}</span>
          </div>
          <p className="truncate font-mono text-[11px] text-muted-foreground">{p.matricula || p.cpf}{p.category_names?.[0] ? ` · ${p.category_names[0]}` : ""}</p>
          <div className="mt-0.5 flex items-center gap-1.5 text-muted-foreground">
            {(p.cred_types || []).map((t) => { const I = CRED_ICON[t]; return I ? <I key={t} className="h-3 w-3" title={t} /> : null; })}
            {p.present && <span className="ml-auto rounded bg-emerald-500/15 px-1.5 text-[10px] text-emerald-300">no site</span>}
          </div>
        </div>
      </button>
    </div>
  );
}

export function VisitorCard({ v, active, onOpen }) {
  const lv = v.last_visit;
  return (
    <button type="button" onClick={onOpen} data-testid={`visitor-card-${v.id}`}
      className={cn("flex w-full items-center gap-2.5 rounded-md border px-2.5 py-2 text-left transition-colors", active ? "border-sky-500 bg-sky-500/10" : "border-border bg-card/40 hover:border-sky-500/40")}>
      <Thumb src={v.photo_thumb} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5"><span className="truncate text-sm font-medium">{v.name}</span>
          {v.blacklist && <span className="rounded bg-red-500/20 px-1.5 text-[10px] font-bold text-red-300">LISTA NEGRA</span>}</div>
        <p className="truncate font-mono text-[11px] text-muted-foreground">{v.document} · {v.origin_company}</p>
        {lv && <p className={cn("truncate text-[11px] uppercase", VISIT_CLS[lv.status])}>{lv.status} · {lv.host_name}</p>}
      </div>
    </button>
  );
}
