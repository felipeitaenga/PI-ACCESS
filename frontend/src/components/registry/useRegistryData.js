import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";

export function useRegistryData() {
  const [companies, setCompanies] = useState([]);
  const [visitorData, setVisitorData] = useState(null);
  const [categories, setCategories] = useState([]);
  const [departments, setDepartments] = useState([]);
  const reload = useCallback(() => {
    api.get("/registry/companies").then(({ data }) => setCompanies(data)).catch(() => {});
    api.get("/registry/visitor-companies").then(({ data }) => setVisitorData(data)).catch(() => {});
  }, []);
  useEffect(() => {
    reload();
    api.get("/access/categories/all").then(({ data }) => setCategories(data.filter((c) => c.enabled !== false))).catch(() => {});
    api.get("/org/departments/all").then(({ data }) => setDepartments(data.map((d) => d.name))).catch(() => {});
  }, [reload]);
  return { companies, visitorData, categories, departments, reload };
}

export function useSearchHotkey(setOpen) {
  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopPropagation(); setOpen(true); }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, [setOpen]);
}

export function useOpenRecord() {
  const nav = useNavigate();
  return useCallback((kind, id) => nav(kind === "person" ? `/cadastro/fixos?person=${id}` : `/cadastro/visitantes?visitor=${id}`), [nav]);
}

function buildRequest(params, defaultType) {
  const p = Object.fromEntries(params);
  if (p.person) return { kind: "person", id: p.person };
  if (p.visitor) return { kind: "visitor", id: p.visitor };
  if (p.doc) return { kind: "lookup", document: p.doc };
  if (p.company) return { kind: "new", type: p.type || defaultType, company_id: p.company };
  if (p.origin) return { kind: "new", type: "visitante", origin_company: p.origin };
  return { kind: "new", type: defaultType };
}

export function useUrlRequest(defaultType) {
  const [params] = useSearchParams();
  const key = params.toString();
  const [request, setRequest] = useState(() => ({ ...buildRequest(params, defaultType), nonce: 0 }));
  const [first, setFirst] = useState(true);
  useEffect(() => {
    if (first) { setFirst(false); return; }
    setRequest({ ...buildRequest(params, defaultType), nonce: Date.now() });
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return request;
}
