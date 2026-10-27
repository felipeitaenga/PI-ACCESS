import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowLeft, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/reset-password", { token, password });
      toast.success("Senha redefinida com sucesso");
      navigate("/login");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6">
      <div className="w-full max-w-sm">
        <h1 className="font-heading text-2xl font-bold text-white">Nova senha</h1>
        <p className="mt-1 text-sm text-slate-500">Defina uma nova senha para sua conta.</p>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password" className="text-slate-300">Nova senha</Label>
            <Input id="password" type="password" value={password} data-testid="reset-password-input"
              onChange={(e) => setPassword(e.target.value)} required minLength={6}
              className="bg-slate-900 border-slate-700 text-slate-100" />
          </div>
          {error && <div className="text-sm text-red-400">{error}</div>}
          <Button type="submit" disabled={loading || !token} data-testid="reset-submit-button" className="w-full bg-sky-500 hover:bg-sky-600 text-white font-semibold">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Redefinir senha"}
          </Button>
        </form>
        <Link to="/login" className="mt-6 inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" /> Voltar ao login
        </Link>
      </div>
    </div>
  );
}
