import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { LgpdEraseButton } from "@/components/registry/LgpdEraseButton";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/registry/FormBits";
import { PhotoBlock } from "@/components/registry/PhotoBlock";
import { SyncStatus } from "@/components/registry/SyncStatus";
import { useAuth } from "@/context/AuthContext";
import { useVisitForm } from "@/components/visits/useVisitForm";
import { readCapture } from "@/components/registry/useRegistryData";
import { toast } from "sonner";
import { HostFields, IdentifierFields, VisitorFields, WhenFields } from "@/components/visits/VisitFields";
import { AlertOctagon, Eraser, LogOut, ShieldCheck } from "lucide-react";

const H = ({ children }) => <h3 className="mb-1.5 font-heading text-xs font-bold uppercase tracking-widest text-sky-400">{children}</h3>;

function CategoryTags({ vtype, categories }) {
  const codes = (vtype?.category_ids || []).map((id) => categories.find((c) => c.id === id)?.code || "?");
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="visit-category-tags">
      <span className="text-[11px] text-muted-foreground">Categorias de acesso:</span>
      {codes.length === 0 && <span className="text-[11px] text-muted-foreground">—</span>}
      {codes.map((c, i) => <span key={`${c}-${i}`} className="rounded-full border border-sky-500/40 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-300">{c}</span>)}
      {vtype?.require_escort && <span className="rounded-full border border-amber-500/40 px-2 py-0.5 text-[11px] text-amber-300">exige escort</span>}
    </div>
  );
}

function Blacklist({ v, isAdmin }) {
  if (!v.f.blacklist) return null;
  return (
    <div className="rounded-md border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-300" data-testid="visit-blacklist-alert">
      <p className="flex items-start gap-2"><AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" /><span><b>VISITANTE EM LISTA NEGRA.</b> {v.f.blacklist}</span></p>
      {isAdmin ? (
        <Textarea className="mt-2" placeholder="Justificativa para liberar (Administrador)" value={v.f.blacklist_justification}
          onChange={(e) => v.set("blacklist_justification", e.target.value)} data-testid="visit-blacklist-justification" />
      ) : <p className="mt-1 text-xs">Somente um Administrador pode liberar esta visita.</p>}
    </div>
  );
}

export function VisitForm({ companies, categories, onSaved }) {
  const v = useVisitForm(onSaved);
  const [params] = useSearchParams();
  const nav = useNavigate();
  const visitorParam = params.get("visitor");
  const captureParam = params.get("capture");
  const { prefill, clear, set } = v;
  useEffect(() => {
    if (visitorParam) { prefill(visitorParam); }
  }, [visitorParam]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const photo = captureParam && readCapture();
    if (!photo) { return; }
    clear(); set("photo", photo);
    toast.info("Foto capturada pelo facial carregada — preencha a visita");
  }, [captureParam]); // eslint-disable-line react-hooks/exhaustive-deps
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const blocked = v.f.blacklist && (!isAdmin || v.f.blacklist_justification.trim().length < 5);
  const active = v.last && ["agendado", "presente"].includes(v.last.status);
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="visit-form">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 lg:space-y-3 lg:p-3">
        <section>
          <div className="flex flex-wrap items-center justify-between gap-2"><H>Visita</H><div className="mb-1.5"><CategoryTags vtype={v.vtype} categories={categories} /></div></div>
          <WhenFields v={v} />
        </section>
        <section><H>Destino</H><HostFields v={v} companies={companies} /></section>
        <div className="grid gap-4 sm:grid-cols-[1fr_120px] lg:gap-3">
          <section className="space-y-3"><H>Visitante e identificação</H><VisitorFields v={v} /><IdentifierFields v={v} /></section>
          <Field label={`Foto${v.f.id_type === "facial" || v.vtype?.require_photo ? " *" : ""}`} error={v.errors.photo}>
            <PhotoBlock compact photo={v.f.photo} onChange={(p) => v.set("photo", p)} />
          </Field>
        </div>
        <Blacklist v={v} isAdmin={isAdmin} />
      </div>
      <div className="border-t border-border p-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* salva, envia ao facial e já deixa o formulário pronto para o próximo visitante */}
          <Button className="bg-sky-500 text-white hover:bg-sky-400" disabled={v.busy || blocked} onClick={() => v.save(true)} data-testid="visit-save-button"><ShieldCheck className="mr-2 h-4 w-4" />Salvar e liberar</Button>
          <div className="min-w-0 flex-1 px-1">
            <SyncStatus sync={v.sync} />
            {v.last && <p className="truncate text-[11px] text-muted-foreground" data-testid="visit-last-status">Última: {v.last.visitor_name} · <b>{v.last.status}</b>{v.last.identifier?.type === "qrcode" && ` · QR ${v.last.identifier.value}`}</p>}
          </div>
          {isAdmin && visitorParam && v.f.name && <LgpdEraseButton kind="visitor" id={visitorParam} name={v.f.name} onDone={() => { v.clear(); nav("/cadastro/visitantes"); onSaved?.(); }} />}
          <Button variant="outline" onClick={v.clear} data-testid="visit-clear-button"><Eraser className="mr-2 h-4 w-4" />Limpar</Button>
          <Button variant="outline" disabled={!active} onClick={v.endVisit} className="text-amber-300" data-testid="visit-end-button"><LogOut className="mr-2 h-4 w-4" />Encerrar visita</Button>
        </div>
      </div>
    </div>
  );
}
