import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { DoorOpen, Loader2, Search, ShieldAlert, UserRound, X } from "lucide-react";
import { toast } from "sonner";

export const OVERRIDE_MAX_MIN = 10;
const QUICK = ["Conferido documento com foto", "Autorizado pelo anfitrião", "Falha no reconhecimento facial", "Entrega / prestação de serviço"];

/** Pode liberar este evento negado pelo feed? (operador, recente, ainda não liberado) */
export function canReleaseEvent(e, hasRole) {
  if (!e || e.access_result !== "denied" || e.released_by_event || !(e.access_point_id || e.door_id)) return false;
  if (!hasRole("admin", "operator", "reception")) return false;
  return (Date.now() - new Date(e.timestamp).getTime()) / 60000 <= OVERRIDE_MAX_MIN;
}

function Photo({ src, label }) {
  return (
    <div>
      <p className="mb-1 text-[10px] font-mono uppercase text-muted-foreground">{label}</p>
      {src ? <img src={src} alt="" className="aspect-[3/4] w-full rounded-md object-cover" />
        : <div className="flex aspect-[3/4] w-full items-center justify-center rounded-md bg-secondary"><UserRound className="h-6 w-6 text-muted-foreground" /></div>}
    </div>
  );
}

function PersonPicker({ value, onChange }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  useEffect(() => {
    if (q.trim().length < 2) { setItems([]); return undefined; }
    const t = setTimeout(() => api.get(`/registry/search?q=${encodeURIComponent(q)}`).then(({ data }) => setItems(data.slice(0, 6))).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [q]);
  if (value) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border p-2" data-testid="release-subject">
        {value.photo ? <img src={value.photo} alt="" className="h-10 w-8 rounded object-cover" /> : <UserRound className="h-5 w-5" />}
        <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{value.name}</p><p className="truncate text-[11px] text-muted-foreground">{value.company_name} · {value.match}</p></div>
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}><X className="h-4 w-4" /></Button>
      </div>
    );
  }
  return (
    <div className="relative">
      <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Quem está passando? (opcional) nome, CPF, placa…" data-testid="release-subject-search" />
      {items.length > 0 && (
        <div className="absolute z-30 mt-1 w-full rounded-md border border-border bg-popover p-1 shadow-xl">
          {items.map((it) => (
            <button key={`${it.kind}-${it.id}`} type="button" onClick={() => { onChange(it); setQ(""); }} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-secondary">
              {it.photo ? <img src={it.photo} alt="" className="h-8 w-6 rounded object-cover" /> : <UserRound className="h-4 w-4" />}
              <span className="flex-1 truncate text-sm">{it.name}</span><span className="text-[10px] text-muted-foreground">{it.status}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Liberação manual: de um evento negado (event) ou direto num ponto de acesso (point). */
export function ManualReleaseDialog({ event, point, onClose, onDone }) {
  const { user } = useAuth();
  const [reason, setReason] = useState("");
  const [subject, setSubject] = useState(null);
  const [busy, setBusy] = useState(false);
  const open = !!(event || point);
  useEffect(() => { if (open) { setReason(""); setSubject(null); } }, [open]);
  const adminOnly = event && /impeditiva|lista negra/i.test(event.reason || "");
  const blocked = adminOnly && user?.role !== "admin";

  const confirm = async () => {
    if (reason.trim().length < 3) { toast.error("Informe o motivo da liberação"); return; }
    setBusy(true);
    try {
      const { data } = event
        ? await api.post(`/events/${event.id}/release`, { reason })
        : await api.post(`/equipment/access-points/${point.id}/open`, { reason, subject: subject ? { kind: subject.kind, id: subject.id } : undefined });
      if (data.ok) toast.success("Liberado e registrado");
      else toast.warning(`Registrado, mas o equipamento não confirmou a abertura: ${data.device_detail || "sem resposta"}`);
      onDone?.(data.event);
      onClose();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="manual-release-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><DoorOpen className="h-5 w-5 text-amber-400" />Liberação manual</DialogTitle>
          <DialogDescription>
            {event ? <>Abre <b>{event.door_name}</b> para <b>{event.person_name}</b>, negado por: <span className="text-red-400">{event.reason}</span></>
              : <>Abre <b>{point?.description}</b> agora.</>} Fica registrado com o seu nome ({user?.name}).
          </DialogDescription>
        </DialogHeader>
        {event && (
          <div className="grid grid-cols-2 gap-3">
            <Photo src={event.person_photo} label="Cadastrada" />
            <Photo src={event.captured_photo} label="Capturada agora" />
          </div>
        )}
        {point && <PersonPicker value={subject} onChange={setSubject} />}
        <div>
          <p className="mb-1 text-xs font-semibold">Motivo <span className="text-sky-400">*</span></p>
          <div className="mb-2 flex flex-wrap gap-1">
            {QUICK.map((qk) => <button key={qk} type="button" onClick={() => setReason(qk)} className="rounded-full border border-border px-2 py-0.5 text-[11px] hover:border-sky-500/60">{qk}</button>)}
          </div>
          <Textarea value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="Ex.: conferido RG, autorizado pelo síndico…" data-testid="release-reason" />
        </div>
        {adminOnly && (
          <p className="flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />{blocked ? "Bloqueio por lista negra / categoria impeditiva: só o Administrador pode liberar." : "Atenção: bloqueio por lista negra / categoria impeditiva."}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button className="bg-amber-500 text-black hover:bg-amber-400" disabled={busy || blocked || reason.trim().length < 3} onClick={confirm} data-testid="release-confirm">
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <DoorOpen className="mr-2 h-4 w-4" />}Liberar agora
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ManualTag({ e }) {
  if (e.manual) return <span className="block text-[10px] font-medium text-amber-300" data-testid="manual-tag">● manual · {e.operator_name}</span>;
  if (e.released_by_name) return <span className="block text-[10px] font-medium text-amber-300" data-testid="released-tag">● liberado por {e.released_by_name}</span>;
  return null;
}
