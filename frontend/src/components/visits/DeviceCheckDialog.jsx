import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2 } from "lucide-react";

const Row = ({ label, children, testId }) => (
  <div className="flex justify-between gap-3 text-xs" data-testid={testId}>
    <span className="text-muted-foreground">{label}</span><span className="text-right font-mono">{children}</span>
  </div>
);

function ControllerResult({ c }) {
  const dp = c.device_person || {};
  const sim = c.similarity_registered_vs_capture;
  const lib = c.library_match;
  return (
    <div className="space-y-1.5 rounded-md border border-border p-3" data-testid={`device-check-ctrl-${c.controller_id}`}>
      <p className="text-sm font-medium">{c.name}</p>
      {c.error ? <p className="text-xs text-red-400" data-testid="device-check-error">{c.error}</p> : <>
        <Row label="Está no facial" testId="device-check-on-device">{c.on_device ? "Sim" : `Não ${c.search_detail || ""}`}</Row>
        {c.on_device && <Row label="Validade gravada">{dp.tempCardType ?? "—"} · {dp.cardValidBegin || "—"} → {dp.cardValidEnd || "—"}</Row>}
        <Row label="Validade esperada">{c.expected?.begin} → {c.expected?.end}</Row>
        <Row label="Hora acertada">{c.time_synced_at ? `${c.time_sync_ok ? "ok" : "falhou"} · ${new Date(c.time_synced_at).toLocaleString("pt-BR")}` : "nunca"}</Row>
        {!c.stranger_at && <p className="text-xs text-muted-foreground">Nenhum "Desconhecido" neste facial nas últimas 3 h.</p>}
        {c.stranger_at && <>
          <Row label="Último desconhecido">{new Date(c.stranger_at).toLocaleString("pt-BR")}</Row>
          <Row label="Foto cadastrada × captura" testId="device-check-similarity">{sim ? (sim.ok ? `${sim.similarity}%` : `erro ${sim.code} ${sim.detail}`) : "—"}</Row>
          <Row label="Busca na base do facial" testId="device-check-library">{lib ? (lib.ok ? JSON.stringify(lib.info) : `sem correspondência (${lib.code} ${lib.detail})`) : "—"}</Row>
        </>}
      </>}
    </div>
  );
}

export function DeviceCheckDialog({ visit, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!visit) { return; }
    setData(null); setError("");
    api.post(`/visits/${visit.id}/device-check`).then(({ data: d }) => setData(d))
      .catch((e) => setError(formatApiErrorDetail(e.response?.data?.detail)));
  }, [visit]);
  return (
    <Dialog open={!!visit} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg" data-testid="device-check-dialog">
        <DialogHeader><DialogTitle>Verificar no facial · {visit?.visitor_name}</DialogTitle></DialogHeader>
        {!data && !error && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Consultando os faciais…</p>}
        {error && <p className="text-sm text-red-400" data-testid="device-check-fail">{error}</p>}
        {data && <div className="max-h-[60vh] space-y-2 overflow-y-auto">
          {!data.has_photo && <p className="text-xs text-amber-400">Visitante sem foto cadastrada.</p>}
          {data.controllers.length === 0 && <p className="text-sm text-muted-foreground" data-testid="device-check-none">Nenhum facial Beward MQTT ativo.</p>}
          {data.controllers.map((c) => <ControllerResult key={c.controller_id} c={c} />)}
        </div>}
      </DialogContent>
    </Dialog>
  );
}
