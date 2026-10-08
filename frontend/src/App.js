import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { RealtimeProvider } from "@/context/RealtimeContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Layout } from "@/components/Layout";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import Dashboard from "@/pages/Dashboard";
import LiveMonitoring from "@/pages/LiveMonitoring";
import People from "@/pages/People";
import Devices from "@/pages/Devices";
import Structure from "@/pages/Structure";
import Alarms from "@/pages/Alarms";
import Emergency from "@/pages/Emergency";
import Reports from "@/pages/Reports";
import Admin from "@/pages/Admin";
import { Credentials, Visitors, Rules } from "@/pages/Placeholders";

function Shell({ children }) {
  return (
    <ProtectedRoute>
      <RealtimeProvider>
        <Layout>{children}</Layout>
      </RealtimeProvider>
    </ProtectedRoute>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/esqueci-senha" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/" element={<Shell><Dashboard /></Shell>} />
      <Route path="/monitoramento" element={<Shell><LiveMonitoring /></Shell>} />
      <Route path="/pessoas" element={<Shell><People /></Shell>} />
      <Route path="/credenciais" element={<Shell><Credentials /></Shell>} />
      <Route path="/visitantes" element={<Shell><Visitors /></Shell>} />
      <Route path="/estrutura" element={<Shell><Structure /></Shell>} />
      <Route path="/dispositivos" element={<Shell><Devices /></Shell>} />
      <Route path="/regras" element={<Shell><Rules /></Shell>} />
      <Route path="/emergencia" element={<Shell><Emergency /></Shell>} />
      <Route path="/relatorios" element={<Shell><Reports /></Shell>} />
      <Route path="/alarmes" element={<Shell><Alarms /></Shell>} />
      <Route path="/administracao" element={<Shell><Admin /></Shell>} />
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
