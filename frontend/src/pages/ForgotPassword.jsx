import { useState } from "react";
import { Link } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowLeft, Loader2, Mail } from "lucide-react";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6">
      <div className="w-full max-w-sm">
        <h1 className="font-heading text-2xl font-bold text-white">Recuperar senha</h1>
        <p className="mt-1 text-sm text-slate-500">Enviaremos um link de redefinição para seu e-mail.</p>
        {sent ? (
          <div className="mt-8 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-4 text-sm text-emerald-400" data-testid="forgot-sent">
            Se o e-mail estiver cadastrado, um link de redefinição foi enviado.
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-slate-300">E-mail</Label>
              <Input id="email" type="email" value={email} data-testid="forgot-email-input"
                onChange={(e) => setEmail(e.target.value)} required
                className="bg-slate-900 border-slate-700 text-slate-100" />
            </div>
            {error && <div className="text-sm text-red-400">{error}</div>}
            <Button type="submit" disabled={loading} data-testid="forgot-submit-button" className="w-full bg-sky-500 hover:bg-sky-600 text-slate-950 font-semibold">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Mail className="mr-2 h-4 w-4" /> Enviar link</>}
            </Button>
          </form>
        )}
        <Link to="/login" className="mt-6 inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" /> Voltar ao login
        </Link>
      </div>
    </div>
  );
}
