import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useRealtime } from "@/context/RealtimeContext";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, ResultBadge, PassageTag } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ManualReleaseDialog, ManualTag, canReleaseEvent } from "@/components/access/ManualReleaseDialog";
import { useOpenRecord } from "@/components/registry/useRegistryData";
import { CaptureActions } from "@/components/registry/CaptureActions";
import { DoorOpen, Pencil, Radio } from "lucide-react";
import { cn } from "@/lib/utils";

function scoreColor(s) {
  if (s >= 90) return "text-emerald-400";
  if (s >= 60) return "text-amber-400";
  return "text-red-400";
}

export default function LiveMonitoring() {
  const { events: live, patch } = useRealtime();
  const { hasRole } = useAuth();
  const [seed, setSeed] = useState([]);
  const [selected, setSelected] = useState(null);
  const [doors, setDoors] = useState([]);
  const [filterResult, setFilterResult] = useState("all");
  const [releasePoint, setReleasePoint] = useState(null);
  const [releaseEv, setReleaseEv] = useState(null);
  const openRecord = useOpenRecord();
  // evento novo vai direto para a Inspeção facial
  const newest = live[0]?.id;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (newest) setSelected(live[0]); }, [newest]);

  useEffect(() => {
    api.get("/events?limit=30").then(({ data }) => setSeed(data.items));
    api.get("/equipment/access-points/all").then(({ data }) => setDoors(data));
  }, []);

  const all = [...live, ...seed]
    .filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i)
    .map(patch)
    .filter((e) => filterResult === "all" || e.access_result === filterResult)
    .slice(0, 60);
  // inspeção acompanha atualizações em tempo real (ex.: foto capturada que chega depois)
  const cur = selected ? (all.find((e) => e.id === selected.id) || patch(selected)) : null;

  const canOperate = hasRole("admin", "operator", "reception");

  return (
    <div>
      <PageHeader title="Monitoramento ao vivo" subtitle="Feed de eventos em tempo real via WebSocket">
        {canOperate && (
          <Select value="" onValueChange={(id) => setReleasePoint(doors.find((d) => d.id === id))}>
            <SelectTrigger className="w-[220px]" data-testid="remote-door-unlock-button">
              <DoorOpen className="mr-2 h-4 w-4" /> <SelectValue placeholder="Liberação manual" />
            </SelectTrigger>
            <SelectContent>
              {doors.map((d) => (
                <SelectItem key={d.id} value={d.id} data-testid={`unlock-door-${d.id}`}>{d.description}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Card className="border-border bg-card lg:col-span-8">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <div className="flex items-center gap-2">
              <Radio className="h-4 w-4 text-sky-400" />
              <span className="text-sm font-semibold uppercase tracking-wider">Feed de eventos</span>
            </div>
            <Select value={filterResult} onValueChange={setFilterResult}>
              <SelectTrigger className="w-[150px]" data-testid="event-result-filter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="granted">Liberados</SelectItem>
                <SelectItem value="denied">Negados</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="max-h-[70vh] overflow-y-auto scrollbar-thin" data-testid="live-event-feed-table">
            {all.map((e, idx) => (
              <button
                key={e.id}
                onClick={() => setSelected(e)}
                data-testid={`event-row-${idx}`}
                className={cn(
                  "flex w-full items-center gap-3 border-b border-border/50 px-5 py-3 text-left transition-colors hover:bg-secondary/50",
                  idx === 0 && live.length > 0 && "animate-row-in"
                )}
              >
                {e.captured_photo || e.person_photo ? (
                  <img src={e.captured_photo || e.person_photo} alt="" className="h-9 w-9 rounded-full object-cover" data-testid={`event-row-photo-${idx}`} />
                ) : (
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary text-xs">?</div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{e.person_name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[e.door_name, e.area_name, e.credential_type?.toUpperCase()].filter(Boolean).join(" · ")}
                  </div>
                  {e.access_result === "denied" && e.reason && (
                    <div className="truncate text-xs text-red-400" data-testid={`event-row-reason-${idx}`}>{e.reason}</div>
                  )}
                </div>
                <div className="text-right">
                  <ResultBadge result={e.access_result} />
                  <PassageTag passage={e.passage} />
                  <ManualTag e={e} />
                  {canReleaseEvent(e, hasRole) && (
                    <span role="button" tabIndex={0} onClick={(ev) => { ev.stopPropagation(); setReleaseEv(e); }}
                      className="mt-1 inline-block rounded border border-amber-500/50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 hover:bg-amber-500/10" data-testid={`event-row-release-${idx}`}>Liberar</span>
                  )}
                  <div className="mt-1 text-[10px] font-mono text-muted-foreground">
                    {new Date(e.timestamp).toLocaleTimeString("pt-BR")}
                  </div>
                </div>
              </button>
            ))}
            {all.length === 0 && <div className="p-6 text-sm text-muted-foreground">Nenhum evento.</div>}
          </div>
        </Card>

        {/* Inspector */}
        <Card className="border-border bg-card p-5 lg:col-span-4">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Inspeção facial</h2>
          {cur ? (
            <div data-testid="event-inspector">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 text-xs font-mono uppercase text-muted-foreground">Cadastrada</div>
                  {cur.person_photo ? (
                    <img src={cur.person_photo} alt="" className="aspect-square w-full rounded-lg object-cover" />
                  ) : (
                    <div className="flex aspect-square w-full items-center justify-center rounded-lg bg-secondary p-3 text-center text-xs text-muted-foreground" data-testid="inspector-no-registered">
                      {cur.person_id ? "Sem foto cadastrada" : "Não identificado pelo facial"}
                    </div>
                  )}
                </div>
                <div>
                  <div className="mb-1 text-xs font-mono uppercase text-muted-foreground">Capturada</div>
                  {cur.captured_photo ? (
                    <img src={cur.captured_photo} alt="" className="aspect-square w-full rounded-lg object-cover" />
                  ) : <div className="aspect-square w-full rounded-lg bg-secondary" />}
                </div>
              </div>
              <div className="mt-4 rounded-lg border border-border p-3 text-center">
                <div className="text-xs font-mono uppercase text-muted-foreground">Confiança</div>
                <div className={cn("text-3xl font-extrabold font-mono", scoreColor(cur.match_score))}>
                  {cur.match_score != null && Number(cur.match_score) > 0 ? `${Math.round(Number(cur.match_score) * 10) / 10}%` : "—"}
                </div>
              </div>
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Pessoa" value={cur.person_name} />
                <Row label="Porta" value={cur.door_name} />
                <Row label="Área" value={cur.area_name} />
                <Row label="Sentido" value={cur.direction} />
                <Row label="Credencial" value={cur.credential_type} />
                <Row label="Resultado" value={<ResultBadge result={cur.access_result} />} />
                {cur.reason && <Row label="Motivo" value={cur.reason} plain />}
                {cur.manual && <Row label="Liberado por" value={cur.operator_name} />}
                {cur.released_by_name && <Row label="Liberado manualmente por" value={cur.released_by_name} />}
              </dl>
              {canReleaseEvent(cur, hasRole) && (
                <Button className="mt-4 w-full bg-amber-500 text-black hover:bg-amber-400" onClick={() => setReleaseEv(cur)} data-testid="inspector-release">
                  <DoorOpen className="mr-2 h-4 w-4" />Liberar manualmente
                </Button>
              )}
              {cur.person_id && (
                <Button variant="outline" className="mt-4 w-full" data-testid="inspector-edit-record"
                  onClick={() => openRecord(cur.person_type === "visitante" ? "visitor" : "person", cur.person_id)}>
                  <Pencil className="mr-2 h-4 w-4" />Editar cadastro {cur.person_type === "visitante" ? "do visitante" : "do fixo"}
                </Button>
              )}
              {!cur.person_id && <CaptureActions photo={cur.captured_photo} className="mt-4" testPrefix="inspector-capture" />}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">Selecione um evento no feed para inspecionar.</div>
          )}
        </Card>
      </div>

      <ManualReleaseDialog event={releaseEv} point={releasePoint} onClose={() => { setReleaseEv(null); setReleasePoint(null); }}
        onDone={(ne) => { setSelected(ne); }} />
    </div>
  );
}

function Row({ label, value, plain = false }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("font-medium text-right", !plain && "capitalize")}>{value}</dd>
    </div>
  );
}
