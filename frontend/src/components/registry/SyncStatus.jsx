import { CheckCircle2, Loader2, XCircle } from "lucide-react";

export function SyncStatus({ sync }) {
  if (!sync) return null;
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]" data-testid="sync-status">
      <span className="text-muted-foreground">Equipamentos:</span>
      {sync.status === "sending" && <span className="flex items-center gap-1 text-sky-300" data-testid="sync-sending"><Loader2 className="h-3 w-3 animate-spin" />enviando…</span>}
      {sync.status === "done" && sync.devices.length === 0 && <span className="text-muted-foreground">nenhuma controladora ativa</span>}
      {sync.devices.map((d) => (
        <span key={d.controller_id} title={d.error || "ok"} data-testid={`sync-device-${d.controller_id}`}
          className={`flex items-center gap-1 rounded border px-1.5 py-0.5 ${d.status === "ok" ? "border-emerald-500/30 text-emerald-300" : "border-red-500/40 text-red-300"}`}>
          {d.status === "ok" ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}{d.name}: {d.status === "ok" ? "ok" : "erro"}
        </span>
      ))}
    </div>
  );
}
