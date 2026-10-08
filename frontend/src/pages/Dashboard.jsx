import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useRealtime } from "@/context/RealtimeContext";
import { PageHeader, ResultBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import {
  DoorOpen, ShieldCheck, ShieldX, Cpu, AlertTriangle, Users, Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

function Kpi({ icon: Icon, label, value, sub, tone = "sky", testid }) {
  const tones = {
    sky: "text-sky-400 bg-sky-500/10",
    emerald: "text-emerald-400 bg-emerald-500/10",
    red: "text-red-400 bg-red-500/10",
    amber: "text-amber-400 bg-amber-500/10",
  };
  return (
    <Card data-testid={testid} className="relative overflow-hidden border-border bg-card p-5 transition-colors hover:border-sky-500/40">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">{label}</div>
          <div className="mt-2 text-3xl font-extrabold font-mono tracking-tight">{value}</div>
          {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
        </div>
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", tones[tone])}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </Card>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-xl">
      <div className="font-mono text-slate-300 mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2" style={{ color: p.color }}>
          <span>{p.dataKey === "liberados" ? "Liberados" : "Negados"}:</span>
          <span className="font-mono font-semibold">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const { events: liveEvents } = useRealtime();

  const load = async () => {
    const { data } = await api.get("/dashboard/stats");
    setStats(data);
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const recent = [...liveEvents, ...(stats?.recent_events || [])]
    .filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i)
    .slice(0, 12);

  if (!stats) return <div className="text-muted-foreground">Carregando painel...</div>;

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Visão geral da operação em tempo real" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi icon={ShieldCheck} label="Liberados hoje" value={stats.today.granted} sub={`${stats.today.total} acessos no total`} tone="emerald" testid="kpi-granted" />
        <Kpi icon={ShieldX} label="Negados hoje" value={stats.today.denied} sub="tentativas bloqueadas" tone="red" testid="kpi-denied" />
        <Kpi icon={Cpu} label="Dispositivos" value={`${stats.devices.online}/${stats.devices.total}`} sub={`${stats.devices.offline} offline`} tone="sky" testid="kpi-devices" />
        <Kpi icon={AlertTriangle} label="Alarmes abertos" value={stats.alarms.open} sub={`${stats.alarms.forced} portas forçadas`} tone="amber" testid="kpi-alarms" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Kpi icon={DoorOpen} label="Portas liberadas" value={stats.doors.liberated} sub={`de ${stats.doors.total} portas`} tone="sky" testid="kpi-doors" />
        <Kpi icon={Users} label="Pessoas ativas" value={stats.people.active} sub={`${stats.people.total} cadastradas`} tone="emerald" testid="kpi-people" />
        <Kpi icon={Activity} label="Fluxo 24h" value={stats.flow.reduce((a, b) => a + b.liberados + b.negados, 0)} sub="eventos registrados" tone="sky" testid="kpi-flow" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Card className="border-border bg-card p-5 lg:col-span-7">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Fluxo de acessos por hora</h2>
            <span className="text-xs font-mono text-muted-foreground">Últimas 24h · America/Sao_Paulo</span>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={stats.flow} margin={{ left: -20, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="gLib" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gNeg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#EF4444" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} interval={2} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="liberados" stroke="#10B981" strokeWidth={2} fill="url(#gLib)" />
              <Area type="monotone" dataKey="negados" stroke="#EF4444" strokeWidth={2} fill="url(#gNeg)" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card className="border-border bg-card p-5 lg:col-span-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Últimos eventos</h2>
            <span className="status-dot animate-pulse-live bg-emerald-500" />
          </div>
          <div className="space-y-1 max-h-[280px] overflow-y-auto scrollbar-thin">
            {recent.map((e) => (
              <div key={e.id} className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-secondary/50">
                {e.person_photo ? (
                  <img src={e.person_photo} alt="" className="h-8 w-8 rounded-full object-cover" />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-secondary" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{e.person_name}</div>
                  <div className="truncate text-xs text-muted-foreground">{e.door_name} · {e.direction}</div>
                </div>
                <ResultBadge result={e.access_result} />
              </div>
            ))}
            {recent.length === 0 && <div className="text-sm text-muted-foreground">Aguardando eventos...</div>}
          </div>
        </Card>
      </div>
    </div>
  );
}
