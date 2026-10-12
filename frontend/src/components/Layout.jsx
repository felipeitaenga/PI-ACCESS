import { useState, useEffect, useMemo } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useRealtime } from "@/context/RealtimeContext";
import { api, useAppInfo } from "@/lib/api";
import { MENU, MENU_FLAT } from "@/config/menu";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  LogOut, Menu, X, ChevronDown, Star, Search,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";

const LS = {
  collapsed: "nx_sidebar_collapsed",
  groups: "nx_menu_groups",
  favs: "nx_favorites",
};
const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const save = (k, v) => localStorage.setItem(k, JSON.stringify(v));

export const MANAGER_PATHS = new Set(["/", "/monitoramento", "/cadastro/visitantes", "/cadastro/fixos", "/visitantes", "/pessoas", "/relatorios", "/logs/acessos"]);

export function Layout({ children }) {
  const { user, logout, hasRole } = useAuth();
  const { connected, alarms } = useRealtime();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => load(LS.collapsed, false));
  const [groupState, setGroupState] = useState(() => load(LS.groups, {}));
  const [favs, setFavs] = useState(() => load(LS.favs, []));
  const [cmd, setCmd] = useState(false);
  const [query, setQuery] = useState("");
  const [alarmCount, setAlarmCount] = useState(0);
  const info = useAppInfo();

  useEffect(() => { save(LS.collapsed, collapsed); }, [collapsed]);
  useEffect(() => { save(LS.groups, groupState); }, [groupState]);
  useEffect(() => { save(LS.favs, favs); }, [favs]);
  useEffect(() => {
    api.get("/alarms?acknowledged=false").then(({ data }) => setAlarmCount(data.length)).catch(() => {});
  }, []);
  useEffect(() => {
    const pend = alarms.filter((a) => !a.acknowledged).length;
    if (pend) setAlarmCount((c) => c + pend);
  }, [alarms.length]); // eslint-disable-line
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setCmd(true); }
      if (e.key === "Escape") setCmd(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isMgr = user?.role === "company_manager";
  const allowed = (perm, to) => (isMgr ? (to ? MANAGER_PATHS.has(to) : true) : (!perm || hasRole(perm)));
  const badgeVal = (b) => (b === "alarms" ? alarmCount : 0);

  const favItems = useMemo(
    () => MENU_FLAT.filter((i) => favs.includes(i.to) && allowed(i.permission, i.to)),
    [favs, user] // eslint-disable-line
  );
  const toggleFav = (to, e) => {
    e.preventDefault(); e.stopPropagation();
    setFavs((f) => (f.includes(to) ? f.filter((x) => x !== to) : [...f, to]));
  };
  const toggleGroup = (label) => setGroupState((g) => ({ ...g, [label]: !(g[label] ?? true) }));

  const handleLogout = async () => { await logout(); navigate("/login"); };

  const searchResults = MENU_FLAT.filter(
    (i) => allowed(i.permission, i.to) && i.label.toLowerCase().includes(query.toLowerCase())
  );

  const Item = ({ it }) => (
    <NavLink
      to={it.to} end={it.to === "/"} data-testid={it.testid}
      onClick={() => setOpen(false)}
      title={collapsed ? it.label : undefined}
      className={({ isActive }) => cn(
        "group/item flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors relative",
        isActive ? "bg-sky-500/15 text-sky-400 font-medium" : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60",
        collapsed && "justify-center px-2"
      )}
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute left-0 top-1 bottom-1 w-0.5 rounded bg-sky-500" />}
          <it.icon className="h-4 w-4 shrink-0" />
          {!collapsed && <span className="flex-1 truncate">{it.label}</span>}
          {!collapsed && badgeVal(it.badge) > 0 && (
            <span className="rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">{badgeVal(it.badge)}</span>
          )}
          {!collapsed && (
            <button onClick={(e) => toggleFav(it.to, e)} data-testid={`fav-star-${it.testid || it.to}`} className="opacity-0 group-hover/item:opacity-100 transition-opacity">
              <Star className={cn("h-3.5 w-3.5", favs.includes(it.to) ? "fill-amber-400 text-amber-400" : "text-slate-500")} />
            </button>
          )}
        </>
      )}
    </NavLink>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <aside className={cn(
        "fixed inset-y-0 left-0 z-40 flex flex-col bg-slate-950/95 border-r border-slate-800 backdrop-blur-md transition-all lg:static",
        collapsed ? "w-16" : "w-64",
        open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      )}>
        <div className="flex h-16 items-center gap-2 px-4 border-b border-slate-800">
          <img src="/brand/pilares-logo.webp" alt="Pilares" className="h-9 w-auto shrink-0 object-contain" data-testid="sidebar-logo" />
          {!collapsed && (
            <div className="leading-tight">
              <div className="font-heading font-extrabold text-slate-100 tracking-tight">PI-ACCESS</div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Controle de Acesso</div>
            </div>
          )}
          <button className="ml-auto lg:hidden text-slate-400" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button>
        </div>

        {!collapsed && (
          <button onClick={() => setCmd(true)} data-testid="menu-search-trigger"
            className="mx-3 mt-3 flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900/50 px-3 py-2 text-xs text-slate-500 hover:border-slate-700">
            <Search className="h-3.5 w-3.5" /> Buscar menu <kbd className="ml-auto font-mono text-[10px] text-slate-600">Ctrl+K</kbd>
          </button>
        )}

        <nav className="flex-1 overflow-y-auto scrollbar-thin py-3 px-2 space-y-0.5">
          {favItems.length > 0 && !collapsed && (
            <div className="mb-2">
              <div className="px-3 pb-1 text-[10px] font-mono uppercase tracking-widest text-amber-500/70">Favoritos</div>
              {favItems.map((it) => <Item key={"fav" + it.to} it={it} />)}
              <div className="my-2 border-t border-slate-800/60" />
            </div>
          )}

          {MENU.map((entry) => {
            if (entry.type === "item") return allowed(entry.permission, entry.to) ? <Item key={entry.to} it={entry} /> : null;
            if (!allowed(entry.permission)) return null;
            const items = entry.items.filter((i) => allowed(i.permission, i.to));
            if (!items.length) return null;
            const openG = groupState[entry.label] ?? true;
            if (collapsed) return <div key={entry.label} className="space-y-0.5">{items.map((i) => <Item key={i.to} it={i} />)}</div>;
            return (
              <div key={entry.label}>
                <button onClick={() => toggleGroup(entry.label)} data-testid={`group-${entry.label}`}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-300">
                  <entry.icon className="h-4 w-4" />
                  <span className="flex-1 text-left">{entry.label}</span>
                  <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", !openG && "-rotate-90")} />
                </button>
                {openG && <div className="ml-2 space-y-0.5 border-l border-slate-800/60 pl-2">{items.map((i) => <Item key={i.to} it={i} />)}</div>}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-slate-800 p-2">
          <button onClick={() => setCollapsed(!collapsed)} data-testid="sidebar-collapse-toggle"
            className="mb-1 flex w-full items-center gap-3 rounded-md px-3 py-2 text-xs text-slate-500 hover:bg-slate-900/60">
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" /> Recolher</>}
          </button>
          <div className="flex items-center gap-2 rounded-md px-2 py-1">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-sky-400">
              {user?.name?.charAt(0) || "U"}
            </div>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-slate-200">{user?.name}</div>
                <div className="truncate text-xs text-slate-500">{user?.role_label}</div>
              </div>
            )}
            <Button variant="ghost" size="icon" data-testid="logout-button" onClick={handleLogout} className="text-slate-400 hover:text-red-400">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
          {!collapsed && info && (
            <p className="px-3 pt-1 font-mono text-[10px] text-slate-600" data-testid="app-version">PI-ACCESS v{info.version} · {info.cliente_nome}</p>
          )}
        </div>
      </aside>

      {open && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setOpen(false)} />}

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 px-4 sm:px-6 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <button className="lg:hidden text-slate-500" onClick={() => setOpen(true)} data-testid="mobile-menu-button"><Menu className="h-5 w-5" /></button>
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className={cn("status-dot animate-pulse-live", connected ? "bg-emerald-500" : "bg-red-500")} />
              <span className="text-slate-500">{connected ? "TEMPO REAL CONECTADO" : "RECONECTANDO..."}</span>
            </div>
          </div>
          <ThemeToggle />
        </header>
        <main className="flex-1 overflow-y-auto scrollbar-thin p-4 sm:p-6">{children}</main>
      </div>

      <Dialog open={cmd} onOpenChange={setCmd}>
        <DialogContent className="max-w-lg p-0 overflow-hidden">
          <DialogTitle className="sr-only">Buscar telas</DialogTitle>
          <div className="flex items-center gap-2 border-b border-border px-4">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} data-testid="command-search-input"
              placeholder="Buscar telas..." className="border-0 focus-visible:ring-0 h-12" />
          </div>
          <div className="max-h-80 overflow-y-auto scrollbar-thin p-2">
            {searchResults.map((r) => (
              <button key={r.to} data-testid={`command-result-${r.testid}`}
                onClick={() => { navigate(r.to); setCmd(false); setQuery(""); }}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm hover:bg-secondary">
                <r.icon className="h-4 w-4 text-sky-400" />
                <span>{r.label}</span>
                {r.group && <span className="ml-auto text-xs text-muted-foreground">{r.group}</span>}
              </button>
            ))}
            {searchResults.length === 0 && <div className="p-4 text-sm text-muted-foreground">Nada encontrado.</div>}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
