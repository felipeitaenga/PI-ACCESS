import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { CategoryMulti } from "@/components/registry/FormBits";

export function CompanyAccess({ form, setForm }) {
  const [cats, setCats] = useState([]);
  const [types, setTypes] = useState([]);
  const [managers, setManagers] = useState([]);
  useEffect(() => {
    api.get("/access/categories/all").then(({ data }) => setCats(data)).catch(() => {});
    api.get("/visits/types").then(({ data }) => setTypes(data.map((t) => ({ id: t.id, code: t.name })))).catch(() => {});
  }, []);
  useEffect(() => {
    if (form.id) api.get(`/registry/companies/${form.id}/managers`).then(({ data }) => setManagers(data)).catch(() => {});
  }, [form.id]);
  const set = (k) => (v) => setForm({ ...form, [k]: v });
  return (
    <div className="space-y-3 rounded-md border border-sky-500/30 bg-sky-500/5 p-3" data-testid="company-access-section">
      <p className="font-heading text-xs font-bold uppercase tracking-widest text-sky-400">Acesso ao sistema (Gestor de empresa)</p>
      <div><p className="mb-1 text-xs font-semibold">Categorias que a empresa pode usar</p>
        <CategoryMulti categories={cats} value={form.allowed_category_ids || []} onChange={set("allowed_category_ids")} /></div>
      <div data-testid="company-allowed-visit-types"><p className="mb-1 text-xs font-semibold">Tipos de visita que a empresa pode usar</p>
        <CategoryMulti categories={types} value={form.allowed_visit_type_ids || []} onChange={set("allowed_visit_type_ids")} placeholder="Buscar e selecionar tipos de visita…" /></div>
      <div><p className="mb-1 text-xs font-semibold">Limite de pessoas ativas (vazio = sem limite)</p>
        <Input type="number" min="0" className="w-40" value={form.max_active_people ?? ""} onChange={(e) => set("max_active_people")(e.target.value ? +e.target.value : null)} data-testid="company-max-active" /></div>
      <div data-testid="company-managers-list"><p className="mb-1 text-xs font-semibold">Gestores vinculados</p>
        {managers.length === 0 ? <p className="text-xs text-muted-foreground">Nenhum gestor</p> : (
          <ul className="space-y-0.5 text-xs">
            {managers.map((m) => <li key={m.id}><Link to="/configuracoes/usuarios" className="text-sky-400 hover:underline">{m.name}</Link> <span className="text-muted-foreground">{m.email}</span></li>)}
          </ul>
        )}</div>
    </div>
  );
}
