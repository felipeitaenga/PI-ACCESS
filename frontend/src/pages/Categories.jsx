import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Trash2, Pencil, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

const FLAGS = [
  ["control_origin", "Controlar origem de acesso", "Só libera se a pessoa estiver na área de origem do ponto"],
  ["control_anti_double", "Controlar anti-dupla entrada", "Bloqueia entrar 2x na mesma área sem sair"],
  ["require_escort_unconditional", "Exigir escort incondicional", "Exige acompanhante autorizado"],
  ["reentry_timed", "Reentrada temporizada", "Tempo mínimo entre saída e nova entrada"],
  ["impeditive", "Categoria impeditiva", "Nega TODO acesso (lista negra) — prevalece"],
  ["use_contingency", "Usar contingência", "Comportamento offline da controladora"],
  ["always_verify_offline", "Sempre verificar offline", "Controladora decide sem servidor"],
];

export default function Categories() {
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");
  const [list, setList] = useState([]);
  const [areas, setAreas] = useState([]);
  const [trs, setTrs] = useState([]);
  const [editing, setEditing] = useState(null); // category being edited (full page)
  const [people, setPeople] = useState([]);
  const [assocOpen, setAssocOpen] = useState(false);
  const [allPeople, setAllPeople] = useState([]);
  const [pSel, setPSel] = useState(new Set());

  const load = async () => {
    const [c, a, t] = await Promise.all([
      api.get("/access/categories?limit=200"), api.get("/access/areas/all"), api.get("/access/time-ranges/all"),
    ]);
    setList(c.data.items); setAreas(a.data); setTrs(t.data);
  };
  useEffect(() => { load(); }, []);

  const startNew = () => setEditing({ code: "", description: "", enabled: true, access_areas: [],
    control_origin: false, control_anti_double: false, require_escort_unconditional: false,
    reentry_timed: false, reentry_minutes: 0, impeditive: false, use_contingency: true, always_verify_offline: false });
  const startEdit = (c) => { setEditing({ ...c }); loadPeople(c.id); };

  const loadPeople = async (id) => { const { data } = await api.get(`/access/categories/${id}/people`); setPeople(data); };

  const save = async () => {
    try {
      if (editing.id) await api.put(`/access/categories/${editing.id}`, editing);
      else await api.post("/access/categories", editing);
      toast.success("Categoria salva"); setEditing(null); load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  const addArea = () => setEditing({ ...editing, access_areas: [...(editing.access_areas || []), { area_id: "", time_range_id: "", require_escort: false }] });
  const setArea = (i, k, v) => { const n = [...editing.access_areas]; n[i] = { ...n[i], [k]: v }; setEditing({ ...editing, access_areas: n }); };
  const delArea = (i) => setEditing({ ...editing, access_areas: editing.access_areas.filter((_, x) => x !== i) });

  const openAssoc = async () => { const { data } = await api.get("/people?limit=500"); setAllPeople(data.items); setPSel(new Set()); setAssocOpen(true); };
  const doAssoc = async () => {
    await api.post(`/access/categories/${editing.id}/people`, { person_ids: [...pSel], action: "add" });
    toast.success("Pessoas associadas"); setAssocOpen(false); loadPeople(editing.id);
  };
  const removePerson = async (pid) => {
    await api.post(`/access/categories/${editing.id}/people`, { person_ids: [pid], action: "remove" });
    loadPeople(editing.id);
  };

  const areaName = (id) => areas.find((a) => a.id === id)?.description || "—";
  const trName = (id) => trs.find((t) => t.id === id)?.description || "—";

  if (editing) {
    return (
      <div>
        <PageHeader title={editing.id ? `Categoria: ${editing.code}` : "Nova categoria"} subtitle="Perfil de acesso">
          <Button variant="outline" onClick={() => setEditing(null)} data-testid="cat-back"><ArrowLeft className="mr-2 h-4 w-4" /> Voltar</Button>
          <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={save} data-testid="cat-save">Salvar</Button>
        </PageHeader>
        <Tabs defaultValue="general">
          <TabsList>
            <TabsTrigger value="general" data-testid="cat-tab-general">Dados gerais</TabsTrigger>
            <TabsTrigger value="areas" data-testid="cat-tab-areas">Áreas de acesso</TabsTrigger>
            {editing.id && <TabsTrigger value="people" data-testid="cat-tab-people">Pessoas associadas</TabsTrigger>}
          </TabsList>

          <TabsContent value="general">
            <Card className="border-border bg-card p-6 space-y-4 max-w-2xl">
              <div className="grid grid-cols-2 gap-4">
                <div><label className="mb-1.5 block text-xs text-muted-foreground">Nome da categoria</label><Input value={editing.code} onChange={(e) => setEditing({ ...editing, code: e.target.value })} data-testid="cat-code" /></div>
                <div><label className="mb-1.5 block text-xs text-muted-foreground">Descrição</label><Input value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} data-testid="cat-desc" /></div>
              </div>
              <label className="flex items-center gap-2 text-sm"><Checkbox checked={editing.enabled !== false} onCheckedChange={(v) => setEditing({ ...editing, enabled: !!v })} /> Habilitada</label>
              <div className="space-y-3 border-t border-border pt-4">
                {FLAGS.map(([k, label, hint]) => (
                  <div key={k} className="flex items-start gap-3">
                    <Checkbox checked={!!editing[k]} onCheckedChange={(v) => setEditing({ ...editing, [k]: !!v })} data-testid={`cat-${k}`} className="mt-0.5" />
                    <div>
                      <div className="text-sm font-medium">{label}</div>
                      <div className="text-xs text-muted-foreground">{hint}</div>
                    </div>
                    {k === "reentry_timed" && editing.reentry_timed && (
                      <Input type="number" className="ml-auto w-24" placeholder="min" value={editing.reentry_minutes || 0} onChange={(e) => setEditing({ ...editing, reentry_minutes: +e.target.value })} data-testid="cat-reentry-min" />
                    )}
                  </div>
                ))}
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="areas">
            <Card className="border-border bg-card p-5">
              <div className="mb-3 flex justify-end"><Button variant="outline" size="sm" onClick={addArea} data-testid="cat-add-area"><Plus className="mr-1 h-3.5 w-3.5" /> Nova área</Button></div>
              <Table>
                <TableHeader><TableRow><TableHead>Área de destino</TableHead><TableHead>Faixa horária</TableHead><TableHead>Exigir escort</TableHead><TableHead></TableHead></TableRow></TableHeader>
                <TableBody>
                  {(editing.access_areas || []).map((cfg, i) => (
                    <TableRow key={i}>
                      <TableCell>
                        <Select value={cfg.area_id} onValueChange={(v) => setArea(i, "area_id", v)}>
                          <SelectTrigger data-testid={`cat-area-${i}`}><SelectValue placeholder="Área" /></SelectTrigger>
                          <SelectContent>{areas.filter((a) => !a.is_exterior).map((a) => <SelectItem key={a.id} value={a.id}>{a.description}</SelectItem>)}</SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell>
                        <Select value={cfg.time_range_id} onValueChange={(v) => setArea(i, "time_range_id", v)}>
                          <SelectTrigger data-testid={`cat-tr-${i}`}><SelectValue placeholder="Faixa" /></SelectTrigger>
                          <SelectContent>{trs.map((t) => <SelectItem key={t.id} value={t.id}>{t.description}</SelectItem>)}</SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell><Checkbox checked={!!cfg.require_escort} onCheckedChange={(v) => setArea(i, "require_escort", !!v)} /></TableCell>
                      <TableCell><Button variant="ghost" size="icon" className="text-red-400" onClick={() => delArea(i)}><Trash2 className="h-4 w-4" /></Button></TableCell>
                    </TableRow>
                  ))}
                  {(editing.access_areas || []).length === 0 && <TableRow><TableCell colSpan={4} className="py-6 text-center text-muted-foreground">Nenhuma área liberada.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Card>
          </TabsContent>

          <TabsContent value="people">
            <Card className="border-border bg-card p-5">
              <div className="mb-3 flex justify-end"><Button variant="outline" size="sm" onClick={openAssoc} data-testid="cat-assoc-people"><Plus className="mr-1 h-3.5 w-3.5" /> Associar pessoas</Button></div>
              <Table>
                <TableHeader><TableRow><TableHead>Pessoa</TableHead><TableHead>Tipo</TableHead><TableHead>Empresa</TableHead><TableHead></TableHead></TableRow></TableHeader>
                <TableBody>
                  {people.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>{p.name}</TableCell>
                      <TableCell className="capitalize">{p.person_type}</TableCell>
                      <TableCell>{p.company_name}</TableCell>
                      <TableCell><Button variant="ghost" size="icon" className="text-red-400" onClick={() => removePerson(p.id)}><Trash2 className="h-4 w-4" /></Button></TableCell>
                    </TableRow>
                  ))}
                  {people.length === 0 && <TableRow><TableCell colSpan={4} className="py-6 text-center text-muted-foreground">Nenhuma pessoa associada.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Card>
          </TabsContent>
        </Tabs>

        <Dialog open={assocOpen} onOpenChange={setAssocOpen}>
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Associar pessoas</DialogTitle></DialogHeader>
            <div className="max-h-80 overflow-y-auto scrollbar-thin space-y-1">
              {allPeople.map((p) => (
                <label key={p.id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-secondary text-sm">
                  <Checkbox checked={pSel.has(p.id)} onCheckedChange={() => { const n = new Set(pSel); n.has(p.id) ? n.delete(p.id) : n.add(p.id); setPSel(n); }} />
                  {p.name} <span className="text-muted-foreground">· {p.company_name}</span>
                </label>
              ))}
            </div>
            <DialogFooter><Button variant="outline" onClick={() => setAssocOpen(false)}>Cancelar</Button><Button className="bg-sky-500 text-slate-950" onClick={doAssoc}>Associar ({pSel.size})</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Categorias" subtitle="Perfis de acesso (áreas + faixas + regras)">
        {canEdit && <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={startNew} data-testid="cat-new"><Plus className="mr-2 h-4 w-4" /> Nova categoria</Button>}
      </PageHeader>
      <Card className="border-border bg-card">
        <Table>
          <TableHeader><TableRow><TableHead>Nome da categoria</TableHead><TableHead>Descrição</TableHead><TableHead>Áreas</TableHead><TableHead>Flags</TableHead><TableHead>Status</TableHead>{canEdit && <TableHead></TableHead>}</TableRow></TableHeader>
          <TableBody>
            {list.map((c) => (
              <TableRow key={c.id} data-testid={`category-row-${c.id}`}>
                <TableCell className="font-mono font-medium">{c.code}</TableCell>
                <TableCell>{c.description}</TableCell>
                <TableCell><Badge variant="outline">{(c.access_areas || []).length}</Badge></TableCell>
                <TableCell className="space-x-1">
                  {c.impeditive && <Badge variant="outline" className="bg-red-500/15 text-red-400 border-red-500/30">Impeditiva</Badge>}
                  {c.control_origin && <Badge variant="outline" className="text-xs">Origem</Badge>}
                  {c.control_anti_double && <Badge variant="outline" className="text-xs">Anti-dupla</Badge>}
                </TableCell>
                <TableCell>{c.enabled !== false ? <Badge variant="outline" className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">Ativa</Badge> : <Badge variant="outline">Inativa</Badge>}</TableCell>
                {canEdit && <TableCell className="text-right"><Button variant="ghost" size="icon" onClick={() => startEdit(c)} data-testid={`category-edit-${c.id}`}><Pencil className="h-4 w-4" /></Button></TableCell>}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
