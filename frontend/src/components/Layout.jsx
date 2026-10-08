import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useRealtime } from "@/context/RealtimeContext";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard, Radio, Users, CreditCard, UserPlus, Network, Cpu,
  ShieldCheck, Flame, FileBarChart, Bell, Settings, LogOut, Menu, X, ShieldHalf,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", testid: "sidebar-nav-dashboard", roles: [] },
  { to: "/monitoramento", icon: Radio, label: "Monitoramento", testid: "sidebar-nav-live-monitoring", roles: [] },
  { to: "/pessoas", icon: Users, label: "Pessoas", testid: "sidebar-nav-people", roles: [] },
  { to: "/credenciais", icon: CreditCard, label: "Credenciais", testid: "sidebar-nav-credentials", roles: [] },
  { to: "/visitantes", icon: UserPlus, label: "Visitantes", testid: "sidebar-nav-visitors", roles: [] },
  { to: "/estrutura", icon: Network, label: "Estrutura", testid: "sidebar-nav-structure", roles: [] },
  { to: "/dispositivos", icon: Cpu, label: "Dispositivos", testid: "sidebar-nav-devices", roles: [] },
  { to: "/regras", icon: ShieldCheck, label: "Regras de Acesso", testid: "sidebar-nav-rules", roles: [] },
  { to: "/emergencia", icon: Flame, label: "Emergência", testid: "sidebar-nav-emergency", roles: [] },
  { to: "/relatorios", icon: FileBarChart, label: "Relatórios", testid: "sidebar-nav-reports", roles: [] },
  { to: "/alarmes", icon: Bell, label: "Alarmes", testid: "sidebar-nav-alarms", roles: [] },
  { to: "/administracao", icon: Settings, label: "Administração", testid: "sidebar-nav-settings", roles: ["admin"] },
];

export function Layout({ children }) {
  const { user, logout, hasRole } = useAuth();
  const { connected, alarms } = useRealtime();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const items = NAV.filter((n) => n.roles.length === 0 || hasRole(...n.roles));
  const openAlarms = alarms.filter((a) => !a.acknowledged).length;

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 flex flex-col bg-slate-950/95 dark:bg-slate-950/95 border-r border-slate-800 backdrop-blur-md transition-transform lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center gap-2 px-5 border-b border-slate-800">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-500 text-slate-950">
            <ShieldHalf className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <div className="font-heading font-extrabold text-slate-100 tracking-tight">NX-ACCESS</div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Controle de Acesso</div>
          </div>
          <button className="ml-auto lg:hidden text-slate-400" onClick={() => setOpen(false)}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar-thin py-3 px-2 space-y-0.5">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              data-testid={n.testid}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-sky-500/15 text-sky-400 font-medium border-r-2 border-sky-500"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
                )
              }
            >
              <n.icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{n.label}</span>
              {n.to === "/alarmes" && openAlarms > 0 && (
                <span className="rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">{openAlarms}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="flex items-center gap-3 rounded-md px-2 py-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-sky-400">
              {user?.name?.charAt(0) || "U"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-slate-200">{user?.name}</div>
              <div className="truncate text-xs text-slate-500">{user?.role_label}</div>
            </div>
            <Button variant="ghost" size="icon" data-testid="logout-button" onClick={handleLogout} className="text-slate-400 hover:text-red-400">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </aside>

      {open && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setOpen(false)} />}

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 px-4 sm:px-6 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <button className="lg:hidden text-slate-500" onClick={() => setOpen(true)} data-testid="mobile-menu-button">
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className={cn("status-dot animate-pulse-live", connected ? "bg-emerald-500" : "bg-red-500")} />
              <span className="text-slate-500">{connected ? "TEMPO REAL CONECTADO" : "RECONECTANDO..."}</span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto scrollbar-thin p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
