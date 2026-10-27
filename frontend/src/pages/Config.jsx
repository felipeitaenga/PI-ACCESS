import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { MENU } from "@/config/menu";
import { PageHeader, ResultBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle2, XCircle, FlaskConical, Play } from "lucide-react";
import { cn } from "@/lib/utils";

export function ConfigHub() {
  const group = MENU.find((e) => e.label === "Configurações");
  return (
    <div>
      <PageHeader title="Configurações" subtitle="Central de administração do sistema" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {group?.items.map((it) => (
          <Link key={it.to} to={it.to} data-testid={`config-card-${it.testid}`}>
            <Card className="border-border bg-card p-5 h-full transition-colors hover:border-sky-500/40">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><it.icon className="h-5 w-5" /></div>
                <div className="font-semibold">{it.label}</div>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function Simulator() {
  const [people, setPeople] = useState([]);
  const [aps, setAps] = useState([]);
  const [personId, setPersonId] = useState("");
  const [apId, setApId] = useState("");
  const [dt, setDt] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.get("/people?limit=500").then(({ data }) => setPeople(data.items));
    api.get("/equipment/access-points/all").then(({ data }) => setAps(data));
  }, []);

  const run = async () => {
    try {
      const { data } = await api.post("/access/simulate", { person_id: personId, access_point_id: apId, datetime: dt || undefined });
      setResult(data);
    } catch (e) { setResult(null); }
  };

  return (
    <div>
      <PageHeader title="Simulador de acesso" subtitle="Testa o motor de decisão passo a passo" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="border-border bg-card p-6 space-y-4">
          <div><label className="mb-1.5 block text-xs text-muted-foreground">Pessoa</label>
            <Select value={personId} onValueChange={setPersonId}>
              <SelectTrigger data-testid="sim-person"><SelectValue placeholder="Selecione a pessoa" /></SelectTrigger>
              <SelectContent>{people.map((p) => <SelectItem key={p.id} value={p.id}>{p.name} · {p.status}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><label className="mb-1.5 block text-xs text-muted-foreground">Ponto de acesso</label>
            <Select value={apId} onValueChange={setApId}>
              <SelectTrigger data-testid="sim-ap"><SelectValue placeholder="Selecione o ponto" /></SelectTrigger>
              <SelectContent>{aps.map((a) => <SelectItem key={a.id} value={a.id}>{a.description} ({a.origin_area_name} → {a.dest_area_name})</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><label className="mb-1.5 block text-xs text-muted-foreground">Data/hora (vazio = agora)</label>
            <Input type="datetime-local" value={dt} onChange={(e) => setDt(e.target.value)} data-testid="sim-datetime" />
          </div>
          <Button className="w-full bg-sky-500 hover:bg-sky-600 text-white" onClick={run} disabled={!personId || !apId} data-testid="sim-run">
            <Play className="mr-2 h-4 w-4" /> Simular acesso
          </Button>
        </Card>

        <Card className="border-border bg-card p-6">
          {result ? (
            <div data-testid="sim-result">
              <div className={cn("mb-4 flex items-center gap-3 rounded-lg p-4", result.granted ? "bg-emerald-500/10" : "bg-red-500/10")}>
                {result.granted ? <CheckCircle2 className="h-8 w-8 text-emerald-400" /> : <XCircle className="h-8 w-8 text-red-400" />}
                <div>
                  <div className={cn("text-lg font-bold", result.granted ? "text-emerald-400" : "text-red-400")}>{result.granted ? "ACESSO LIBERADO" : "ACESSO NEGADO"}</div>
                  <div className="text-sm text-muted-foreground">{result.reason}{result.category_code ? ` · ${result.category_code}` : ""}{result.escort_required ? " · requer escort" : ""}</div>
                </div>
              </div>
              <div className="text-xs font-mono uppercase tracking-wide text-muted-foreground mb-2">Passo a passo da decisão</div>
              <ol className="space-y-1">
                {result.steps.map((s, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm">
                    {s.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" /> : <XCircle className="h-4 w-4 text-red-400 shrink-0" />}
                    <span className={cn(!s.ok && "text-red-400")}>{s.msg}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <FlaskConical className="h-10 w-10 text-sky-400/50" />
              <p className="mt-3 text-sm">Escolha pessoa e ponto de acesso e clique em Simular.</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
