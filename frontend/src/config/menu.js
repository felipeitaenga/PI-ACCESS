import {
  LayoutDashboard, Radio, Users, Network, Cpu, Flame, FileBarChart, Settings,
  Activity, Bell, UserPlus, Car, CreditCard, ShieldCheck, MapPin, Clock,
  CalendarDays, DoorOpen, Camera, Building2, Boxes, Briefcase, LogIn,
  CalendarClock, ScrollText, FileClock, RefreshCw, SlidersHorizontal, Plug,
  Keyboard, FlaskConical, DatabaseBackup, UsersRound, UserCog, IdCard,
} from "lucide-react";

// Menu central e extensível. Adicionar um submenu novo = adicionar uma entrada aqui.
export const MENU = [
  { type: "item", label: "Dashboard", to: "/", icon: LayoutDashboard, testid: "nav-dashboard" },
  {
    type: "group", label: "Monitoramento", icon: Radio, items: [
      { label: "Eventos ao vivo", to: "/monitoramento", icon: Activity, testid: "nav-live" },
      { label: "Ocupação por área", to: "/ocupacao", icon: Boxes, testid: "nav-occupancy" },
      { label: "Alarmes", to: "/alarmes", icon: Bell, badge: "alarms", testid: "nav-alarms" },
    ],
  },
  {
    type: "group", label: "Cadastro", icon: Users, items: [
      { label: "Cadastro de visitantes", to: "/cadastro/visitantes", icon: UserPlus, testid: "nav-register-visitors" },
      { label: "Cadastro de fixos", to: "/cadastro/fixos", icon: UserCog, testid: "nav-register-fixed" },
      { label: "Visitantes", to: "/visitantes", icon: IdCard, testid: "nav-visitors" },
      { label: "Fixos", to: "/pessoas", icon: Users, testid: "nav-people" },
      { label: "Veículos", to: "/veiculos", icon: Car, testid: "nav-vehicles" },
      { label: "Identificadores", to: "/identificadores", icon: CreditCard, testid: "nav-identifiers" },
    ],
  },
  {
    type: "group", label: "Controle de Acesso", icon: ShieldCheck, items: [
      { label: "Categorias", to: "/categorias", icon: ShieldCheck, testid: "nav-categories" },
      { label: "Áreas", to: "/areas", icon: MapPin, testid: "nav-areas" },
      { label: "Faixas horárias", to: "/faixas-horarias", icon: Clock, testid: "nav-timeranges" },
      { label: "Feriados", to: "/feriados", icon: CalendarDays, testid: "nav-holidays" },
    ],
  },
  {
    type: "group", label: "Equipamentos", icon: Cpu, items: [
      { label: "Controladoras", to: "/controladoras", icon: Cpu, testid: "nav-controllers" },
      { label: "Câmeras", to: "/cameras", icon: Camera, testid: "nav-cameras" },
    ],
  },
  {
    type: "group", label: "Organização", icon: Building2, items: [
      { label: "Empresas", to: "/empresas", icon: Building2, testid: "nav-companies" },
      { label: "Grupos de empresas", to: "/grupos-empresas", icon: Boxes, testid: "nav-company-groups" },
      { label: "Departamentos", to: "/departamentos", icon: Briefcase, testid: "nav-departments" },
    ],
  },
  {
    type: "group", label: "Portaria / Recepção", icon: LogIn, items: [
      { label: "Check-in / Check-out", to: "/portaria", icon: LogIn, testid: "nav-reception" },
      { label: "Agendamentos", to: "/agendamentos", icon: CalendarClock, testid: "nav-schedules" },
    ],
  },
  { type: "item", label: "Emergência", to: "/emergencia", icon: Flame, testid: "nav-emergency" },
  { type: "item", label: "Relatórios", to: "/relatorios", icon: FileBarChart, testid: "nav-reports" },
  {
    type: "group", label: "Logs", icon: ScrollText, items: [
      { label: "Acessos", to: "/logs/acessos", icon: FileClock, testid: "nav-logs-access" },
      { label: "Auditoria", to: "/logs/auditoria", icon: ScrollText, permission: "admin", testid: "nav-logs-audit" },
      { label: "Sincronização", to: "/logs/sincronizacao", icon: RefreshCw, testid: "nav-logs-sync" },
    ],
  },
  {
    type: "group", label: "Configurações", icon: Settings, permission: "admin", items: [
      { label: "Geral do sistema", to: "/configuracoes/geral", icon: SlidersHorizontal, testid: "nav-cfg-general" },
      { label: "Usuários e perfis", to: "/configuracoes/usuarios", icon: UsersRound, testid: "nav-cfg-users" },
      { label: "Integrações", to: "/configuracoes/integracoes", icon: Plug, testid: "nav-cfg-integrations" },
      { label: "Visitantes", to: "/configuracoes/visitantes", icon: IdCard, testid: "nav-cfg-visitors" },
      { label: "Atalhos", to: "/configuracoes/atalhos", icon: Keyboard, testid: "nav-cfg-shortcuts" },
      { label: "Simulador", to: "/configuracoes/simulador", icon: FlaskConical, testid: "nav-cfg-simulator" },
      { label: "Backup", to: "/configuracoes/backup", icon: DatabaseBackup, testid: "nav-cfg-backup" },
    ],
  },
];

// Lista achatada de todos os itens navegáveis (para busca Ctrl+K e favoritos).
export const MENU_FLAT = MENU.flatMap((e) =>
  e.type === "item" ? [{ ...e, group: null }] : e.items.map((i) => ({ ...i, group: e.label }))
);
