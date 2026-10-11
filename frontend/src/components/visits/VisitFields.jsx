import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field, CompanyCombo } from "@/components/registry/FormBits";
import { cn } from "@/lib/utils";
import { addHours, endOfDay, DOC_TYPES, ID_TYPES, maskDoc, maskPlate } from "@/components/visits/visitUtils";

const sel = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

export function WhenFields({ v }) {
  const { f, set, setF, types, errors } = v;
  const manualEnd = (val) => setF((s) => ({ ...s, end_at: val, end_at_manual: true }));
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <Field label="Tipo da visita" required error={errors.visit_type_id}>
        <select className={sel} value={f.visit_type_id} onChange={(e) => set("visit_type_id", e.target.value)} data-testid="visit-type-select">
          <option value="">Selecione…</option>
          {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </Field>
      <Field label="Início" error={errors.start_at}>
        <Input type="datetime-local" value={f.start_at} onChange={(e) => set("start_at", e.target.value)} data-testid="visit-start-input" />
      </Field>
      <Field label="Fim da visita" required error={errors.end_at} hint={f.end_at_manual ? "Alterado manualmente" : "Calculado pela duração do tipo"}>
        <Input type="datetime-local" value={f.end_at} onChange={(e) => manualEnd(e.target.value)} data-testid="visit-end-input" />
        <div className="mt-1 flex gap-1">
          {[["+1h", 1], ["+4h", 4]].map(([l, h]) => (
            <Button key={l} type="button" size="sm" variant="outline" className="h-6 px-2 text-[11px]" onClick={() => manualEnd(addHours(f.end_at || f.start_at, h))} data-testid={`visit-end-plus-${h}`}>{l}</Button>
          ))}
          <Button type="button" size="sm" variant="outline" className="h-6 px-2 text-[11px]" onClick={() => manualEnd(endOfDay(f.start_at))} data-testid="visit-end-eod">Fim do dia</Button>
        </div>
      </Field>
    </div>
  );
}

