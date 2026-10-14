import { useCallback, useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FileSpreadsheet, FileText, Loader2, Search } from "lucide-react";
import { toast } from "sonner";

const KINDS = [
  ["access", "Acessos"], ["visits", "Visitas"], ["present", "Presentes agora"], ["people", "Pessoas cadastradas"], ["denied", "Negados / desconhecidos"],
];
const USES = {
  access: ["period", "company", "person", "ptype", "door", "result", "category"],
  denied: ["period", "company", "person", "ptype", "door", "category"],
  visits: ["period", "company", "person", "category", "vstatus"],
  present: ["company", "person", "ptype", "category"],
  people: ["company", "person", "ptype", "category"],
};
const sel = "h-9 w-full rounded-md border border-input bg-field px-2 text-sm focus:border-sky-500 focus:outline-none";
const today = () => new Date().toLocaleDateString("en-CA");
const daysAgo = (n) => new Date(Date.now() - n * 864e5).toLocaleDateString("en-CA");
const EMPTY = { start: daysAgo(7), end: today(), company_id: "", person: "", person_type: "", door_id: "", result: "", category_id: "", status: "" };
const list = (d) => (Array.isArray(d) ? d : d?.items || []);

function useOptions() {
  const [o, setO] = useState({ companies: [], doors: [], categories: [] });
  useEffect(() => {
    api.get("/registry/companies").then(({ data }) => setO((s) => ({ ...s, companies: list(data) }))).catch(() => {});
    api.get("/equipment/access-points/all").then(({ data }) => setO((s) => ({ ...s, doors: list(data) }))).catch(() => {});
    api.get("/access/categories/all").then(({ data }) => setO((s) => ({ ...s, categories: list(data) }))).catch(() => {});
  }, []);
  return o;
}

const F = ({ label, children }) => <label className="space-y-1 text-xs text-muted-foreground"><span>{label}</span>{children}</label>;

function Filters({ kind, f, set, opts }) {
  const u = USES[kind];
  const s = (k) => (e) => set({ ...f, [k]: e.target.value });
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" data-testid="report-filters">
      {u.includes("period") && <F label="De"><Input type="date" value={f.start} onChange={s("start")} data-testid="report-filter-start" /></F>}
      {u.includes("period") && <F label="Até"><Input type="date" value={f.end} onChange={s("end")} data-testid="report-filter-end" /></F>}
      {u.includes("company") && <F label="Empresa"><select className={sel} value={f.company_id} onChange={s("company_id")} data-testid="report-filter-company"><option value="">Todas</option>{opts.companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></F>}
      {u.includes("person") && <F label="Pessoa"><Input value={f.person} onChange={s("person")} placeholder="Nome" data-testid="report-filter-person" /></F>}
      {u.includes("ptype") && <F label="Tipo"><select className={sel} value={f.person_type} onChange={s("person_type")} data-testid="report-filter-ptype"><option value="">{kind === "people" ? "Fixos" : "Todos"}</option><option value="fixo">Fixo</option><option value="visitante">Visitante</option></select></F>}
      {u.includes("door") && <F label="Porta"><select className={sel} value={f.door_id} onChange={s("door_id")} data-testid="report-filter-door"><option value="">Todas</option>{opts.doors.map((d) => <option key={d.id} value={d.id}>{d.description || d.name}</option>)}</select></F>}
      {u.includes("result") && <F label="Resultado"><select className={sel} value={f.result} onChange={s("result")} data-testid="report-filter-result"><option value="">Todos</option><option value="granted">Liberado</option><option value="denied">Negado</option></select></F>}
      {u.includes("category") && <F label="Categoria"><select className={sel} value={f.category_id} onChange={s("category_id")} data-testid="report-filter-category"><option value="">Todas</option>{opts.categories.map((c) => <option key={c.id} value={c.id}>{c.code}{c.description ? ` · ${c.description}` : ""}</option>)}</select></F>}
      {u.includes("vstatus") && <F label="Status"><select className={sel} value={f.status} onChange={s("status")} data-testid="report-filter-status"><option value="">Todos</option>{["agendado", "presente", "finalizado", "expirado", "cancelado"].map((x) => <option key={x} value={x}>{x}</option>)}</select></F>}
    </div>
  );
}

