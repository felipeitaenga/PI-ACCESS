import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, ResultBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";

export default function Reports() {
  const [access, setAccess] = useState([]);
  const [occupancy, setOccupancy] = useState([]);
  const [presence, setPresence] = useState([]);

  useEffect(() => {
    api.get("/reports/access").then(({ data }) => setAccess(data.items.slice(0, 100)));
    api.get("/reports/occupancy").then(({ data }) => setOccupancy(data.areas));
    api.get("/reports/presence").then(({ data }) => setPresence(data.items));
  }, []);

  return (
    <div>
      <PageHeader title="Relatórios" subtitle="Acessos, ocupação e presença · exportáveis" />
      <Tabs defaultValue="access">
        <TabsList>
          <TabsTrigger value="access" data-testid="report-tab-access">Acessos</TabsTrigger>
          <TabsTrigger value="occupancy" data-testid="report-tab-occupancy">Ocupação atual</TabsTrigger>
          <TabsTrigger value="presence" data-testid="report-tab-presence">Presença (hoje)</TabsTrigger>
        </TabsList>

        <TabsContent value="access">
          <Card className="border-border bg-card">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Data/Hora</TableHead><TableHead>Pessoa</TableHead>
                <TableHead>Porta</TableHead><TableHead>Sentido</TableHead>
                <TableHead>Resultado</TableHead><TableHead>Motivo</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {access.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="font-mono text-xs">{new Date(e.timestamp).toLocaleString("pt-BR")}</TableCell>
                    <TableCell>{e.person_name}</TableCell>
                    <TableCell>{e.door_name}</TableCell>
                    <TableCell className="capitalize">{e.direction}</TableCell>
                    <TableCell><ResultBadge result={e.access_result} /></TableCell>
                    <TableCell className="text-muted-foreground text-sm">{e.reason || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="occupancy">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {occupancy.map((a) => {
              const pct = a.max_occupancy ? Math.min(100, (a.current / a.max_occupancy) * 100) : 0;
              return (
                <Card key={a.area_id} className="border-border bg-card p-5">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{a.area_name}</span>
                    <span className="font-mono text-xl font-bold text-sky-400">{a.current}{a.max_occupancy ? `/${a.max_occupancy}` : ""}</span>
                  </div>
                  {a.max_occupancy > 0 && <Progress value={pct} className="mt-3" />}
                </Card>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="presence">
          <Card className="border-border bg-card">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Pessoa</TableHead><TableHead>Primeiro acesso</TableHead><TableHead>Último acesso</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {presence.map((p) => (
                  <TableRow key={p.person_id}>
                    <TableCell>{p.name}</TableCell>
                    <TableCell className="font-mono text-sm">{new Date(p.first).toLocaleTimeString("pt-BR")}</TableCell>
                    <TableCell className="font-mono text-sm">{new Date(p.last).toLocaleTimeString("pt-BR")}</TableCell>
                  </TableRow>
                ))}
                {presence.length === 0 && <TableRow><TableCell colSpan={3} className="py-8 text-center text-muted-foreground">Nenhum acesso registrado hoje.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
