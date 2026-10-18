import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { PageHeader } from "@/components/common";
import { CategoryMulti } from "@/components/registry/FormBits";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, KeyRound } from "lucide-react";
import { toast } from "sonner";

const ROLE_LABEL = { admin: "Administrador", operator: "Operador", reception: "Recepção", viewer: "Somente leitura", company_manager: "Gestor de empresa" };

const SECTIONS = {
  "/configuracoes/usuarios": ["users", "Usuários", "Contas de acesso ao sistema e perfis"],
  "/logs/auditoria": ["audit", "Auditoria", "Quem fez o quê e quando no sistema"],
  "/configuracoes/geral": ["settings", "Configurações gerais", "Parâmetros gerais do sistema"],
};

export default function Admin() {
  const { pathname } = useLocation();
  const [section, title, subtitle] = SECTIONS[pathname] || SECTIONS["/configuracoes/usuarios"];
  const [users, setUsers] = useState([]);
  const [audit, setAudit] = useState([]);
  const [settings, setSettings] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "operator", company_ids: [] });
  const [companies, setCompanies] = useState([]);
  useEffect(() => { api.get("/org/companies/all").then(({ data }) => setCompanies(data)).catch(() => {}); }, []);
  const [pwdUser, setPwdUser] = useState(null);
  const [newPwd, setNewPwd] = useState("");

  const resetPassword = async () => {
    try {
      await api.put(`/auth/users/${pwdUser.id}`, { password: newPwd });
      toast.success(`Senha de ${pwdUser.name} redefinida`);
      setPwdUser(null); setNewPwd("");
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const load = async () => {
    const [u, a, s] = await Promise.all([
      api.get("/auth/users"), api.get("/admin/audit"), api.get("/admin/settings"),
    ]);
    setUsers(u.data); setAudit(a.data.items); setSettings(s.data);
  };
  useEffect(() => { load(); }, []);

  const createUser = async () => {
    try {
      await api.post("/auth/users", form);
      toast.success("Usuário criado");
      setOpen(false); setForm({ email: "", password: "", name: "", role: "operator", company_ids: [] }); load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const removeUser = async (id) => {
    if (!window.confirm("Excluir usuário?")) return;
    try { await api.delete(`/auth/users/${id}`); toast.success("Excluído"); load(); }
    catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const saveSettings = async () => {
    await api.put("/admin/settings", settings);
    toast.success("Configurações salvas");
  };

  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />
      <Tabs value={section}>

        <TabsContent value="users">
          <div className="mb-4 flex justify-end">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" data-testid="admin-add-user-button"><Plus className="mr-2 h-4 w-4" /> Novo usuário</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Novo usuário</DialogTitle></DialogHeader>
                <div className="space-y-3">
                  <div><Label className="mb-1.5 block text-xs text-muted-foreground">Nome</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" /></div>
                  <div><Label className="mb-1.5 block text-xs text-muted-foreground">E-mail</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" /></div>
                  <div><Label className="mb-1.5 block text-xs text-muted-foreground">Senha</Label><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="user-password-input" /></div>
                  <div><Label className="mb-1.5 block text-xs text-muted-foreground">Perfil</Label>
                    <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                      <SelectTrigger data-testid="user-role-select"><SelectValue /></SelectTrigger>
                      <SelectContent>{Object.entries(ROLE_LABEL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  {form.role === "company_manager" && (
                    <div data-testid="user-companies-field"><Label className="mb-1.5 block text-xs text-muted-foreground">Empresas que pode gerenciar *</Label>
                      <CategoryMulti categories={companies.map((c) => ({ id: c.id, code: c.name }))} value={form.company_ids || []} onChange={(v) => setForm({ ...form, company_ids: v })} />
                    </div>
                  )}
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
                  <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={createUser} data-testid="user-save-button">Criar</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
          <Card className="border-border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Nome</TableHead><TableHead>E-mail</TableHead><TableHead>Perfil</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Ações</TableHead></TableRow></TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                    <TableCell className="font-medium">{u.name}</TableCell>
                    <TableCell className="font-mono text-sm">{u.email}</TableCell>
                    <TableCell><Badge variant="outline" className="bg-sky-500/10 text-sky-400 border-sky-500/30">{u.role_label}</Badge>
                      {u.role === "company_manager" && <p className="mt-1 text-[11px] text-muted-foreground" data-testid={`user-companies-${u.id}`}>{(u.company_ids || []).map((id) => companies.find((c) => c.id === id)?.name || "?").join(", ")}</p>}</TableCell>
                    <TableCell>{u.active ? <span className="text-emerald-400 text-sm">Ativo</span> : <span className="text-slate-500 text-sm">Inativo</span>}</TableCell>
                    <TableCell className="text-right"><Button variant="ghost" size="icon" className="text-sky-400" title="Redefinir senha" onClick={() => { setPwdUser(u); setNewPwd(""); }} data-testid={`user-reset-password-${u.id}`}><KeyRound className="h-4 w-4" /></Button><Button variant="ghost" size="icon" className="text-red-400" onClick={() => removeUser(u.id)} data-testid={`user-delete-${u.id}`}><Trash2 className="h-4 w-4" /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <Dialog open={!!pwdUser} onOpenChange={(o) => !o && setPwdUser(null)}>
            <DialogContent data-testid="reset-password-dialog">
              <DialogHeader><DialogTitle>Redefinir senha — {pwdUser?.name}</DialogTitle></DialogHeader>
              <p className="text-xs text-muted-foreground">{pwdUser?.email} · as sessões abertas deste usuário serão encerradas.</p>
              <div><Label className="mb-1.5 block text-xs text-muted-foreground">Nova senha (mín. 8 caracteres)</Label><Input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} data-testid="reset-password-input" /></div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setPwdUser(null)}>Cancelar</Button>
                <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" disabled={newPwd.length < 8} onClick={resetPassword} data-testid="reset-password-save">Salvar nova senha</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </TabsContent>

        <TabsContent value="audit">          <Card className="border-border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Data/Hora</TableHead><TableHead>Usuário</TableHead><TableHead>Ação</TableHead><TableHead>Entidade</TableHead><TableHead>Detalhes</TableHead><TableHead>IP</TableHead></TableRow></TableHeader>
              <TableBody>
                {audit.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-mono text-xs">{new Date(a.timestamp).toLocaleString("pt-BR")}</TableCell>
                    <TableCell>{a.user_name}</TableCell>
                    <TableCell><Badge variant="outline">{a.action}</Badge></TableCell>
                    <TableCell className="text-muted-foreground">{a.entity_type}</TableCell>
                    <TableCell className="text-sm">{a.details}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{a.ip}</TableCell>
                  </TableRow>
                ))}
                {audit.length === 0 && <TableRow><TableCell colSpan={6} className="py-8 text-center text-muted-foreground">Sem registros.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="settings">
          {settings && (
            <Card className="border-border bg-card p-6 max-w-lg">
              <div className="space-y-4">
                <div><Label className="mb-1.5 block text-xs text-muted-foreground">Retenção de eventos (dias)</Label><Input type="number" value={settings.retention_days} onChange={(e) => setSettings({ ...settings, retention_days: +e.target.value })} data-testid="settings-retention-input" /></div>
                <div><Label className="mb-1.5 block text-xs text-muted-foreground">Retenção de fotos biométricas (dias)</Label><Input type="number" value={settings.photo_retention_days} onChange={(e) => setSettings({ ...settings, photo_retention_days: +e.target.value })} /></div>
                <div><Label className="mb-1.5 block text-xs text-muted-foreground">Fuso horário</Label><Input value={settings.timezone} disabled /></div>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!settings.manager_can_create_managers} onChange={(e) => setSettings({ ...settings, manager_can_create_managers: e.target.checked })} data-testid="settings-manager-create" />Gestor de empresa pode criar outros gestores da mesma empresa</label>
                <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={saveSettings} data-testid="settings-save-button">Salvar configurações</Button>
              </div>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