function ResultTable({ data }) {
  if (!data) return null;
  return (
    <Card className="mt-4 overflow-x-auto border-border bg-card" data-testid="report-table">
      <Table>
        <TableHeader><TableRow>{data.columns.map((c) => <TableHead key={c.key} className="whitespace-nowrap">{c.label}</TableHead>)}</TableRow></TableHeader>
        <TableBody>
          {data.rows.slice(0, 500).map((r, i) => (
            <TableRow key={r.id || i}>{data.columns.map((c) => <TableCell key={c.key} className="whitespace-nowrap text-sm">{r[c.key] || "—"}</TableCell>)}</TableRow>
          ))}
          {data.rows.length === 0 && <TableRow><TableCell colSpan={data.columns.length} className="py-8 text-center text-muted-foreground">Nenhum registro encontrado.</TableCell></TableRow>}
        </TableBody>
      </Table>
    </Card>
  );
}

export default function Reports() {
  const opts = useOptions();
  const [kind, setKind] = useState("access");
  const [f, setF] = useState(EMPTY);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");
  const params = useCallback((format) => {
    const p = new URLSearchParams({ format });
    USES[kind].forEach((k) => {
      const keys = { period: ["start", "end"], company: ["company_id"], person: ["person"], ptype: ["person_type"], door: ["door_id"], result: ["result"], category: ["category_id"], vstatus: ["status"] }[k];
      keys.forEach((x) => { if (f[x]) p.set(x, f[x]); });
    });
    return p.toString();
  }, [kind, f]);
  const run = useCallback(async () => {
    setBusy("json");
    try { const { data: d } = await api.get(`/reports/data/${kind}?${params("json")}`); setData(d); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(""); }
  }, [kind, params]);
  useEffect(() => { run(); }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps
  const download = async (format) => {
    setBusy(format);
    try {
      const res = await api.get(`/reports/data/${kind}?${params(format)}`, { responseType: "blob" });
      const name = (res.headers["content-disposition"] || "").match(/filename="([^"]+)"/)?.[1] || `relatorio.${format}`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch { toast.error("Não foi possível gerar o arquivo"); } finally { setBusy(""); }
  };
  return (
    <div>
      <PageHeader title="Relatórios" subtitle="Filtre, visualize e baixe em PDF ou Excel" />
      <div className="mb-4 flex flex-wrap gap-2" data-testid="report-kinds">
        {KINDS.map(([k, l]) => (
          <Button key={k} size="sm" variant={kind === k ? "default" : "outline"} className={kind === k ? "bg-sky-500 text-slate-950 hover:bg-sky-400" : ""}
            onClick={() => { setKind(k); setData(null); }} data-testid={`report-kind-${k}`}>{l}</Button>
        ))}
      </div>
      <Card className="border-border bg-card p-4">
        <Filters kind={kind} f={f} set={setF} opts={opts} />
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={run} disabled={!!busy} className="bg-sky-500 text-slate-950 hover:bg-sky-400" data-testid="report-run">{busy === "json" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}Gerar</Button>
          <Button variant="outline" onClick={() => download("pdf")} disabled={!!busy} data-testid="report-pdf">{busy === "pdf" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}PDF</Button>
          <Button variant="outline" onClick={() => download("xlsx")} disabled={!!busy} data-testid="report-xlsx">{busy === "xlsx" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileSpreadsheet className="mr-2 h-4 w-4" />}Excel</Button>
          <Button variant="ghost" onClick={() => setF(EMPTY)} data-testid="report-clear">Limpar filtros</Button>
          {data && <span className="ml-auto text-xs text-muted-foreground" data-testid="report-total">{data.total} registro(s){data.total >= data.limit ? ` · limitado a ${data.limit}` : ""}{data.total > 500 ? " · tela mostra 500, o arquivo traz todos" : ""}</span>}
        </div>
      </Card>
      <ResultTable data={data} />
    </div>
  );
}
