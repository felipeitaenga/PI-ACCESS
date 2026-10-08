import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, StatusDot } from "@/components/common";
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
import { Badge } from "@/components/ui/badge";
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion";
import { Plus, Building2, MapPin, DoorClosed } from "lucide-react";
import { toast } from "sonner";

function doorModeBadge(mode) {
  const map = {
    normal: "bg-slate-500/15 text-slate-400 border-slate-500/30",
    liberada: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    bloqueada: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  return <Badge variant="outline" className={map[mode]}>{mode}</Badge>;
}

export default function Structure() {
  const { hasRole } = useAuth();
  const [sites, setSites] = useState([]);
  const [areas, setAreas] = useState([]);
  const [doors, setDoors] = useState([]);
  const [devices, setDevices] = useState([]);
  const [dialog, setDialog] = useState(null); // {type, parent}
  const [form, setForm] = useState({});

  const load = async () => {
    const [s, a, d, dev] = await Promise.all([
      api.get("/structure/sites"), api.get("/structure/areas"),
      api.get("/structure/doors"), api.get("/devices"),
    ]);
    setSites(s.data); setAreas(a.data); setDoors(d.data); setDevices(dev.data);
  };
  useEffect(() => { load(); }, []);

  const canEdit = hasRole("admin", "operator");

  const openDialog = (type, parent = {}) => {
    setForm(type === "site" ? { name: "", address: "" }
      : type === "area" ? { name: "", site_id: parent.site_id, max_occupancy: 0, anti_passback: "none" }
      : { name: "", site_id: parent.site_id, area_id: parent.area_id });
    setDialog({ type, parent });
  };

  const save = async () => {
    try {
      const path = dialog.type === "site" ? "/structure/sites" : dialog.type === "area" ? "/structure/areas" : "/structure/doors";
      await api.post(path, form);
      toast.success("Criado com sucesso");
      setDialog(null); load();
    } catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="Estrutura" subtitle="Sites › Áreas › Portas › Dispositivos">
        {canEdit && <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={() => openDialog("site")} data-testid="add-site-button"><Plus className="mr-2 h-4 w-4" /> Novo site</Button>}
      </PageHeader>

      <div className="space-y-4">
        {sites.map((site) => (
          <Card key={site.id} className="border-border bg-card p-4" data-testid={`site-${site.id}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400"><Building2 className="h-5 w-5" /></div>
                <div>
                  <div className="font-heading font-bold">{site.name}</div>
                  <div className="text-xs text-muted-foreground">{site.address}</div>
                </div>
              </div>
              {canEdit && <Button variant="outline" size="sm" onClick={() => openDialog("area", { site_id: site.id })} data-testid={`add-area-${site.id}`}><Plus className="mr-1 h-3.5 w-3.5" /> Área</Button>}
            </div>

            <Accordion type="multiple" className="mt-4">
              {areas.filter((a) => a.site_id === site.id).map((area) => (
                <AccordionItem key={area.id} value={area.id} className="border-border">
                  <AccordionTrigger className="hover:no-underline">
                    <div className="flex flex-1 items-center gap-2 pr-4">
                      <MapPin className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{area.name}</span>
                      <Badge variant="outline" className="ml-2 text-xs">{doors.filter((d) => d.area_id === area.id).length} portas</Badge>
                      {area.anti_passback !== "none" && <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-400 border-amber-500/30">anti-passback {area.anti_passback}</Badge>}
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2 pl-6">
                      {doors.filter((d) => d.area_id === area.id).map((door) => {
                        const devs = devices.filter((x) => x.door_id === door.id);
                        return (
                          <div key={door.id} className="rounded-md border border-border/50 p-3" data-testid={`door-${door.id}`}>
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <DoorClosed className="h-4 w-4 text-muted-foreground" />
                                <span className="font-medium">{door.name}</span>
                              </div>
                              {doorModeBadge(door.mode)}
                            </div>
                            {devs.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-2 pl-6">
                                {devs.map((dv) => (
                                  <div key={dv.id} className="flex items-center gap-1.5 rounded border border-border/50 px-2 py-1 text-xs">
                                    <StatusDot online={dv.online} /> {dv.name}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {canEdit && <Button variant="ghost" size="sm" onClick={() => openDialog("door", { site_id: site.id, area_id: area.id })} data-testid={`add-door-${area.id}`}><Plus className="mr-1 h-3.5 w-3.5" /> Adicionar porta</Button>}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </Card>
        ))}
      </div>

      <Dialog open={!!dialog} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Novo {dialog?.type === "site" ? "site" : dialog?.type === "area" ? "área" : "porta"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="mb-1.5 block text-xs text-muted-foreground">Nome</Label><Input value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="structure-name-input" /></div>
            {dialog?.type === "site" && <div><Label className="mb-1.5 block text-xs text-muted-foreground">Endereço</Label><Input value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>}
            {dialog?.type === "area" && (
              <>
                <div><Label className="mb-1.5 block text-xs text-muted-foreground">Ocupação máxima</Label><Input type="number" value={form.max_occupancy || 0} onChange={(e) => setForm({ ...form, max_occupancy: +e.target.value })} /></div>
                <div><Label className="mb-1.5 block text-xs text-muted-foreground">Anti-passback</Label>
                  <Select value={form.anti_passback} onValueChange={(v) => setForm({ ...form, anti_passback: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="none">Nenhum</SelectItem><SelectItem value="soft">Flexível</SelectItem><SelectItem value="hard">Rígido</SelectItem></SelectContent>
                  </Select>
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>Cancelar</Button>
            <Button className="bg-sky-500 hover:bg-sky-600 text-slate-950" onClick={save} data-testid="structure-save-button">Salvar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
