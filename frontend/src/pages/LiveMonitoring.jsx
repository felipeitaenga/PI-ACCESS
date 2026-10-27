import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useRealtime } from "@/context/RealtimeContext";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, ResultBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useOpenRecord } from "@/components/registry/useRegistryData";
import { CaptureActions } from "@/components/registry/CaptureActions";
import { DoorOpen, Pencil, Radio } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function scoreColor(s) {
  if (s >= 90) return "text-emerald-400";
  if (s >= 60) return "text-amber-400";
  return "text-red-400";
}

export default function LiveMonitoring() {
  const { events: live } = useRealtime();
  const { hasRole } = useAuth();
  const [seed, setSeed] = useState([]);
  const [selected, setSelected] = useState(null);
  const [doors, setDoors] = useState([]);
  const [filterResult, setFilterResult] = useState("all");
  const [unlockDoor, setUnlockDoor] = useState(null);
  const [reason, setReason] = useState("");
  const openRecord = useOpenRecord();

  useEffect(() => {
    api.get("/events?limit=30").then(({ data }) => setSeed(data.items));
    api.get("/equipment/access-points/all").then(({ data }) => setDoors(data));
  }, []);

  const all = [...live, ...seed]
    .filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i)
    .filter((e) => filterResult === "all" || e.access_result === filterResult)
    .slice(0, 60);

  const canOperate = hasRole("admin", "operator", "reception");

  const doUnlock = async () => {
    try {
      await api.post(`/equipment/access-points/${unlockDoor}/open`, { seconds: 5, reason });
      toast.success("Porta aberta remotamente");
      setUnlockDoor(null);
      setReason("");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  return (
    <div>
      <PageHeader title="Monitoramento ao vivo" subtitle="Feed de eventos em tempo real via WebSocket">
        {canOperate && (
          <Select onValueChange={setUnlockDoor}>
            <SelectTrigger className="w-[220px]" data-testid="remote-door-unlock-button">
              <DoorOpen className="mr-2 h-4 w-4" /> <SelectValue placeholder="Abrir porta remotamente" />
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
          {selected ? (
            <div data-testid="event-inspector">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 text-xs font-mono uppercase text-muted-foreground">Cadastrada</div>
                  {selected.person_photo ? (
                    <img src={selected.person_photo} alt="" className="aspect-square w-full rounded-lg object-cover" />
                  ) : (
                    <div className="flex aspect-square w-full items-center justify-center rounded-lg bg-secondary p-3 text-center text-xs text-muted-foreground" data-testid="inspector-no-registered">
                      {selected.person_id ? "Sem foto cadastrada" : "Não identificado pelo facial"}
                    </div>
                  )}
                </div>
                <div>
                  <div className="mb-1 text-xs font-mono uppercase text-muted-foreground">Capturada</div>
                  {selected.captured_photo ? (
                    <img src={selected.captured_photo} alt="" className="aspect-square w-full rounded-lg object-cover" />
                  ) : <div className="aspect-square w-full rounded-lg bg-secondary" />}
                </div>
              </div>
              <div className="mt-4 rounded-lg border border-border p-3 text-center">
                <div className="text-xs font-mono uppercase text-muted-foreground">Confiança</div>
                <div className={cn("text-3xl font-extrabold font-mono", scoreColor(selected.match_score))}>
                  {selected.match_score != null && Number(selected.match_score) > 0 ? `${Math.round(Number(selected.match_score) * 10) / 10}%` : "—"}
                </div>
              </div>
              <dl className="mt-4 space-y-2 text-sm">
                <Row label="Pessoa" value={selected.person_name} />
                <Row label="Porta" value={selected.door_name} />
                <Row label="Área" value={selected.area_name} />
                <Row label="Sentido" value={selected.direction} />
                <Row label="Credencial" value={selected.credential_type} />
                <Row label="Resultado" value={<ResultBadge result={selected.access_result} />} />
                {selected.reason && <Row label="Motivo" value={selected.reason} />}
              </dl>
              {selected.person_id && (
                <Button variant="outline" className="mt-4 w-full" data-testid="inspector-edit-record"
                  onClick={() => openRecord(selected.person_type === "visitante" ? "visitor" : "person", selected.person_id)}>
                  <Pencil className="mr-2 h-4 w-4" />Editar cadastro {selected.person_type === "visitante" ? "do visitante" : "do fixo"}
                </Button>
              )}
              {!selected.person_id && <CaptureActions photo={selected.captured_photo} className="mt-4" testPrefix="inspector-capture" />}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">Selecione um evento no feed para inspecionar.</div>
          )}
        </Card>
      </div>

      <Dialog open={!!unlockDoor} onOpenChange={(o) => !o && setUnlockDoor(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirmação de abertura remota</DialogTitle>
            <DialogDescription>
              Esta ação abrirá a porta fisicamente e será registrada em auditoria.
            </DialogDescription>
          </DialogHeader>
          <Textarea placeholder="Motivo da abertura (opcional)" value={reason}
            onChange={(e) => setReason(e.target.value)} data-testid="unlock-reason-input" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setUnlockDoor(null)}>Cancelar</Button>
            <Button className="bg-sky-500 hover:bg-sky-600 text-white" onClick={doUnlock} data-testid="confirm-door-unlock-button">
              Confirmar abertura
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium text-right capitalize">{value}</dd>
    </div>
  );
}
