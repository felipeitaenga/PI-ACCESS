import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Flame, Users, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function Emergency() {
  const { hasRole } = useAuth();
  const [sites, setSites] = useState([]);
  const [siteId, setSiteId] = useState("");
  const [muster, setMuster] = useState(null);

  useEffect(() => {
    api.get("/structure/sites").then(({ data }) => {
      setSites(data);
      if (data[0]) setSiteId(data[0].id);
    });
  }, []);

  const loadMuster = async (id) => {
    if (!id) return;
    const { data } = await api.get(`/emergency/muster/${id}`);
    setMuster(data);
  };
  useEffect(() => { loadMuster(siteId); }, [siteId]);

  const canTrigger = hasRole("admin", "operator");

  const trigger = async (mode) => {
    try {
      const { data } = await api.post(`/emergency/lockdown/${siteId}`, { mode });
      toast[mode === "liberada" ? "success" : "success"](
        mode === "liberada" ? `LIBERAÇÃO GERAL: ${data.doors_affected} portas liberadas` : "Operação normal restaurada"
      );
      loadMuster(siteId);
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const totalInside = muster?.areas.reduce((a, b) => a + b.count, 0) || 0;

  return (
    <div>
      <PageHeader title="Emergência / Incêndio" subtitle="Liberação geral de rota de fuga e lista de evacuação">
        <Select value={siteId} onValueChange={setSiteId}>
          <SelectTrigger className="w-[260px]" data-testid="emergency-site-select"><SelectValue placeholder="Site" /></SelectTrigger>
          <SelectContent>{sites.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
        </Select>
      </PageHeader>

      {canTrigger && (
        <Card className="mb-6 border-red-500/30 bg-red-500/5 p-6">
          <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-red-500/15 text-red-400"><Flame className="h-6 w-6" /></div>
              <div>
                <div className="font-heading text-lg font-bold">Liberação geral de emergência</div>
                <div className="text-sm text-muted-foreground">Coloca todas as portas de rota de fuga em modo liberado. Ação registrada em auditoria.</div>
              </div>
            </div>
            <div className="flex gap-3">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button className="bg-red-600 hover:bg-red-700 text-white font-bold" data-testid="emergency-panic-button">
                    <Flame className="mr-2 h-4 w-4" /> LIBERAÇÃO GERAL
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Confirmar liberação geral?</AlertDialogTitle>
                    <AlertDialogDescription>
                      TODAS as portas do site serão liberadas imediatamente. Use somente em emergência real (incêndio/evacuação).
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancelar</AlertDialogCancel>
                    <AlertDialogAction className="bg-red-600 hover:bg-red-700" onClick={() => trigger("liberada")} data-testid="emergency-confirm-button">Confirmar liberação</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <Button variant="outline" onClick={() => trigger("normal")} data-testid="emergency-restore-button">
                <ShieldCheck className="mr-2 h-4 w-4" /> Restaurar operação
              </Button>
            </div>
          </div>
        </Card>
      )}

      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><Users className="h-5 w-5" /></div>
        <div>
          <div className="font-semibold">Lista de evacuação (Muster Report)</div>
          <div className="text-sm text-muted-foreground">{totalInside} pessoas estimadas dentro do site</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {muster?.areas.map((area) => (
          <Card key={area.area_id} className="border-border bg-card p-4" data-testid={`muster-area-${area.area_id}`}>
            <div className="flex items-center justify-between border-b border-border pb-3">
              <span className="font-medium">{area.area_name}</span>
              <span className="font-mono text-2xl font-bold text-sky-400">{area.count}</span>
            </div>
            <div className="mt-3 max-h-64 space-y-2 overflow-y-auto scrollbar-thin">
              {area.people.map((p) => (
                <div key={p.person_id} className="flex items-center gap-2 text-sm">
                  {p.photo ? <img src={p.photo} alt="" className="h-7 w-7 rounded-full object-cover" /> : <div className="h-7 w-7 rounded-full bg-secondary" />}
                  <span className="truncate">{p.name}</span>
                </div>
              ))}
              {area.people.length === 0 && <div className="text-sm text-muted-foreground">Área vazia.</div>}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