function HostPicker({ companyId, value, name, onPick, error }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  useEffect(() => {
    if (!open || !companyId) return undefined;
    const t = setTimeout(() => api.get(`/registry/people?status=ativo&limit=10&company_id=${companyId}&q=${encodeURIComponent(q)}`)
      .then(({ data }) => setItems(data.items)).catch(() => setItems([])), 250);
    return () => clearTimeout(t);
  }, [q, open, companyId]);
  return (
    <Field label="Pessoa a ser visitada (anfitrião)" required error={error}>
      <div ref={ref} className="relative">
        <Input disabled={!companyId} value={open ? q : name} placeholder={companyId ? "Buscar pessoa ativa…" : "Escolha a empresa primeiro"}
          onFocus={() => { setOpen(true); setQ(""); }} onChange={(e) => setQ(e.target.value)} data-testid="visit-host-input" />
        {open && (
          <div className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-popover p-1 shadow-xl" data-testid="visit-host-list">
            {items.length === 0 && <p className="px-2 py-1.5 text-xs text-muted-foreground">Nenhuma pessoa ativa</p>}
            {items.map((p) => (
              <button key={p.id} type="button" onClick={() => { onPick(p); setOpen(false); }} className={cn("flex w-full flex-col rounded px-2 py-1.5 text-left hover:bg-secondary", value === p.id && "bg-secondary")} data-testid={`visit-host-option-${p.id}`}>
                <span className="text-sm">{p.name}</span><span className="text-[11px] text-muted-foreground">{p.department || p.role_title || p.company_name}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </Field>
  );
}

export function HostFields({ v, companies }) {
  const { f, setF, errors } = v;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Empresa a ser visitada" required error={errors.host_company_id}>
        <CompanyCombo companies={companies} value={f.host_company_id} allowedTypes={["propria", "cliente"]}
          onChange={(c) => setF((s) => ({ ...s, host_company_id: c.id, host_person_id: "", host_name: "" }))} onCreate={() => {}} />
      </Field>
      <HostPicker companyId={f.host_company_id} value={f.host_person_id} name={f.host_name} error={errors.host_person_id}
        onPick={(p) => setF((s) => ({ ...s, host_person_id: p.id, host_name: p.name }))} />
    </div>
  );
}

export function VisitorFields({ v }) {
  const { f, set, settings, errors } = v;
  const [sug, setSug] = useState([]);
  useEffect(() => {
    const t = setTimeout(() => api.get(`/visits/visitor-companies?q=${encodeURIComponent(f.visitor_company)}`).then(({ data }) => setSug(data)).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [f.visitor_company]);
  return (
    <div className="grid gap-3 sm:grid-cols-6">
      <Field className="sm:col-span-6" label="Nome completo do visitante" required error={errors.name}>
        <Input value={f.name} onChange={(e) => set("name", e.target.value)} data-testid="visit-name-input" />
      </Field>
      <Field className="sm:col-span-2" label="Tipo de documento" required error={errors.doc_type}>
        <select className={sel} value={f.doc_type} onChange={(e) => { set("doc_type", e.target.value); set("doc_number", ""); }} data-testid="visit-doc-type-select">
          {DOC_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </Field>
      <Field className="sm:col-span-4" label="Número do documento" required error={errors.doc_number}>
        <Input value={f.doc_number} onChange={(e) => set("doc_number", maskDoc(f.doc_type, e.target.value, settings))} className="font-mono" data-testid="visit-doc-number-input" />
      </Field>
      <Field className="sm:col-span-6" label="Empresa do visitante">
        <Input list="visitor-company-suggestions" value={f.visitor_company} onChange={(e) => set("visitor_company", e.target.value)} data-testid="visit-visitor-company-input" />
        <datalist id="visitor-company-suggestions">{sug.map((s) => <option key={s} value={s} />)}</datalist>
      </Field>
    </div>
  );
}

export function IdentifierFields({ v }) {
  const { f, set, errors, last } = v;
  const qr = last?.identifier?.type === "qrcode" ? last.identifier.value : "";
  return (
    <div className="grid gap-3 sm:grid-cols-6">
      <Field className="sm:col-span-3" label="Identificador do visitante" error={errors.identifier}>
        <div className="grid grid-cols-3 gap-1" data-testid="visit-identifier-type">
          {ID_TYPES.map(([k, l]) => (
            <button key={k} type="button" onClick={() => { set("id_type", k); set("id_value", ""); }} data-testid={`visit-id-type-${k}`}
              className={cn("rounded-md border px-2 py-2 text-xs font-medium transition-colors", f.id_type === k ? "border-sky-500 bg-sky-500/15 text-sky-300" : "border-border text-muted-foreground hover:text-foreground")}>{l}</button>
          ))}
        </div>
      </Field>
      <Field className="sm:col-span-3" label="Valor" hint={f.id_type === "cartao" ? "Decimal ou hexadecimal (ex.: 0x1A2B)" : f.id_type === "qrcode" ? "Gerado automaticamente ao salvar" : "Usa a foto do visitante"}>
        {f.id_type === "cartao" ? <Input value={f.id_value} onChange={(e) => set("id_value", e.target.value)} className="font-mono" data-testid="visit-card-input" />
          : <Input disabled value={f.id_type === "qrcode" ? qr || "(automático)" : "Foto"} className="font-mono" data-testid="visit-id-value" />}
      </Field>
      <Field className="sm:col-span-2" label="Placa do veículo" error={errors.plate}>
        <Input value={f.plate} onChange={(e) => set("plate", maskPlate(e.target.value))} placeholder="AAA0A00" className="font-mono uppercase" data-testid="visit-plate-input" />
      </Field>
      <Field className="sm:col-span-4" label="Observações">
        <Input value={f.notes} onChange={(e) => set("notes", e.target.value)} data-testid="visit-notes-input" />
      </Field>
    </div>
  );
}
