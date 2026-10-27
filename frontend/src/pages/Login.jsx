import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail, useAppInfo } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Lock } from "lucide-react";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const info = useAppInfo();

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-950">
      {/* Visual side */}
      <div className="relative hidden lg:flex lg:w-1/2 flex-col justify-between overflow-hidden border-r border-slate-800 p-12">
        <div
          className="absolute inset-0 opacity-60"
          style={{
            backgroundImage: "url('/brand/login-access.jpg')",
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
          data-testid="login-hero-image"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/60 to-slate-950/20" />
        <div className="relative flex items-center gap-4">
          <img src="/brand/scarvel-logo-h.png" alt="SCARVEL — Controle de Acesso" className="h-16 w-auto object-contain" data-testid="login-logo" />
        </div>
        <div className="relative max-w-md">
          <h2 className="font-heading text-3xl font-bold text-white leading-tight">
            Controle de acesso corporativo em tempo real
          </h2>
          <p className="mt-4 text-sm text-slate-400">
            Monitoramento ao vivo, gestão de pessoas e dispositivos, alarmes e resposta de
            emergência — tudo num único painel de operação.
          </p>
        </div>
      </div>

      {/* Form side */}
      <div className="flex w-full flex-col justify-center px-6 py-12 lg:w-1/2 sm:px-16 lg:px-24">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <img src="/brand/scarvel-logo-h.png" alt="SCARVEL — Controle de Acesso" className="h-12 w-auto object-contain" data-testid="login-logo-mobile" />
          </div>
          <h1 className="font-heading text-2xl font-bold text-white">Acessar o painel</h1>
          <p className="mt-1 text-sm text-slate-500">Use suas credenciais corporativas.</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-slate-300">E-mail</Label>
              <Input
                id="email" type="email" data-testid="login-email-input"
                value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="voce@empresa.com" required
                className="bg-slate-900 border-slate-700 text-slate-100"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-slate-300">Senha</Label>
                {info?.email_enabled && (
                  <Link to="/esqueci-senha" className="text-xs text-sky-400 hover:text-sky-300" data-testid="forgot-password-link">
                    Esqueceu a senha?
                  </Link>
                )}
              </div>
              <Input
                id="password" type="password" data-testid="login-password-input"
                value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••" required
                className="bg-slate-900 border-slate-700 text-slate-100"
              />
            </div>
            {error && (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400" data-testid="login-error">
                {error}
              </div>
            )}
            <Button type="submit" disabled={loading} data-testid="login-submit-button" className="w-full bg-sky-500 hover:bg-sky-600 text-white font-semibold">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Lock className="mr-2 h-4 w-4" /> Entrar</>}
            </Button>
          </form>

          {info?.demo && (
            <div className="mt-6 rounded-md border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-500" data-testid="login-demo-box">
              <div className="font-mono uppercase tracking-wide text-slate-600 mb-1">Demo — Administrador</div>
              felipejferreira@gmail.com / NxAccess@2026
            </div>
          )}
          {info && <p className="mt-6 text-center font-mono text-[11px] text-slate-600" data-testid="login-version">{info.cliente_nome} · v{info.version}</p>}
        </div>
      </div>
    </div>
  );
}
