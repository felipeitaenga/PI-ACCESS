import CrudPage, { enabledBadge } from "@/components/CrudPage";
import { CompanyAccess } from "@/components/CompanyAccess";

const COMP_TYPES = [
  { value: "propria", label: "Fixos" }, { value: "terceirizada", label: "Terceirizada" },
  { value: "transportadora", label: "Transportadora" }, { value: "cliente", label: "Cliente" },
];

export function Companies() {
  return (
    <CrudPage title="Empresas" subtitle="Próprias, terceirizadas, transportadoras e clientes" endpoint="/org/companies"
      defaultForm={{ name: "", cnpj: "", trade_name: "", type: "terceirizada", contract_valid_until: "", enabled: true }}
      formFields={[
        { key: "name", label: "Razão social", full: true },
        { key: "trade_name", label: "Nome fantasia" },
        { key: "cnpj", label: "CNPJ" },
        { key: "type", label: "Tipo", type: "select", options: COMP_TYPES },
        { key: "contract_valid_until", label: "Validade do contrato", type: "date" },
        { key: "access", label: "", full: true, type: "custom", render: (form, setForm) => <CompanyAccess form={form} setForm={setForm} /> },
      ]}
      columns={[
        { key: "name", label: "Razão social", render: (r) => <span className="font-medium">{r.name}</span> },
        { key: "cnpj", label: "CNPJ" },
        { key: "type", label: "Tipo", render: (r) => <span className="capitalize">{r.type}</span> },
        { key: "contract_valid_until", label: "Contrato" },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}

export function CompanyGroups() {
  return (
    <CrudPage title="Grupos de empresas" subtitle="Agrupamento de empresas" endpoint="/org/company-groups"
      defaultForm={{ name: "", enabled: true }}
      formFields={[{ key: "name", label: "Nome do grupo", full: true }]}
      columns={[{ key: "name", label: "Grupo" }, { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) }]} />
  );
}

export function Departments() {
  return (
    <CrudPage title="Departamentos" subtitle="Departamentos / centros de custo" endpoint="/org/departments"
      defaultForm={{ name: "", enabled: true }}
      formFields={[{ key: "name", label: "Nome", full: true }]}
      columns={[{ key: "name", label: "Departamento" }, { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) }]} />
  );
}

export function Vehicles() {
  return (
    <CrudPage title="Veículos" subtitle="Placas vinculadas a pessoas (LPR)" endpoint="/cadastros/vehicles"
      defaultForm={{ plate: "", model: "", color: "", enabled: true }}
      formFields={[
        { key: "plate", label: "Placa" }, { key: "model", label: "Modelo" }, { key: "color", label: "Cor" },
      ]}
      columns={[
        { key: "plate", label: "Placa", render: (r) => <span className="font-mono font-medium">{r.plate}</span> },
        { key: "model", label: "Modelo" }, { key: "color", label: "Cor" },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}

export function Identifiers() {
  return (
    <CrudPage title="Identificadores" subtitle="Cartões de acesso" endpoint="/cadastros/identifiers"
      defaultForm={{ type: "cartao", value: "", format: "Wiegand 26", active: true, enabled: true }}
      formFields={[
        { key: "type", label: "Tipo", type: "select", options: [{ value: "cartao", label: "Cartão" }] },
        { key: "value", label: "Número do cartão (decimal)" },
        { key: "hex", label: "Hexadecimal" },
        { key: "format", label: "Formato", type: "select", options: [
          { value: "Wiegand 26", label: "Wiegand 26" }, { value: "Wiegand 34", label: "Wiegand 34" }, { value: "MIFARE", label: "MIFARE" }] },
      ]}
      columns={[
        { key: "type", label: "Tipo", render: (r) => <span className="capitalize">{r.type}</span> },
        { key: "value", label: "Valor", render: (r) => <span className="font-mono">{r.value}</span> },
        { key: "hex", label: "Hexa", render: (r) => <span className="font-mono text-xs">{r.hex || "—"}</span> },
        { key: "format", label: "Formato" },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}

export function VisitorsList() {
  return (
    <CrudPage title="Visitantes" subtitle="Cadastro reaproveitável de visitantes" endpoint="/cadastros/visitors"
      defaultForm={{ name: "", document: "", phone: "", email: "", origin_company: "", blacklist: false, enabled: true }}
      formFields={[
        { key: "name", label: "Nome", full: true },
        { key: "document", label: "Documento" }, { key: "phone", label: "Telefone" },
        { key: "email", label: "E-mail" }, { key: "origin_company", label: "Empresa de origem" },
        { key: "blacklist", label: "Lista negra", type: "checkbox", hint: "Bloquear visitante" },
      ]}
      columns={[
        { key: "name", label: "Visitante", render: (r) => <span className="font-medium">{r.name}</span> },
        { key: "document", label: "Documento", render: (r) => <span className="font-mono">{r.document}</span> },
        { key: "origin_company", label: "Origem" },
        { label: "Lista negra", render: (r) => (r.blacklist ? "Sim" : "Não") },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}
