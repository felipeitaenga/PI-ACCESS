import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Section } from "@/components/registry/FormBits";
import { ResultBadge } from "@/components/common";
import { daysUntil, fmtDateTime, maskPlate, onlyDigits } from "@/lib/br";
import { fileToDataUrl } from "@/lib/image";
import { Car, FileText, History, KeyRound, Paperclip, Plus, ScanFace, Trash2 } from "lucide-react";
import { toast } from "sonner";

const upd = (list, i, patch) => list.map((x, j) => (j === i ? { ...x, ...patch } : x));

function wiegand(value, format) {
  if (!value) return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  if (format === "Wiegand 34") return `FC ${Math.floor(n / 65536) % 65536} · CN ${n % 65536}`;
  return `FC ${Math.floor(n / 65536) % 256} · CN ${n % 65536}`;
}

function CredRow({ c, i, list, onChange, error }) {
  const set = (patch) => onChange(upd(list, i, patch));
  const hex = c.type === "cartao" && c.value ? Number(c.value).toString(16).toUpperCase() : "";
  return (
    <div className="grid grid-cols-12 items-start gap-2" data-testid={`cred-row-${i}`}>
      <div className="col-span-4 sm:col-span-3">
        <Select value={c.type} onValueChange={(v) => set({ type: v, value: "" })} disabled={c.type === "cartao"}>
          <SelectTrigger data-testid={`cred-type-${i}`}><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="cartao">Cartão</SelectItem>{c.type === "qrcode" && <SelectItem value="qrcode">QR Code</SelectItem>}{c.type === "pin" && <SelectItem value="pin">PIN</SelectItem>}</SelectContent>
        </Select>
      </div>
      <div className="col-span-8 sm:col-span-4">
        <Input id={`f-identifiers.${i}`} value={c.value} inputMode={c.type === "qrcode" ? "text" : "numeric"} placeholder={c.type === "cartao" ? "Número do cartão" : c.type === "pin" ? "4 a 8 dígitos" : "Código"}
          onChange={(e) => set({ value: c.type === "qrcode" ? e.target.value : onlyDigits(e.target.value) })} className={error ? "border-red-500/60" : ""} data-testid={`cred-value-${i}`} />
        {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      </div>
      {c.type === "cartao" ? (
        <>
          <Input className="col-span-5 sm:col-span-2 font-mono" placeholder="Hexa" value={hex}
            onChange={(e) => { const h = e.target.value.replace(/[^0-9a-fA-F]/g, ""); set({ value: h ? String(parseInt(h, 16)) : "" }); }} data-testid={`cred-hex-${i}`} />
          <div className="col-span-5 sm:col-span-2">
            <Select value={c.format || "Wiegand 26"} onValueChange={(v) => set({ format: v })}>
              <SelectTrigger data-testid={`cred-format-${i}`}><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="Wiegand 26">Wiegand 26</SelectItem><SelectItem value="Wiegand 34">Wiegand 34</SelectItem><SelectItem value="MIFARE">MIFARE</SelectItem></SelectContent>
            </Select>
          </div>
        </>
      ) : c.type === "qrcode" ? (
        <Button type="button" variant="outline" className="col-span-10 sm:col-span-4" onClick={() => set({ value: `NXQ-${Math.random().toString(36).slice(2, 10).toUpperCase()}` })} data-testid={`cred-gen-${i}`}>Gerar código</Button>
      ) : <div className="hidden sm:col-span-4 sm:block" />}
      <Button type="button" variant="ghost" size="icon" className="col-span-2 sm:col-span-1 text-red-400" onClick={() => onChange(list.filter((_, j) => j !== i))} data-testid={`cred-remove-${i}`}><Trash2 className="h-4 w-4" /></Button>
      {c.type === "cartao" && c.value && <p className="col-span-12 -mt-1 font-mono text-[11px] text-muted-foreground">{wiegand(c.value, c.format)}</p>}
    </div>
  );
}

export function CredentialsSection({ f, set, errors }) {
  const list = f.identifiers;
  return (
    <Section title="Credenciais" icon={KeyRound} count={list.length + (f.photo ? 1 : 0)} testid="section-credentials">
      <div className="space-y-3">
        <div className="flex items-center gap-2 rounded-md bg-secondary/40 px-3 py-2 text-sm" data-testid="cred-face-status">
          <ScanFace className={f.photo ? "h-4 w-4 text-emerald-400" : "h-4 w-4 text-muted-foreground"} />
          Face: {f.photo ? "cadastrada a partir da foto" : "sem foto — capture a foto para habilitar"}
        </div>
        {list.map((c, i) => <CredRow key={i} c={c} i={i} list={list} onChange={(v) => set("identifiers", v)} error={errors[`identifiers.${i}`]} />)}
        <Button type="button" variant="outline" size="sm" onClick={() => set("identifiers", [...list, { type: "cartao", value: "", format: "Wiegand 26" }])} data-testid="cred-add-button"><Plus className="mr-1 h-4 w-4" />Adicionar credencial</Button>
      </div>
    </Section>
  );
}

export function VehiclesSection({ f, set }) {
  const list = f.vehicles;
  return (
    <Section title="Veículos" icon={Car} count={list.length} testid="section-vehicles">
      <div className="space-y-2">
        {list.map((v, i) => (
          <div key={i} className="grid grid-cols-12 gap-2" data-testid={`vehicle-row-${i}`}>
            <Input className="col-span-4 font-mono" placeholder="Placa" value={v.plate} onChange={(e) => set("vehicles", upd(list, i, { plate: maskPlate(e.target.value) }))} data-testid={`vehicle-plate-${i}`} />
            <Input className="col-span-4" placeholder="Modelo" value={v.model} onChange={(e) => set("vehicles", upd(list, i, { model: e.target.value }))} data-testid={`vehicle-model-${i}`} />
            <Input className="col-span-3" placeholder="Cor" value={v.color} onChange={(e) => set("vehicles", upd(list, i, { color: e.target.value }))} data-testid={`vehicle-color-${i}`} />
            <Button type="button" variant="ghost" size="icon" className="col-span-1 text-red-400" onClick={() => set("vehicles", list.filter((_, j) => j !== i))} data-testid={`vehicle-remove-${i}`}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={() => set("vehicles", [...list, { plate: "", model: "", color: "" }])} data-testid="vehicle-add-button"><Plus className="mr-1 h-4 w-4" />Adicionar veículo</Button>
      </div>
    </Section>
  );
}

function DocStatus({ date }) {
  const d = daysUntil(date);
  if (d === null) return <span className="text-[11px] text-muted-foreground">sem validade</span>;
  if (d < 0) return <span className="text-[11px] font-medium text-red-400">vencido há {-d}d</span>;
  if (d <= 7) return <span className="text-[11px] font-medium text-amber-400">vence em {d}d</span>;
  return <span className="text-[11px] text-emerald-400">válido</span>;
}

export function DocumentsSection({ f, set, errors, defaultOpen }) {
  const list = f.documents;
  const attach = async (i, file) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast.error("Arquivo maior que 2 MB"); return; }
    set("documents", upd(list, i, { file: await fileToDataUrl(file), file_name: file.name }));
  };
  return (
    <Section title="Documentos" icon={FileText} count={list.length} defaultOpen={defaultOpen} testid="section-documents">
      <p className="mb-3 text-xs text-muted-foreground">Documentos vencidos bloqueiam o acesso automaticamente (status “vencido”).</p>
      <datalist id="doc-types">{["ASO", "Integração", "NR-10", "NR-33", "NR-35", "CNH", "Contrato"].map((d) => <option key={d} value={d} />)}</datalist>
      <div className="space-y-2">
        {list.map((d, i) => (
          <div key={i} className="grid grid-cols-12 items-center gap-2" data-testid={`doc-row-${i}`}>
            <Input className="col-span-4" list="doc-types" placeholder="Tipo" value={d.type} onChange={(e) => set("documents", upd(list, i, { type: e.target.value }))} data-testid={`doc-type-${i}`} />
            <div className="col-span-4">
              <Input id={`f-documents.${i}`} type="date" value={(d.valid_until || "").slice(0, 10)} onChange={(e) => set("documents", upd(list, i, { valid_until: e.target.value }))} className={errors[`documents.${i}`] ? "border-red-500/60" : ""} data-testid={`doc-valid-${i}`} />
            </div>
            <div className="col-span-2 text-center"><DocStatus date={d.valid_until} /></div>
            <label className="col-span-1 flex cursor-pointer justify-center text-muted-foreground hover:text-sky-400" title={d.file_name || "Anexar arquivo"}>
              <Paperclip className={d.file ? "h-4 w-4 text-sky-400" : "h-4 w-4"} />
              <input type="file" className="hidden" accept="image/*,application/pdf" onChange={(e) => attach(i, e.target.files?.[0])} data-testid={`doc-file-${i}`} />
            </label>
            <Button type="button" variant="ghost" size="icon" className="col-span-1 text-red-400" onClick={() => set("documents", list.filter((_, j) => j !== i))} data-testid={`doc-remove-${i}`}><Trash2 className="h-4 w-4" /></Button>
            {errors[`documents.${i}`] && <p className="col-span-12 text-xs text-red-400">{errors[`documents.${i}`]}</p>}
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={() => set("documents", [...list, { type: "", valid_until: "", file: "", file_name: "" }])} data-testid="doc-add-button"><Plus className="mr-1 h-4 w-4" />Adicionar documento</Button>
      </div>
    </Section>
  );
}

export function HistorySection({ f }) {
  const visitor = f.person_type === "visitante";
  return (
    <Section title={visitor ? "Histórico de visitas" : "Histórico de acessos"} icon={History} count={f.history.length} testid="section-history">
      {!visitor && <p className="mb-3 text-sm">Área atual: <span className="font-medium text-sky-300" data-testid="history-current-area">{f.current_area_name || "—"}</span></p>}
      {f.history.length === 0 && <p className="text-sm text-muted-foreground">Sem registros.</p>}
      <div className="space-y-1.5">
        {f.history.map((h) => (
          <div key={h.id} className="flex items-center gap-3 rounded border border-border/60 px-3 py-1.5 text-xs" data-testid={`history-row-${h.id}`}>
            <span className="w-28 shrink-0 font-mono text-muted-foreground">{fmtDateTime(h.timestamp || h.expected_start)}</span>
            {visitor ? (
              <><span className="flex-1 truncate">Anfitrião: {h.host_name} · {h.reason}</span><span className="uppercase text-muted-foreground">{h.status}</span></>
            ) : (
              <><span className="flex-1 truncate">{h.door_name}{h.reason ? ` — ${h.reason}` : ""}</span><ResultBadge result={h.access_result} /></>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}
