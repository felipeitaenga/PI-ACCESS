import { useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ShieldX } from "lucide-react";
import { toast } from "sonner";

export function LgpdEraseButton({ kind, id, name, onDone }) {
  const [open, setOpen] = useState(false);
  const [just, setJust] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = just.trim().length >= 10 && confirm.trim().toUpperCase() === "EXCLUIR";
  const run = async () => {
    setBusy(true);
    try {
      await api.post("/lgpd/erase", { kind, id, justification: just });
      toast.success("Cadastro excluído definitivamente e histórico anonimizado");
      setOpen(false); onDone?.();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <>
      <Button type="button" size="sm" variant="ghost" className="text-red-400 hover:text-red-300" onClick={() => { setJust(""); setConfirm(""); setOpen(true); }} data-testid="lgpd-erase-button">
        <ShieldX className="mr-1 h-4 w-4" />Excluir definitivamente (LGPD)
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="lgpd-erase-dialog">
          <DialogHeader>
            <DialogTitle>Excluir definitivamente · {name}</DialogTitle>
            <DialogDescription>
              Apaga o cadastro, a foto, a face, os cartões e as placas, remove dos faciais e deixa o histórico de acessos e visitas anônimo
              ("Pessoa removida"). Não pode ser desfeito.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Textarea value={just} onChange={(e) => setJust(e.target.value)} placeholder="Justificativa (ex.: pedido do titular em 14/10/2026, protocolo 123)" data-testid="lgpd-erase-justification" />
            <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder='Digite EXCLUIR para confirmar' data-testid="lgpd-erase-confirm" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button disabled={!ok || busy} onClick={run} className="bg-red-600 text-white hover:bg-red-500" data-testid="lgpd-erase-submit">Excluir definitivamente</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
