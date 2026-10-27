import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { maskCnpj, onlyDigits } from "@/lib/br";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/registry/FormBits";
import { toast } from "sonner";

export const COMPANY_TYPES = { propria: "Fixos", terceirizada: "Terceirizada", transportadora: "Transportadora" };
const EMPTY = { cnpj: "", name: "", trade_name: "", type: "terceirizada", contract_valid_until: "", default_category_id: "" };

export function QuickCompanyDialog({ open, onOpenChange, categories, initialName = "", onCreated }) {
  const [f, setF] = useState(EMPTY);
  const [err, setErr] = useState({});
  useEffect(() => { if (open) { setF({ ...EMPTY, name: initialName }); setErr({}); } }, [open, initialName]);
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));

  const save = async () => {
    const e = {};
    if (!f.name.trim()) e.name = "Informe a razão social";
    if (f.cnpj && onlyDigits(f.cnpj).length !== 14) e.cnpj = "CNPJ deve ter 14 dígitos";
    setErr(e);
    if (Object.keys(e).length) return;
    try {
      const { data } = await api.post("/org/companies", { ...f, contract_valid_until: f.contract_valid_until || null, default_category_id: f.default_category_id || null });
      toast.success("Empresa cadastrada");
      onCreated(data);
      onOpenChange(false);
    } catch (er) { toast.error(formatApiErrorDetail(er.response?.data?.detail)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="quick-company-dialog">
        <DialogHeader><DialogTitle>Nova empresa</DialogTitle><DialogDescription>Cadastro rápido — complete os dados depois em Organização › Empresas.</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <Field label="CNPJ" error={err.cnpj}><Input value={f.cnpj} onChange={(e) => set("cnpj")(maskCnpj(e.target.value))} placeholder="00.000.000/0000-00" data-testid="company-cnpj-input" /></Field>
          <Field label="Tipo"><Select value={f.type} onValueChange={set("type")}><SelectTrigger data-testid="company-type-select"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(COMPANY_TYPES).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Razão social" required error={err.name} className="col-span-2"><Input autoFocus value={f.name} onChange={(e) => set("name")(e.target.value)} data-testid="company-name-input" /></Field>
          <Field label="Nome fantasia" className="col-span-2"><Input value={f.trade_name} onChange={(e) => set("trade_name")(e.target.value)} data-testid="company-trade-input" /></Field>
          <Field label="Validade do contrato"><Input type="date" value={f.contract_valid_until} onChange={(e) => set("contract_valid_until")(e.target.value)} data-testid="company-contract-input" /></Field>
          <Field label="Categoria padrão"><Select value={f.default_category_id} onValueChange={set("default_category_id")}><SelectTrigger data-testid="company-category-select"><SelectValue placeholder="Nenhuma" /></SelectTrigger><SelectContent>{categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.code}</SelectItem>)}</SelectContent></Select></Field>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button className="bg-sky-500 text-white hover:bg-sky-400" onClick={save} data-testid="company-save-button">Salvar empresa</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
