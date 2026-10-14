import { fromLocalInput, nowLocal, toLocalInput, validCpf, onlyDigits } from "@/lib/br";
import { docError } from "@/components/visits/visitUtils";

const nn = (v) => v ?? "";

export const emptyForm = (type = "funcionario", extra = {}) => ({
  person_type: type, name: "", cpf: "", rg: "", document: "", doc_type: "cpf", doc_number: "", can_authorize_visits: true, birth: "", phone: "", email: "",
  company_id: "", notes: "", matricula: "", department: "", role_title: "", manager: "", admission_date: "",
  valid_from: "", valid_until: "", category_ids: [], status: "ativo", status_reason: "", photo: "", consent: false,
  function: "", contract_manager: "", identifiers: [], vehicles: [],
  documents: type === "terceiro" ? [{ type: "ASO", valid_until: "", file: "", file_name: "" }, { type: "Integração", valid_until: "", file: "", file_name: "" }] : [],
  history: [], current_area_name: "", present: false,
  visitor_id: null, visit_id: null, origin_company: "", host_id: "", host_name: "", reason: "",
  expected_start: nowLocal(0), expected_end: nowLocal(4), category_id: "", require_escort: true,
  credential_type: "qrcode", credential_value: "", vehicle_plate: "", blacklist: false, blacklist_reason: "", visit_status: "",
  ...extra,
});

export const mapPerson = (p) => emptyForm(p.person_type, {
  name: nn(p.name), cpf: nn(p.cpf), rg: nn(p.rg), document: nn(p.document), birth: nn(p.birth).slice(0, 10),
  doc_type: p.doc_type || "cpf", doc_number: nn(p.doc_number || p.cpf), can_authorize_visits: p.can_authorize_visits !== false,
  phone: nn(p.phone), email: nn(p.email), company_id: nn(p.company_id), notes: nn(p.notes), matricula: nn(p.matricula),
  department: nn(p.department), role_title: nn(p.role_title), manager: nn(p.manager),
  admission_date: nn(p.admission_date).slice(0, 10), valid_from: nn(p.valid_from).slice(0, 10),
  valid_until: nn(p.valid_until).slice(0, 10), category_ids: p.category_ids || [], status: p.status || "ativo",
  status_reason: nn(p.status_reason), photo: nn(p.photo), consent: !!p.consent, function: nn(p.function),
  contract_manager: nn(p.contract_manager),
  identifiers: (p.identifiers || []).map((i) => ({ type: i.type, value: nn(i.value), format: nn(i.format) })),
  vehicles: (p.vehicles || []).map((v) => ({ plate: nn(v.plate), model: nn(v.model), color: nn(v.color) })),
  documents: (p.documents || []).map((d) => ({ type: d.type, valid_until: nn(d.valid_until).slice(0, 10), file: nn(d.file), file_name: nn(d.file_name) })),
  history: p.history || [], current_area_name: nn(p.current_area_name), present: !!p.present,
});

export const mapVisitor = (v) => {
  const active = (v.visits || []).find((x) => ["agendado", "presente"].includes(x.status));
  return emptyForm("visitante", {
    visitor_id: v.id, name: nn(v.name), document: nn(v.document), cpf: nn(v.cpf), rg: nn(v.rg), birth: nn(v.birth).slice(0, 10),
    phone: nn(v.phone), email: nn(v.email), origin_company: nn(v.origin_company), notes: nn(v.notes), photo: nn(v.photo),
    blacklist: !!v.blacklist, blacklist_reason: nn(v.blacklist_reason), history: v.visits || [],
    ...(active ? {
      visit_id: active.id, host_id: active.host_id, host_name: active.host_name, reason: nn(active.reason),
      expected_start: toLocalInput(active.expected_start), expected_end: toLocalInput(active.expected_end),
      category_id: nn(active.category_id), require_escort: active.require_escort !== false,
      credential_type: active.credential_type || "qrcode", credential_value: nn(active.credential_value),
      vehicle_plate: nn(active.vehicle_plate), visit_status: active.status,
    } : {}),
  });
};

