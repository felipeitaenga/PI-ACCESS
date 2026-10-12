import axios from "axios";
import { useEffect, useRef } from "react";
import { API, formatApiErrorDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

// Cliente sem token: as páginas públicas nunca enviam a sessão de quem estiver logado no mesmo navegador.
export const pub = axios.create({ baseURL: `${API}/public/selfreg` });
export const errMsg = (e) => formatApiErrorDetail(e?.response?.data?.detail) || "Falha de conexão. Tente novamente.";
export const errFields = (e) => e?.response?.data?.detail?.fields || {};

export const fmtDT = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

export function PublicShell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto w-full max-w-md px-4 pb-16 pt-6">
        <div className="mb-5 flex items-center gap-3">
          <img src="/brand/pilares-logo.webp" alt="" className="h-9 w-auto object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
          <div className="min-w-0">
            <div className="font-heading text-lg font-extrabold leading-tight">{title || "PI-ACCESS"}</div>
            {subtitle && <div className="truncate text-xs uppercase tracking-widest text-sky-400">{subtitle}</div>}
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

export const Box = ({ className, children }) => (
  <div className={cn("rounded-xl border border-slate-800 bg-slate-900/70 p-4", className)}>{children}</div>
);

export const PField = ({ label, error, hint, children, required }) => (
  <div className="block">
    <span className="mb-1 block text-sm font-medium text-slate-200">{label}{required && <span className="text-sky-400"> *</span>}</span>
    {children}
    {error ? <span className="mt-1 block text-xs text-red-400">{error}</span> : hint ? <span className="mt-1 block text-xs text-slate-400">{hint}</span> : null}
  </div>
);

export const inputCls = "h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/30";

export const PButton = ({ className, variant = "primary", ...p }) => (
  <button type="button" {...p}
    className={cn("inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg px-4 text-base font-semibold transition disabled:opacity-50",
      variant === "primary" ? "bg-sky-500 text-slate-950 hover:bg-sky-400" : variant === "danger" ? "bg-red-500/90 text-white hover:bg-red-500" : "border border-slate-700 text-slate-200 hover:bg-slate-800",
      className)} />
);

// Cloudflare Turnstile (só aparece se o servidor tiver a chave configurada)
export function Captcha({ siteKey, onToken }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!siteKey || !ref.current) return undefined;
    let id = null;
    const render = () => { if (window.turnstile && ref.current && id === null) id = window.turnstile.render(ref.current, { sitekey: siteKey, callback: onToken, "expired-callback": () => onToken("") }); };
    if (window.turnstile) render();
    else {
      let s = document.querySelector("script[data-turnstile]");
      if (!s) {
        s = document.createElement("script");
        s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
        s.async = true; s.dataset.turnstile = "1";
        document.head.appendChild(s);
      }
      s.addEventListener("load", render);
    }
    return () => { try { if (id !== null) window.turnstile.remove(id); } catch { /* */ } };
  }, [siteKey]); // eslint-disable-line
  if (!siteKey) return null;
  return <div ref={ref} className="my-2 flex justify-center" />;
}
