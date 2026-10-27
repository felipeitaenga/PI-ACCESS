import { useState } from "react";
import CrudPage, { FormRow, enabledBadge } from "@/components/CrudPage";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2 } from "lucide-react";

const DOW = [["Dom", 0], ["Seg", 1], ["Ter", 2], ["Qua", 3], ["Qui", 4], ["Sex", 5], ["Sáb", 6]];

export function TimeRanges() {
  const renderForm = (form, setForm) => {
    const intervals = form.intervals || [{ start: "00:00", end: "23:59" }];
    const wd = form.weekdays || [];
    const setIv = (i, k, v) => { const n = [...intervals]; n[i] = { ...n[i], [k]: v }; setForm({ ...form, intervals: n }); };
    return (
      <div className="space-y-4">
        <FormRow label="Descrição"><Input value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="tr-description" /></FormRow>
        <FormRow label="Dias da semana válidos">
          <div className="flex flex-wrap gap-2">
            {DOW.map(([lbl, d]) => (
              <button key={d} type="button" data-testid={`tr-dow-${d}`}
                onClick={() => setForm({ ...form, weekdays: wd.includes(d) ? wd.filter((x) => x !== d) : [...wd, d] })}
                className={`rounded-md border px-3 py-1.5 text-sm ${wd.includes(d) ? "bg-sky-500 text-white border-sky-500" : "border-border text-muted-foreground"}`}>{lbl}</button>
            ))}
          </div>
        </FormRow>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={!!form.valid_on_holidays} onCheckedChange={(v) => setForm({ ...form, valid_on_holidays: !!v })} data-testid="tr-holidays" /> Válida em feriados</label>
        <FormRow label="Intervalos">
          <div className="space-y-2">
            {intervals.map((iv, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input type="time" value={iv.start} onChange={(e) => setIv(i, "start", e.target.value)} className="w-32" />
                <span className="text-muted-foreground">até</span>
                <Input type="time" value={iv.end} onChange={(e) => setIv(i, "end", e.target.value)} className="w-32" />
                <Button variant="ghost" size="icon" className="text-red-400" onClick={() => setForm({ ...form, intervals: intervals.filter((_, x) => x !== i) })}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setForm({ ...form, intervals: [...intervals, { start: "08:00", end: "18:00" }] })}><Plus className="mr-1 h-3.5 w-3.5" /> Intervalo</Button>
          </div>
        </FormRow>
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={form.enabled !== false} onCheckedChange={(v) => setForm({ ...form, enabled: !!v })} /> Habilitada</label>
      </div>
    );
  };
  return (
    <CrudPage title="Faixas horárias" subtitle="Janelas de permissão por dia e horário" endpoint="/access/time-ranges"
      defaultForm={{ description: "", weekdays: [1, 2, 3, 4, 5], valid_on_holidays: false, intervals: [{ start: "08:00", end: "18:00" }], enabled: true }}
      renderForm={renderForm}
      columns={[
        { key: "description", label: "Descrição" },
        { label: "Dias", render: (r) => <span className="font-mono text-xs">{(r.weekdays || []).map((d) => DOW[d][0]).join(" ")}</span> },
        { label: "Intervalos", render: (r) => <span className="font-mono text-xs">{(r.intervals || []).map((i) => `${i.start}-${i.end}`).join(", ")}</span> },
        { label: "Feriados", render: (r) => (r.valid_on_holidays ? "Sim" : "Não") },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}

export function Holidays() {
  return (
    <CrudPage title="Feriados" subtitle="Datas que alteram as faixas horárias" endpoint="/access/holidays"
      defaultForm={{ date: "", description: "", recurring_annual: false, scope: "all", enabled: true }}
      formFields={[
        { key: "date", label: "Data", type: "date", full: false },
        { key: "description", label: "Descrição", full: false },
        { key: "recurring_annual", label: "Recorrente anual", type: "checkbox", hint: "Repete todo ano" },
        { key: "scope", label: "Abrangência", type: "select", options: [{ value: "all", label: "Todos os sites" }] },
      ]}
      columns={[
        { key: "date", label: "Data" },
        { key: "description", label: "Descrição" },
        { label: "Recorrente", render: (r) => (r.recurring_annual ? "Anual" : "Única") },
        { label: "Abrangência", render: (r) => (r.scope === "all" ? "Todos" : "Site") },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}

export function Areas() {
  return (
    <CrudPage title="Áreas" subtitle="Zonas físicas do site · lotação calculada por eventos" endpoint="/access/areas"
      defaultForm={{ description: "", anti_double_entry: false, max_occupancy: 0, is_exterior: false, enabled: true }}
      formFields={[
        { key: "description", label: "Descrição", full: true },
        { key: "max_occupancy", label: "Lotação máxima (0 = ilimitada)", type: "number" },
        { key: "anti_double_entry", label: "Anti-dupla entrada", type: "checkbox", hint: "Bloqueia entrar duas vezes sem sair" },
        { key: "is_exterior", label: "Área EXTERIOR", type: "checkbox", hint: "Fora do site" },
      ]}
      columns={[
        { key: "description", label: "Área", render: (r) => <span className="font-medium">{r.description}</span> },
        { key: "site_name", label: "Site" },
        { label: "Anti-dupla", render: (r) => (r.anti_double_entry ? <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/30">Sim</Badge> : "Não") },
        { label: "Lotação", render: (r) => <span className="font-mono">{r.current_occupancy || 0}{r.max_occupancy ? `/${r.max_occupancy}` : ""}</span> },
        { key: "enabled", label: "Status", render: (r) => enabledBadge(r.enabled) },
      ]} />
  );
}
