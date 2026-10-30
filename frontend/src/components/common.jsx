import { cn } from "@/lib/utils";

export function StatusDot({ online, className }) {
  return (
    <span
      className={cn(
        "status-dot",
        online ? "bg-emerald-500" : "bg-slate-500",
        className
      )}
    />
  );
}

const PASSAGE = {
  pendente: ["aguardando passagem…", "text-sky-300"],
  confirmada: ["passou", "text-emerald-400"],
  nao_passou: ["liberado, não passou", "text-amber-300"],
};
export function PassageTag({ passage }) {
  const p = PASSAGE[passage];
  if (!p) return null;
  return <span className={`block text-[10px] font-medium ${p[1]}`} data-testid="passage-tag">● {p[0]}</span>;
}

export function ResultBadge({ result }) {
  const map = {
    granted: { label: "Liberado", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
    denied: { label: "Negado", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
  };
  const m = map[result] || map.denied;
  return (
    <span className={cn("inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium font-mono", m.cls)}>
      {m.label}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  const map = {
    alta: "bg-red-500/15 text-red-400 border-red-500/30",
    media: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    baixa: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  };
  return (
    <span className={cn("inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium uppercase", map[priority] || map.baixa)}>
      {priority}
    </span>
  );
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight font-heading text-slate-900 dark:text-slate-100">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