export function validate(f, docSettings) {
  const e = {};
  const visitor = f.person_type === "visitante";
  if (!f.name.trim()) e.name = "Informe o nome completo";
  if (visitor) {
    if (!f.document.trim()) e.document = "Informe o documento";
    if (f.cpf && !validCpf(f.cpf)) e.cpf = "CPF inválido";
    if (!f.host_id) e.host_id = "Selecione o anfitrião";
    if (!f.expected_start) e.expected_start = "Informe a entrada prevista";
    if (!f.expected_end) e.expected_end = "Informe a saída prevista";
    else if (f.expected_start && f.expected_end <= f.expected_start) e.expected_end = "Saída deve ser após a entrada";
  } else {
    const de = docError(f.doc_type, f.doc_number, docSettings || { validate_cpf: true });
    if (de) e.doc_number = de;
    if (!f.company_id) e.company_id = "Selecione a empresa";
    if (!f.category_ids.length) e.category_ids = "Selecione ao menos uma categoria";
  }
  if (f.email && !/^\S+@\S+\.\S+$/.test(f.email)) e.email = "E-mail inválido";
  if (f.person_type === "terceiro") {
    if (!f.valid_from) e.valid_from = "Informe o início da validade";
    if (!f.valid_until) e.valid_until = "Informe o fim da validade";
    else if (f.valid_from && f.valid_until < f.valid_from) e.valid_until = "Fim deve ser após o início";
    f.documents.forEach((d, i) => { if (d.type && !d.valid_until) e[`documents.${i}`] = `Informe a validade de ${d.type}`; });
  }
  f.identifiers.forEach((c, i) => {
    if (c.type === "cartao" && !onlyDigits(c.value)) e[`identifiers.${i}`] = "Informe o número do cartão";
    if (c.type === "placa" && !/^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$/.test(c.value || "")) e[`identifiers.${i}`] = "Placa inválida (ex.: ABC1234 ou ABC1D23)";
    if (c.type === "pin" && !/^\d{4,8}$/.test(c.value)) e[`identifiers.${i}`] = "PIN deve ter de 4 a 8 dígitos";
    if (c.type === "qrcode" && !c.value.trim()) e[`identifiers.${i}`] = "Informe ou gere o código";
  });
  return e;
}

const PERSON_KEYS = ["person_type", "name", "cpf", "rg", "document", "doc_type", "doc_number", "can_authorize_visits", "birth", "phone", "email", "company_id", "notes",
  "matricula", "department", "role_title", "manager", "admission_date", "valid_from", "valid_until", "category_ids",
  "status", "photo", "consent", "function", "contract_manager", "identifiers", "vehicles", "documents"];

export const personBody = (f) => {
  const b = Object.fromEntries(PERSON_KEYS.map((k) => [k, f[k] === "" ? null : f[k]]));
  if (b.status === "vencido") b.status = "ativo";
  b.documents = f.documents.filter((d) => d.type);
  return b;
};

export const visitPayload = (f, checkin) => ({
  checkin,
  visitor: {
    id: f.visitor_id, name: f.name, document: f.document, cpf: f.cpf, rg: f.rg, birth: f.birth, phone: f.phone,
    email: f.email, origin_company: f.origin_company, notes: f.notes, ...(f.photo?.startsWith("data:") || !f.visitor_id ? { photo: f.photo } : {}),
  },
  visit: {
    id: f.visit_id, host_id: f.host_id, reason: f.reason, expected_start: fromLocalInput(f.expected_start),
    expected_end: fromLocalInput(f.expected_end), category_id: f.category_id || null, require_escort: f.require_escort,
    credential_type: f.credential_type, credential_value: f.credential_value, vehicle_plate: f.vehicle_plate,
  },
});
