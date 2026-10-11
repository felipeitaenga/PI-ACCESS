import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CategoryMulti, CompanyCombo, Field, HostCombo, SuggestInput } from "@/components/registry/FormBits";
import { maskCpf, maskPhone, maskPlate } from "@/lib/br";
import { DOC_TYPES, maskDoc } from "@/components/visits/visitUtils";

const T = (f, set, errors, key, label, opts = {}) => (
  <Field label={label} required={opts.required} error={errors[key]} className={opts.className} hint={opts.hint}>
    {opts.onPick ? (
      <SuggestInput id={`f-${key}`} value={f[key] ?? ""} placeholder={opts.placeholder} kind={opts.kind} onPick={opts.onPick}
        onChange={(e) => set(key, opts.mask ? opts.mask(e.target.value) : e.target.value)} onBlur={opts.onBlur}
        inputMode={opts.inputMode} inputRef={opts.inputRef} className={errors[key] ? "border-red-500/60" : ""} testid={`f-${key}`} />
    ) : (
    <Input id={`f-${key}`} type={opts.type || "text"} value={f[key] ?? ""} placeholder={opts.placeholder}
      onChange={(e) => set(key, opts.mask ? opts.mask(e.target.value) : e.target.value)} onBlur={opts.onBlur}
      inputMode={opts.inputMode} ref={opts.inputRef} className={errors[key] ? "border-red-500/60" : ""} data-testid={`f-${key}`} />
    )}
  </Field>
);

export function CommonFields({ f, set, errors, companies, onCreateCompany, nameRef, onDocBlur, onPick, docSettings }) {
  const visitor = f.person_type === "visitante";
  const allowed = f.person_type === "terceiro" ? ["terceirizada", "transportadora"] : null;
  const sug = onPick ? { onPick, kind: visitor ? "visitor" : "person" } : {};
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {T(f, set, errors, "name", "Nome completo", { required: true, className: "sm:col-span-2", inputRef: nameRef, ...sug, hint: onPick ? "Digite 3 letras para localizar cadastros existentes" : undefined })}
      {visitor && T(f, set, errors, "document", "Documento (RG/Passaporte)", { required: true, onBlur: onDocBlur, ...sug, hint: "Se o visitante já existir, os dados e a foto são reaproveitados" })}
      {visitor && T(f, set, errors, "cpf", "CPF", { mask: maskCpf, placeholder: "000.000.000-00", inputMode: "numeric", ...sug })}
      {!visitor && (
        <Field label="Tipo de documento" required error={errors.doc_type}>
          <select id="f-doc_type" className="h-9 w-full rounded-md border border-input bg-field px-3 text-sm hover:border-sky-500/50 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/30" value={f.doc_type}
            onChange={(e) => { set("doc_type", e.target.value); set("doc_number", ""); }} data-testid="f-doc_type">
            {DOC_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
      )}
      {!visitor && T(f, set, errors, "doc_number", "Número do documento", { required: true, mask: (v) => maskDoc(f.doc_type, v, docSettings),
        placeholder: f.doc_type === "cpf" ? "000.000.000-00" : "", ...sug })}
      {T(f, set, errors, "birth", "Data de nascimento", { type: "date" })}
      {T(f, set, errors, "phone", "Telefone", { mask: maskPhone, placeholder: "(11) 90000-0000", inputMode: "tel" })}
      {T(f, set, errors, "email", "E-mail", { type: "email" })}
      {visitor ? T(f, set, errors, "origin_company", "Empresa de origem") : (
        <Field label={f.person_type === "terceiro" ? "Empresa terceirizada" : "Empresa"} required error={errors.company_id}>
          <CompanyCombo id="f-company_id" companies={companies} value={f.company_id} allowedTypes={allowed}
            onChange={(c) => { set("company_id", c.id); if (!f.category_ids.length && c.default_category_id) set("category_ids", [c.default_category_id]); }}
            onCreate={onCreateCompany} />
        </Field>
      )}
      {!visitor && (
        <label className="flex items-center gap-3 rounded-md border border-border px-3 py-2 text-sm sm:col-span-2">
          <Switch checked={f.can_authorize_visits} onCheckedChange={(v) => set("can_authorize_visits", v)} data-testid="f-can_authorize_visits" />
          Pode autorizar visitas (aparece como anfitrião no cadastro de visitante)
        </label>
      )}
      <Field label="Observações" className="sm:col-span-2">
        <Textarea rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} data-testid="f-notes" />
      </Field>
    </div>
  );
}

