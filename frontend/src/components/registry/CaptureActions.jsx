import { useUseCapture } from "@/components/registry/useRegistryData";
import { cn } from "@/lib/utils";
import { UserPlus } from "lucide-react";

const TARGETS = [["visitantes", "Visitante"], ["fixos", "Fixo"]];

export function CaptureActions({ photo, className, testPrefix = "capture" }) {
  const sendCapture = useUseCapture();
  if (!photo) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)} onClick={(e) => e.stopPropagation()}>
      <UserPlus className="h-3 w-3 text-muted-foreground" />
      {TARGETS.map(([t, l]) => (
        <button key={t} type="button" onClick={() => sendCapture(t, photo)} data-testid={`${testPrefix}-to-${t}`}
          className="rounded border border-sky-500/40 px-1.5 py-0.5 text-[10px] text-sky-300 transition-colors hover:bg-sky-500/15">
          Cadastrar {l.toLowerCase()}
        </button>
      ))}
    </div>
  );
}
