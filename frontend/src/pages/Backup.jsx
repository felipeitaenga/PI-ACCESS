import { useCallback, useEffect, useRef, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { fmtDateTime } from "@/lib/br";
import { DatabaseBackup, Download, Loader2, RotateCcw, Save, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

const ORIGIN = { manual: "Manual", auto: "Automático", seguranca: "Segurança (antes de restaurar)", enviado: "Enviado" };
const fmtSize = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const CHUNK = 2 * 1024 * 1024;

function Schedule({ s, onSaved }) {
  const [f, setF] = useState(s);
  useEffect(() => setF(s), [s]);
  const save = async () => {
    try { await api.put("/backups/settings", f); toast.success("Agendamento salvo"); onSaved(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  return (
    <Card className="border-border bg-card p-4" data-testid="backup-schedule">
      <h2 className="mb-3 font-heading text-sm font-bold uppercase tracking-widest">Backup automático</h2>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex items-center gap-2 text-sm"><Switch checked={!!f.enabled} onCheckedChange={(v) => setF({ ...f, enabled: v })} data-testid="backup-auto-enabled" />Diário</label>
        <div><p className="mb-1 text-xs font-semibold">Horário</p><Input type="time" className="w-32" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} data-testid="backup-auto-time" /></div>
        <div><p className="mb-1 text-xs font-semibold">Manter últimas cópias</p><Input type="number" min="1" max="90" className="w-28" value={f.keep} onChange={(e) => setF({ ...f, keep: +e.target.value })} data-testid="backup-auto-keep" /></div>
        <Button variant="outline" onClick={save} data-testid="backup-schedule-save"><Save className="mr-2 h-4 w-4" />Salvar</Button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Os arquivos ficam no volume de dados do cliente (/app/data/backups). Baixe cópias e guarde fora do servidor.</p>
    </Card>
  );
}

function RestoreDialog({ name, onClose, onDone }) {
  const [txt, setTxt] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setTxt(""), [name]);
  const go = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/backups/${name}/restore`, { confirm: txt });
      toast.success(`Backup restaurado. Backup de segurança: ${data.safety_backup}`);
      onDone();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!name} onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent data-testid="backup-restore-dialog">
        <DialogHeader><DialogTitle>Restaurar backup</DialogTitle></DialogHeader>
        <p className="text-sm">Todos os dados atuais serão substituídos pelos de <span className="font-mono text-sky-400">{name}</span>, inclusive usuários e senhas. Antes disso o sistema gera automaticamente um backup de segurança.</p>
        <p className="text-xs text-muted-foreground">Digite <b>RESTAURAR</b> para confirmar.</p>
        <Input value={txt} onChange={(e) => setTxt(e.target.value)} data-testid="backup-restore-confirm-input" />
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancelar</Button>
          <Button className="bg-red-600 text-white hover:bg-red-500" disabled={busy || txt !== "RESTAURAR"} onClick={go} data-testid="backup-restore-confirm">
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}Restaurar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Backup() {
  const [data, setData] = useState({ items: [], settings: { enabled: true, time: "03:00", keep: 7 } });
  const [busy, setBusy] = useState("");
  const [restore, setRestore] = useState(null);
  const fileRef = useRef(null);
  const load = useCallback(() => api.get("/backups").then(({ data }) => setData(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setBusy("create");
    try { const { data: b } = await api.post("/backups"); toast.success(`Backup gerado (${b.documents} registros)`); load(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(""); }
  };
  const download = async (name) => {
    try {
      const r = await api.get(`/backups/${name}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = Object.assign(document.createElement("a"), { href: url, download: name });
      a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Falha ao baixar"); }
  };
  const remove = async (name) => {
    if (!window.confirm(`Excluir ${name}?`)) return;
    await api.delete(`/backups/${name}`); toast.success("Backup excluído"); load();
  };
  const upload = async (file) => {
    if (!file) return;
    setBusy("upload");
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    try {
      let res;
      for (let off = 0; off < file.size || off === 0; off += CHUNK) {
        const part = file.slice(off, off + CHUNK);
        const done = off + CHUNK >= file.size ? 1 : 0;
        res = await api.put(`/backups/upload?upload_id=${id}&offset=${off}&done=${done}`, part, { headers: { "Content-Type": "application/octet-stream" } });
        if (done) break;
      }
      toast.success("Arquivo enviado e validado"); await load(); setRestore(res.data.name);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); } finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  };

  return (
    <div className="space-y-4" data-testid="page-backup">
      <PageHeader title="Backup" subtitle="Cópias do banco de dados do cliente (inclui fotos), agendamento e restauração" />
      <div className="flex flex-wrap gap-2">
        <Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" disabled={!!busy} onClick={create} data-testid="backup-create-button">
          {busy === "create" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <DatabaseBackup className="mr-2 h-4 w-4" />}Gerar backup agora
        </Button>
        <Button variant="outline" disabled={!!busy} onClick={() => fileRef.current?.click()} data-testid="backup-upload-button">
          {busy === "upload" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}Enviar arquivo para restaurar
        </Button>
        <input ref={fileRef} type="file" accept=".gz" className="hidden" onChange={(e) => upload(e.target.files[0])} data-testid="backup-upload-input" />
      </div>
      <Schedule s={data.settings} onSaved={load} />
      <Card className="border-border bg-card p-0" data-testid="backup-list">
        {data.items.length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">Nenhum backup ainda</p>}
        {data.items.map((b) => (
          <div key={b.name} className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 last:border-0" data-testid={`backup-row-${b.name}`}>
            <div className="min-w-0 flex-1">
              <p className="truncate font-mono text-sm">{b.name}</p>
              <p className="text-xs text-muted-foreground">{fmtDateTime(b.created_at)} · {fmtSize(b.size)} · {ORIGIN[b.origin] || b.origin}{b.documents != null ? ` · ${b.documents} registros` : ""}{b.by ? ` · ${b.by}` : ""}</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => download(b.name)} data-testid={`backup-download-${b.name}`}><Download className="mr-1 h-4 w-4" />Baixar</Button>
            <Button size="sm" variant="outline" className="text-amber-300" onClick={() => setRestore(b.name)} data-testid={`backup-restore-${b.name}`}><RotateCcw className="mr-1 h-4 w-4" />Restaurar</Button>
            <Button size="icon" variant="ghost" className="text-red-400" onClick={() => remove(b.name)} data-testid={`backup-delete-${b.name}`}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
      </Card>
      <RestoreDialog name={restore} onClose={() => setRestore(null)} onDone={() => { setRestore(null); load(); }} />
    </div>
  );
}
