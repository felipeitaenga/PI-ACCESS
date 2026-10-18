import { useCallback, useEffect, useRef, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { fromLocalInput, nowLocal } from "@/lib/br";
import { addHours, docError, plateError, typeHours } from "@/components/visits/visitUtils";
import { toast } from "sonner";

const blank = (keep = {}) => ({
  visit_type_id: "", start_at: nowLocal(), end_at: "", end_at_manual: false,
  host_company_id: "", host_person_id: "", host_name: "", name: "", doc_type: "cpf", doc_number: "",
  visitor_company: "", id_type: "facial", id_value: "", photo: "", plate: "", notes: "", visit_reason: "",
  blacklist: null, blacklist_justification: "", ...keep,
});

export function useVisitForm(onSaved) {
  const [f, setF] = useState(blank());
  const [types, setTypes] = useState([]);
  const [settings, setSettings] = useState({ validate_cpf: true, validate_rg: false, default_hours: 8 });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [sync, setSync] = useState(null);
  const [last, setLast] = useState(null);
  const picked = useRef("");
  const set = useCallback((k, v) => setF((s) => ({ ...s, [k]: v })), []);
  const vtype = types.find((t) => t.id === f.visit_type_id);

  useEffect(() => {
    api.get("/visits/types?active=true").then(({ data }) => {
      setTypes(data);
      const def = data.find((t) => t.name === "Visita padrão") || data[0];
      if (def) setF((s) => (s.visit_type_id ? s : { ...s, visit_type_id: def.id }));
    }).catch(() => {});
    api.get("/visits/settings").then(({ data }) => setSettings(data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (f.end_at_manual || !f.start_at) return;
    setF((s) => ({ ...s, end_at: addHours(s.start_at, typeHours(vtype, settings)) }));
  }, [f.visit_type_id, f.start_at, f.end_at_manual, vtype, settings]);

  useEffect(() => {
    if (docError(f.doc_type, f.doc_number, settings)) return undefined;
    if (picked.current === `${f.doc_type}|${f.doc_number}`) return undefined;
    const t = setTimeout(() => {
      api.get(`/visits/lookup?doc_type=${f.doc_type}&doc_number=${encodeURIComponent(f.doc_number)}`).then(({ data }) => {
        if (!data.found) { setF((s) => ({ ...s, blacklist: null })); return; }
        const v = data.visitor;
        setF((s) => ({ ...s, name: v.name || s.name, visitor_company: v.origin_company || s.visitor_company,
          photo: v.photo || s.photo, plate: v.plate || s.plate, blacklist: v.blacklist ? (v.blacklist_reason || "acesso proibido") : null }));
        toast.info(v.blacklist ? "Visitante em LISTA NEGRA" : "Visitante já cadastrado — dados reaproveitados");
      }).catch(() => {});
    }, 500);
    return () => clearTimeout(t);
  }, [f.doc_type, f.doc_number, settings]);

  const localErrors = () => {
    const e = {};
    if (!f.visit_type_id) e.visit_type_id = "Selecione o tipo da visita";
    if (!f.end_at) e.end_at = "Informe o fim da visita";
    if (!f.host_company_id) e.host_company_id = "Selecione a empresa visitada";
    if (!f.host_person_id) e.host_person_id = "Selecione o anfitrião";
    if (!f.name.trim()) e.name = "Informe o nome completo";
    const de = docError(f.doc_type, f.doc_number, settings);
    if (de) e.doc_number = de;
    if (f.id_type === "cartao" && !f.id_value.trim()) e.identifier = "Informe o número do cartão";
    if ((f.id_type === "facial" || vtype?.require_photo) && !f.photo) e.photo = "Foto obrigatória";
    const pe = plateError(f.plate);
    if (pe) e.plate = pe;
    return e;
  };

  const save = async (andNew) => {
    const e = localErrors();
    setErrors(e);
    if (Object.keys(e).length) { toast.error("Verifique os campos destacados"); return; }
    setBusy(true); setSync({ status: "sending", devices: [] });
    try {
      const { data } = await api.post("/visits", {
        visit_type_id: f.visit_type_id, start_at: fromLocalInput(f.start_at), end_at: fromLocalInput(f.end_at),
        end_at_manual: f.end_at_manual, host_company_id: f.host_company_id, host_person_id: f.host_person_id,
        name: f.name, doc_type: f.doc_type, doc_number: f.doc_number, visitor_company: f.visitor_company,
        identifier: { type: f.id_type, value: f.id_value }, photo: f.photo?.startsWith("data:") ? f.photo : "",
        plate: f.plate, notes: f.notes, visit_reason: f.visit_reason, blacklist_justification: f.blacklist_justification,
      });
      setSync({ status: "done", devices: data.sync });
      setLast(data.visit);
      toast.success(`Visita salva (${data.visit.status})`);
      if (andNew) setF(blank({ visit_type_id: f.visit_type_id, host_company_id: f.host_company_id }));
      onSaved?.();
    } catch (err) {
      setSync(null);
      const d = err.response?.data?.detail;
      if (d?.fields) setErrors(d.fields);
      toast.error(formatApiErrorDetail(d));
    } finally { setBusy(false); }
  };

  const endVisit = async () => {
    try {
      const { data } = await api.post(`/visits/${last.id}/end`);
      setSync({ status: "done", devices: data.sync });
      setLast({ ...last, status: "finalizado" });
      toast.success("Visita encerrada e removida do facial");
      onSaved?.();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const prefill = async (id) => {
    try {
      const { data } = await api.get(`/visits/visitor/${id}/prefill`);
      const v = data.visitor;
      const lv = data.last_visit || {};
      picked.current = `${v.doc_type}|${v.doc_number}`;
      setF((s) => ({
        ...s, name: v.name, doc_type: v.doc_type, doc_number: v.doc_number, visitor_company: v.origin_company,
        photo: v.photo || "", plate: lv.plate || v.plate || "", blacklist: v.blacklist ? (v.blacklist_reason || "acesso proibido") : null,
        ...(data.last_visit ? {
          visit_type_id: lv.visit_type_id || s.visit_type_id, host_company_id: lv.host_company_id || "",
          host_person_id: lv.host_person_id || "", host_name: lv.host_name || "", id_type: lv.id_type || "facial",
          id_value: lv.id_value || "", notes: lv.notes || "",
        } : {}),
        start_at: nowLocal(), end_at_manual: false,
      }));
      setErrors({});
      toast.info(v.blacklist ? "Visitante em LISTA NEGRA" : data.last_visit ? "Dados da última visita preenchidos" : "Dados do visitante preenchidos");
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const clear = () => { picked.current = ""; setF(blank({ visit_type_id: f.visit_type_id })); setErrors({}); setSync(null); setLast(null); };
  return { f, set, setF, types, vtype, settings, errors, busy, sync, last, save, endVisit, clear, prefill };
}
