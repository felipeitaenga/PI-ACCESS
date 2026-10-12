import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, ResultBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";

export function Occupancy() {
  const { hasRole } = useAuth();
  const [areas, setAreas] = useState([]);
  const load = async () => { const { data } = await api.get("/reports/occupancy"); setAreas(data.areas); };
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);
  const reset = async (id) => { await api.post(`/access/areas/${id}/occupancy`, { value: 0 }); toast.success("Lotação zerada"); load(); };
  return (
    <div>
      <PageHeader title="Ocupação por área" subtitle="Lotação atual calculada pelos eventos" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {areas.map((a) => {
          const pct = a.max_occupancy ? Math.min(100, (a.current / a.max_occupancy) * 100) : 0;
          return (
            <Card key={a.area_id} className="border-border bg-card p-5" data-testid={`occupancy-${a.area_id}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium">{a.area_name}</span>
                <span className="font-mono text-2xl font-bold text-sky-400">{a.current}{a.max_occupancy ? `/${a.max_occupancy}` : ""}</span>
              </div>
              {a.max_occupancy > 0 && <Progress value={pct} className="mt-3" />}
              {hasRole("admin", "operator") && <Button variant="outline" size="sm" className="mt-3" onClick={() => reset(a.area_id)} data-testid={`occupancy-reset-${a.area_id}`}><RotateCcw className="mr-1 h-3.5 w-3.5" /> Zerar</Button>}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

export function LogsAccess() {
  const [data, setData] = useState({ items: [], total: 0 });
  const [page, setPage] = useState(1);
  useEffect(() => { api.get(`/events?page=${page}&limit=30`).then(({ data }) => setData(data)); }, [page]);
  return (
    <div>
      <PageHeader title="Logs · Acessos" subtitle={`${data.total} eventos registrados`} />
      <Card className="border-border bg-card">
        <Table>
          <TableHeader><TableRow><TableHead>Data/Hora</TableHead><TableHead>Pessoa</TableHead><TableHead>Ponto</TableHead><TableHead>Fluxo</TableHead><TableHead>Resultado</TableHead><TableHead>Motivo</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.items.map((e) => (
              <TableRow key={e.id}>
                <TableCell className="font-mono text-xs">{new Date(e.timestamp).toLocaleString("pt-BR")}</TableCell>
                <TableCell>{e.person_name}</TableCell>
                <TableCell>{e.door_name}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{e.origin_area_name || "—"} → {e.area_name}</TableCell>
                <TableCell><ResultBadge result={e.access_result} /></TableCell>
                <TableCell className="text-sm text-muted-foreground">{e.reason || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="flex items-center justify-between border-t border-border p-4 text-sm">
          <span className="text-muted-foreground">Página {page}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
            <Button variant="outline" size="sm" disabled={page * 30 >= data.total} onClick={() => setPage(page + 1)}>Próxima</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function LogsSync() {
  const [jobs, setJobs] = useState([]);
  useEffect(() => { api.get("/equipment/sync-jobs").then(({ data }) => setJobs(data)); }, []);
  return (
    <div>
      <PageHeader title="Logs · Sincronização" subtitle="Histórico de sincronização com equipamentos" />
      <Card className="border-border bg-card">
        <Table>
          <TableHeader><TableRow><TableHead>Início</TableHead><TableHead>Controladora</TableHead><TableHead>Resumo</TableHead><TableHead>Erros</TableHead></TableRow></TableHeader>
          <TableBody>
            {jobs.map((j) => (
              <TableRow key={j.id}>
                <TableCell className="font-mono text-xs">{new Date(j.started_at).toLocaleString("pt-BR")}</TableCell>
                <TableCell>{j.device_name}</TableCell>
                <TableCell className="font-mono text-xs">TZ:{j.totals?.time_zones} Áreas:{j.totals?.areas} Pontos:{j.totals?.portals} Regras:{j.totals?.access_rules} Pessoas:{j.success}/{j.total}</TableCell>
                <TableCell className="text-xs">{(j.errors || []).length === 0 ? "0" : (j.errors || []).slice(0, 3).map((e, i) => <div key={i} className="text-red-400">{e.name || e.person_id}: {e.error || e.name || "falha"}</div>)}</TableCell>
              </TableRow>
            ))}
            {jobs.length === 0 && <TableRow><TableCell colSpan={4} className="py-8 text-center text-muted-foreground">Nenhuma sincronização ainda.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
