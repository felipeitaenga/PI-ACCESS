import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { CompanyColumn } from "@/components/registry/CompanyColumn";
import { PeopleColumn } from "@/components/registry/PeopleColumn";
import { PersonForm } from "@/components/registry/PersonForm";
import { GlobalSearch } from "@/components/registry/GlobalSearch";
import { PresentVisitors } from "@/components/registry/PresentVisitors";
import { QuickCompanyDialog } from "@/components/registry/QuickCompanyDialog";
import { IdCard, Search } from "lucide-react";

const TITLES = {
  people: ["Pessoas e Empresas", "Navegue por empresa · cadastro fixo sempre disponível"],
  visitors: ["Visitantes", "Visitantes por empresa de origem · agendamento e credencial temporária"],
  portaria: ["Portaria", "Recepção de visitantes · check-in e check-out"],
};

function MobileTabs({ tabs, tab, setTab }) {
  return (
    <div className="mb-3 grid gap-1 rounded-lg border border-border bg-card p-1 lg:hidden" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }} data-testid="registry-mobile-tabs">
      {tabs.map(([k, l]) => (
        <button key={k} type="button" onClick={() => setTab(k)} data-testid={`mobile-tab-${k}`}
          className={cn("rounded-md py-2 text-xs font-medium transition-colors", tab === k ? "bg-sky-500/20 text-sky-200" : "text-muted-foreground")}>{l}</button>
      ))}
    </div>
  );
}

function DocSearch({ onSearch }) {
  const [doc, setDoc] = useState("");
  const go = () => doc.trim() && onSearch(doc.trim());
  return (
    <Card className="mb-4 flex flex-col gap-2 border-sky-500/30 bg-card p-3 sm:flex-row" data-testid="portaria-doc-search">
      <div className="relative flex-1">
        <IdCard className="absolute left-4 top-3.5 h-5 w-5 text-sky-400" />
        <Input autoFocus className="h-12 pl-12 text-lg" placeholder="Buscar por documento (RG, CPF, passaporte)…" value={doc}
          onChange={(e) => setDoc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} data-testid="portaria-doc-input" />
      </div>
      <Button className="h-12 bg-sky-500 px-6 text-slate-950 hover:bg-sky-400" onClick={go} data-testid="portaria-doc-button"><Search className="mr-2 h-4 w-4" />Buscar</Button>
    </Card>
  );
}

export default function Registry({ mode = "people" }) {
  const portaria = mode === "portaria";
  const visitorMode = mode !== "people";
  const [companies, setCompanies] = useState([]);
  const [visitorData, setVisitorData] = useState(null);
  const [categories, setCategories] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [selection, setSelection] = useState(visitorMode ? { kind: "visitors_today", name: "Visitantes do dia" } : null);
  const [request, setRequest] = useState({ kind: "new", type: visitorMode ? "visitante" : "funcionario", nonce: 0 });
  const [activeId, setActiveId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [tab, setTab] = useState(portaria ? "form" : "companies");
  const [searchOpen, setSearchOpen] = useState(false);
  const [companyDlg, setCompanyDlg] = useState(false);

  const loadCompanies = useCallback(() => {
    api.get("/registry/companies").then(({ data }) => setCompanies(data)).catch(() => {});
    api.get("/registry/visitor-companies").then(({ data }) => setVisitorData(data)).catch(() => {});
  }, []);
  useEffect(() => { loadCompanies(); }, [loadCompanies, refreshKey]);
  useEffect(() => {
    api.get("/access/categories/all").then(({ data }) => setCategories(data.filter((c) => c.enabled !== false))).catch(() => {});
    api.get("/org/departments/all").then(({ data }) => setDepartments(data.map((d) => d.name))).catch(() => {});
  }, []);
  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopPropagation(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, []);

  const open = (kind, id) => { setActiveId(id); setRequest({ kind, id, nonce: Date.now() }); setTab("form"); };
  const newIn = (sel) => {
    setActiveId(null);
    if (sel.kind === "company") setRequest({ kind: "new", type: sel.company?.type === "propria" ? "funcionario" : "terceiro", company_id: sel.id, nonce: Date.now() });
    else setRequest({ kind: "new", type: "visitante", origin_company: sel.kind === "visitor_origin" ? sel.name : "", nonce: Date.now() });
    setTab("form");
  };
  const pickSearch = (r) => {
    if (r.kind === "person") {
      const c = companies.find((x) => x.id === r.company_id);
      if (c) setSelection({ kind: "company", id: c.id, company: c });
    }
    open(r.kind, r.id);
  };
  const onSaved = () => setRefreshKey((k) => k + 1);
  const [title, subtitle] = TITLES[mode];
  const tabs = portaria ? [["present", "Presentes"], ["form", "Cadastro"]] : [["companies", "Empresas"], ["people", "Pessoas"], ["form", "Cadastro"]];
  const col = (k) => cn("min-h-0 overflow-hidden rounded-lg border border-border bg-card", tab === k ? "flex flex-col" : "hidden", "lg:flex lg:flex-col");

  return (
    <div data-testid={`registry-page-${mode}`}>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex-1">
          <h1 className="font-heading text-2xl font-bold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        </div>
        <Button variant="outline" className="justify-start text-muted-foreground sm:w-80" onClick={() => setSearchOpen(true)} data-testid="global-search-button">
          <Search className="mr-2 h-4 w-4" />Buscar pessoa, CPF, cartão, placa…<kbd className="ml-auto font-mono text-[10px]">Ctrl+K</kbd>
        </Button>
      </div>
      {portaria && <DocSearch onSearch={(document) => { setActiveId(null); setRequest({ kind: "lookup", document, nonce: Date.now() }); setTab("form"); }} />}
      <MobileTabs tabs={tabs} tab={tab} setTab={setTab} />
      <div className={cn("grid gap-3", portaria ? "lg:h-[calc(100vh-18rem)]" : "lg:h-[calc(100vh-13rem)]", portaria ? "lg:grid-cols-[340px_1fr]" : "lg:grid-cols-[280px_minmax(300px,360px)_1fr]")}>
        {portaria ? (
          <section className={cn(col("present"), "h-[70vh] lg:h-auto")}><PresentVisitors refreshKey={refreshKey} onOpen={open} onChanged={onSaved} /></section>
        ) : (
          <>
            <section className={cn(col("companies"), "h-[70vh] lg:h-auto")}>
              <CompanyColumn companies={companies} visitorData={visitorData} selection={selection}
                onSelect={(s) => { setSelection(s); setTab("people"); }} onNewCompany={() => setCompanyDlg(true)} />
            </section>
            <section className={cn(col("people"), "h-[70vh] lg:h-auto")}>
              <PeopleColumn selection={selection} activeId={activeId} categories={categories} refreshKey={refreshKey} onOpen={open} onNew={newIn} />
            </section>
          </>
        )}
        <section className={cn(col("form"), "h-[80vh] lg:h-auto")}>
          <PersonForm request={request} companies={companies} categories={categories} departments={departments}
            onSaved={onSaved} onCompanyCreated={() => loadCompanies()} />
        </section>
      </div>
      <GlobalSearch open={searchOpen} onOpenChange={setSearchOpen} onPick={pickSearch} />
      <QuickCompanyDialog open={companyDlg} onOpenChange={setCompanyDlg} categories={categories} onCreated={() => loadCompanies()} />
    </div>
  );
}
