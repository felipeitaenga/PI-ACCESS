import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { RealtimeProvider } from "@/context/RealtimeContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Layout } from "@/components/Layout";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import Dashboard from "@/pages/Dashboard";
import LiveMonitoring from "@/pages/LiveMonitoring";
import { FixedBrowse, VisitorsBrowse, FixedRegister, VisitorRegister } from "@/pages/Registry";
import Alarms from "@/pages/Alarms";
import Emergency from "@/pages/Emergency";
import Reports from "@/pages/Reports";
import Admin from "@/pages/Admin";
import Categories from "@/pages/Categories";
import { TimeRanges, Holidays, Areas } from "@/pages/AccessModel";
import { Controllers } from "@/pages/Equipment";
import { Companies, CompanyGroups, Departments, Vehicles, Identifiers } from "@/pages/SimpleCrud";
import { ConfigHub, Simulator } from "@/pages/Config";
import { Occupancy, LogsAccess, LogsSync } from "@/pages/Misc";
import { Cameras, Schedules, Shortcuts, Backup } from "@/pages/Placeholders";
import Integrations from "@/pages/Integrations";

function Shell({ children }) {
  return (
    <ProtectedRoute>
      <RealtimeProvider>
        <Layout>{children}</Layout>
      </RealtimeProvider>
    </ProtectedRoute>
  );
}

const R = (path, el) => <Route key={path} path={path} element={<Shell>{el}</Shell>} />;

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/esqueci-senha" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      {R("/", <Dashboard />)}
      {R("/monitoramento", <LiveMonitoring />)}
      {R("/ocupacao", <Occupancy />)}
      {R("/alarmes", <Alarms />)}
      {R("/pessoas", <FixedBrowse />)}
      {R("/visitantes", <VisitorsBrowse />)}
      {R("/cadastro/fixos", <FixedRegister />)}
      {R("/cadastro/visitantes", <VisitorRegister />)}
      {R("/veiculos", <Vehicles />)}
      {R("/identificadores", <Identifiers />)}
      {R("/categorias", <Categories />)}
      {R("/areas", <Areas />)}
      {R("/faixas-horarias", <TimeRanges />)}
      {R("/feriados", <Holidays />)}
      {R("/controladoras", <Controllers />)}
      <Route path="/pontos-acesso" element={<Navigate to="/controladoras" replace />} />
      {R("/cameras", <Cameras />)}
      {R("/empresas", <Companies />)}
      {R("/grupos-empresas", <CompanyGroups />)}
      {R("/departamentos", <Departments />)}
      <Route path="/portaria" element={<Navigate to="/cadastro/visitantes" replace />} />
      {R("/agendamentos", <Schedules />)}
      {R("/emergencia", <Emergency />)}
      {R("/relatorios", <Reports />)}
      {R("/logs/acessos", <LogsAccess />)}
      {R("/logs/auditoria", <Admin />)}
      {R("/logs/sincronizacao", <LogsSync />)}
      {R("/configuracoes", <ConfigHub />)}
      {R("/configuracoes/geral", <Admin />)}
      {R("/configuracoes/usuarios", <Admin />)}
      {R("/configuracoes/integracoes", <Integrations />)}
      {R("/configuracoes/atalhos", <Shortcuts />)}
      {R("/configuracoes/simulador", <Simulator />)}
      {R("/configuracoes/backup", <Backup />)}
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