export function EmployeeFields({ f, set, errors, categories, departments }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {T(f, set, errors, "matricula", "Matrícula")}
      <Field label="Departamento">
        <Input id="f-department" list="dept-list" value={f.department} onChange={(e) => set("department", e.target.value)} data-testid="f-department" />
        <datalist id="dept-list">{departments.map((d) => <option key={d} value={d} />)}</datalist>
      </Field>
      {T(f, set, errors, "role_title", "Cargo")}
      {T(f, set, errors, "manager", "Gestor")}
      {T(f, set, errors, "admission_date", "Data de admissão", { type: "date" })}
      {T(f, set, errors, "valid_until", "Validade do acesso", { type: "date", hint: "Opcional — vazio = sem vencimento" })}
      <Field label="Categorias" required error={errors.category_ids} className="sm:col-span-2">
        <CategoryMulti categories={categories} value={f.category_ids} onChange={(v) => set("category_ids", v)} error={errors.category_ids} />
      </Field>
    </div>
  );
}

export function ThirdFields({ f, set, errors, categories }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {T(f, set, errors, "function", "Função")}
      {T(f, set, errors, "contract_manager", "Responsável / gestor do contrato")}
      {T(f, set, errors, "valid_from", "Início da validade", { type: "date", required: true })}
      {T(f, set, errors, "valid_until", "Fim da validade", { type: "date", required: true, hint: "Acesso bloqueado automaticamente ao vencer" })}
      <Field label="Categorias" required error={errors.category_ids} className="sm:col-span-2">
        <CategoryMulti categories={categories} value={f.category_ids} onChange={(v) => set("category_ids", v)} error={errors.category_ids} />
      </Field>
    </div>
  );
}

export function VisitorFields({ f, set, errors, categories }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Anfitrião (pessoa fixa)" required error={errors.host_id} className="sm:col-span-2">
        <HostCombo id="f-host_id" hostId={f.host_id} hostName={f.host_name} onChange={(p) => { set("host_id", p.id); set("host_name", p.name); }} />
      </Field>
      {T(f, set, errors, "reason", "Motivo da visita", { className: "sm:col-span-2" })}
      {T(f, set, errors, "expected_start", "Entrada prevista", { type: "datetime-local", required: true })}
      {T(f, set, errors, "expected_end", "Saída prevista", { type: "datetime-local", required: true })}
      <Field label="Categoria">
        <Select value={f.category_id || "default"} onValueChange={(v) => set("category_id", v === "default" ? "" : v)}>
          <SelectTrigger data-testid="f-category_id"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="default">VISITANTE (padrão)</SelectItem>
            {categories.filter((c) => c.code !== "VISITANTE").map((c) => <SelectItem key={c.id} value={c.id}>{c.code}</SelectItem>)}
          </SelectContent>
        </Select>
      </Field>
      <Field label="Credencial temporária">
        <Select value={f.credential_type} onValueChange={(v) => set("credential_type", v)}>
          <SelectTrigger data-testid="f-credential_type"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="qrcode">QR Code</SelectItem>
            <SelectItem value="cartao">Cartão de visitante</SelectItem>
            <SelectItem value="facial">Face</SelectItem>
          </SelectContent>
        </Select>
      </Field>
      {f.credential_type === "cartao" && T(f, set, errors, "credential_value", "Nº do cartão de visitante", { inputMode: "numeric" })}
      {f.credential_type === "qrcode" && T(f, set, errors, "credential_value", "Código QR", { hint: "Vazio = gerado automaticamente ao salvar" })}
      {T(f, set, errors, "vehicle_plate", "Veículo / placa", { mask: maskPlate, placeholder: "ABC1D23" })}
      <label className="flex items-center gap-3 rounded-md border border-border px-3 py-2 text-sm sm:col-span-2">
        <Switch checked={f.require_escort} onCheckedChange={(v) => set("require_escort", v)} data-testid="f-require_escort" />
        Exigir escort (acompanhante) em áreas restritas
      </label>
    </div>
  );
}
