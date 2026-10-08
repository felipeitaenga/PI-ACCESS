import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useRealtime } from "@/context/RealtimeContext";
import { PageHeader, PriorityBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Bell, AlertTriangle, Check } from "lucide-react";
import { toast } from "sonner";

const TYPE_LABEL = {
  porta_forcada: "Porta forçada",
  porta_aberta: "Porta mantida aberta",
  dispositivo_offline: "Dispositivo offline",
  tentativas_negadas: "Tentativas negadas repetidas",
  coacao: "Coação",
};

export default function Alarms() {
  const { hasRole } = useAuth();
  const { alarms: liveAlarms } = useRealtime();
  const [alarms, setAlarms] = useState([]);
  const [tab, setTab] = useState("open");
  const [ackTarget, setAckTarget] = useState(null);
  const [comment, setComment] = useState("");

  const load = async () => {
    const ackParam = tab === "open" ? "false" : tab === "ack" ? "true" : "";
    const { data } = await api.get(`/alarms${ackParam ? `?acknowledged=${ackParam}` : ""}`);
    setAlarms(data);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tab, liveAlarms.length]);

  const canAck = hasRole("admin", "operator");

  const ack = async () => {
    await api.post(`/alarms/${ackTarget.id}/ack`, { comment });
    toast.success("Alarme reconhecido");
    setAckTarget(null); setComment(""); load();
  };

  return (
    <div>
      <PageHeader title="Alarmes" subtitle="Eventos críticos com prioridade e reconhecimento">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="open" data-testid="alarms-tab-open">Abertos</TabsTrigger>
            <TabsTrigger value="ack" data-testid="alarms-tab-ack">Reconhecidos</TabsTrigger>
            <TabsTrigger value="all" data-testid="alarms-tab-all">Todos</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>

      <div className="space-y-3">
        {alarms.map((a) => (
          <Card key={a.id} className="border-border bg-card p-4" data-testid={`alarm-${a.id}`}>
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-400">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{TYPE_LABEL[a.type] || a.type}</span>
                  <PriorityBadge priority={a.priority} />
                  {a.acknowledged && <span className="inline-flex items-center gap-1 text-xs text-emerald-400"><Check className="h-3 w-3" /> {a.ack_by}</span>}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">{a.door_name} · {a.site_name}</div>
                <div className="mt-1 text-xs font-mono text-muted-foreground">{new Date(a.timestamp).toLocaleString("pt-BR")}</div>
                {a.comment && <div className="mt-2 rounded-md border border-border/50 bg-secondary/40 px-3 py-2 text-sm">{a.comment}</div>}
              </div>
              {canAck && !a.acknowledged && (
                <Button variant="outline" size="sm" onClick={() => setAckTarget(a)} data-testid={`alarm-ack-${a.id}`}>Reconhecer</Button>
              )}
            </div>
          </Card>
        ))}
        {alarms.length === 0 && (
          <Card className="border-border bg-card p-12 text-center">
            <Bell className="mx-auto h-10 w-10 text-muted-foreground/40" />
            <p className="mt-3 text-sm text-muted-foreground">Nenhum alarme nesta categoria.</p>
          </Card>
        )}
      </div>

      <Dialog open={!!ackTarget} onOpenChange={(o) => !o && setAckTarget(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reconhecer alarme</DialogTitle></DialogHeader>
          <Textarea placeholder="Comentário do operador (opcional)" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="alarm-ack-comment" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setAckTarget(null)}>Cancelar</Button>
            <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={ack} data-testid="alarm-ack-confirm">Confirmar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
