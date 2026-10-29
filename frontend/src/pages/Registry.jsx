import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { CompanyColumn } from "@/components/registry/CompanyColumn";
import { PeopleColumn } from "@/components/registry/PeopleColumn";
import { PersonForm } from "@/components/registry/PersonForm";
import { GlobalSearch } from "@/components/registry/GlobalSearch";
import { PresentVisitors } from "@/components/registry/PresentVisitors";
import { LiveAccessFeed } from "@/components/registry/LiveAccessFeed";
import { QuickCompanyDialog } from "@/components/registry/QuickCompanyDialog";
import { VisitForm } from "@/components/visits/VisitForm";
import { PresentNow } from "@/components/visits/PresentNow";
import { useOpenRecord, useRegistryData, useSearchHotkey, useUrlRequest } from "@/components/registry/useRegistryData";
import { Search } from "lucide-react";

function PageTop({ title, subtitle, onSearch }) {
  return (
    <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="flex-1">
        <h1 className="font-heading text-2xl font-bold tracking-tight" data-testid="page-title">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </div>
      <Button variant="outline" className="justify-start text-muted-foreground sm:w-80" onClick={onSearch} data-testid="global-search-button">
        <Search className="mr-2 h-4 w-4" />Buscar pessoa, CPF, cartão, placa…<kbd className="ml-auto font-mono text-[10px]">Ctrl+K</kbd>
      </Button>
    </div>
  );
}

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

const panel = (tab, k, extra = "") => cn("min-h-0 overflow-hidden rounded-lg border border-border bg-card lg:flex lg:flex-col", tab === k ? "flex flex-col" : "hidden", extra);

function useSearch() {
  const [open, setOpen] = useState(false);
  useSearchHotkey(setOpen);
  const openRecord = useOpenRecord();
  const node = <GlobalSearch open={open} onOpenChange={setOpen} onPick={(r) => openRecord(r.kind, r.id)} />;
  return [() => setOpen(true), node];
}

export function FixedBrowse() {
  const d = useRegistryData();
  const nav = useNavigate();
  const [sel, setSel] = useState(null);
  const [tab, setTab] = useState("companies");
  const [companyDlg, setCompanyDlg] = useState(false);
  const [openSearch, searchNode] = useSearch();
  return (
    <div data-testid="page-fixed-browse">
      <PageTop title="Fixos" subtitle="Funcionários e terceiros por empresa — clique para abrir o cadastro" onSearch={openSearch} />
      <MobileTabs tabs={[["companies", "Empresas"], ["people", "Pessoas"]]} tab={tab} setTab={setTab} />
      <div className="grid gap-3 lg:h-[calc(100vh-13rem)] lg:grid-cols-[300px_1fr]">
        <section className={panel(tab, "companies", "h-[70vh] lg:h-auto")}>
          <CompanyColumn companies={d.companies} visitorData={d.visitorData} selection={sel} onSelect={(s) => { setSel(s); setTab("people"); }} onNewCompany={() => setCompanyDlg(true)} />
        </section>
        <section className={panel(tab, "people", "h-[75vh] lg:h-auto")}>
          <PeopleColumn wide selection={sel} categories={d.categories} refreshKey={0}
            onOpen={(k, id) => nav(`/cadastro/fixos?person=${id}`)}
            onNew={(s) => nav(`/cadastro/fixos?company=${s.id}&type=${s.company?.type === "propria" ? "funcionario" : "terceiro"}`)} />
        </section>
      </div>
      {searchNode}
      <QuickCompanyDialog open={companyDlg} onOpenChange={setCompanyDlg} categories={d.categories} onCreated={d.reload} />
    </div>
  );
}

export function VisitorsBrowse() {
  const d = useRegistryData();
  const nav = useNavigate();
  const openRecord = useOpenRecord();
  const [sel, setSel] = useState({ kind: "visitors_today", name: "Visitantes do dia" });
  const [tab, setTab] = useState("people");
  const [refreshKey, setRefreshKey] = useState(0);
  const [openSearch, searchNode] = useSearch();
  return (
    <div data-testid="page-visitors-browse">
      <PageTop title="Visitantes" subtitle="Visitantes por empresa visitada — clique para abrir o cadastro" onSearch={openSearch} />
      <MobileTabs tabs={[["companies", "Empresas"], ["people", "Visitantes"], ["present", "Presentes"]]} tab={tab} setTab={setTab} />
      <div className="grid gap-3 lg:h-[calc(100vh-13rem)] lg:grid-cols-[280px_1fr_340px]">
        <section className={panel(tab, "companies", "h-[70vh] lg:h-auto")}>
          <CompanyColumn variant="visitors" companies={d.companies} visitorData={d.visitorData} selection={sel} onSelect={(s) => { setSel(s); setTab("people"); }} />
        </section>
        <section className={panel(tab, "people", "h-[75vh] lg:h-auto")}>
          <PeopleColumn selection={sel} categories={d.categories} refreshKey={refreshKey} onOpen={openRecord}
            onNew={() => nav("/cadastro/visitantes")} />
        </section>
        <section className={panel(tab, "present", "h-[70vh] lg:h-auto")}>
          <PresentVisitors refreshKey={refreshKey} onOpen={openRecord} onChanged={() => { setRefreshKey((k) => k + 1); d.reload(); }} />
        </section>
      </div>
      {searchNode}
    </div>
  );
}

export function FixedRegister() {
  const d = useRegistryData();
  const request = useUrlRequest("funcionario");
  const [openSearch, searchNode] = useSearch();
  return (
    <div data-testid="page-fixed-register">
      <PageTop title="Cadastro de fixos" subtitle="Funcionários e terceiros · Ctrl+S salva" onSearch={openSearch} />
      <Card className="flex h-[85vh] min-h-0 flex-col overflow-hidden border-border bg-card lg:h-[calc(100vh-13rem)]">
        <PersonForm request={request} allowedTypes={["funcionario", "terceiro"]} companies={d.companies} categories={d.categories}
          departments={d.departments} onSaved={d.reload} onCompanyCreated={d.reload} />
      </Card>
      {searchNode}
    </div>
  );
}

export function VisitorRegister() {
  const d = useRegistryData();
  const [tab, setTab] = useState("form");
  const [refreshKey, setRefreshKey] = useState(0);
  const [openSearch, searchNode] = useSearch();
  const saved = () => { setRefreshKey((k) => k + 1); d.reload(); };
  return (
    <div data-testid="page-visitor-register">
      <PageTop title="Cadastro de visitante" subtitle="Portaria · visita com validade, envio ao facial e acessos em tempo real" onSearch={openSearch} />
      <MobileTabs tabs={[["form", "Cadastro"], ["monitor", "Presentes"]]} tab={tab} setTab={setTab} />
      <div className="grid gap-3 lg:h-[calc(100vh-12rem)] lg:grid-cols-[1fr_340px] xl:grid-cols-[1fr_400px]">
        <section className={panel(tab, "form", "h-[85vh] lg:h-auto lg:max-h-full lg:self-start")}>
          <VisitForm companies={d.companies} categories={d.categories} onSaved={saved} />
        </section>
        <section className={cn("min-h-0 gap-3 lg:flex lg:flex-col", tab === "monitor" ? "flex flex-col" : "hidden")} data-testid="visitor-register-monitor">
          <div className="flex h-[45vh] min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card lg:h-auto lg:flex-[2]">
            <PresentNow refreshKey={refreshKey} onChanged={saved} />
          </div>
          <div className="flex h-[45vh] min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card lg:h-auto lg:flex-[3]"><LiveAccessFeed /></div>
        </section>
      </div>
      {searchNode}
    </div>
  );
}
