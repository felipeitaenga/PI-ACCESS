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

export const scrollToError = () => requestAnimationFrame(() => {
  document.querySelector("[data-field-error='true']")?.scrollIntoView({ behavior: "smooth", block: "center" });
});

export function PublicShell({ title, subtitle, children, bar }) {
  return (
    <div className="min-h-[100dvh] bg-slate-950 text-base text-slate-100">
      <div className={cn("mx-auto w-full max-w-md px-4 pt-5", bar ? "pb-36" : "pb-12")}>
        <div className="mb-5 flex items-center gap-3">
          <img src="/brand/scarvel-mark.png" alt="SCARVEL" className="h-10 w-auto object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} />
          <div className="min-w-0">
            <div className="truncate font-heading text-lg font-extrabold leading-tight" data-testid="public-title">{title || "SCARVEL"}</div>
            {subtitle && <div className="truncate text-xs uppercase tracking-widest text-sky-400">{subtitle}</div>}
          </div>
        </div>
        {children}
      </div>
      {bar && <BottomBar>{bar}</BottomBar>}
    </div>
  );
}

export const BottomBar = ({ children }) => (
  <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-800 bg-slate-950/95 backdrop-blur" data-testid="public-bottom-bar">
    <div className="mx-auto flex w-full max-w-md gap-2 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">{children}</div>
  </div>
);

export function StepBar({ steps, current }) {
  return (
    <div className="mb-5" data-testid="selfreg-stepbar" aria-label={`Passo ${current + 1} de ${steps.length}`}>
      <div className="mb-2 flex justify-between text-xs text-slate-400">
        <span className="font-semibold text-sky-300">Passo {current + 1} de {steps.length}</span><span>{steps[current]}</span>
      </div>
      <div className="flex gap-1.5">
        {steps.map((s, i) => (
          <div key={s} className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
            <div className={cn("h-full rounded-full bg-sky-500 transition-[width] duration-200 motion-reduce:transition-none", i <= current ? "w-full" : "w-0")} />
          </div>
        ))}
      </div>
    </div>
  );
}

export const Skeleton = ({ className }) => <div className={cn("rounded-xl bg-slate-800/70 motion-safe:animate-pulse", className)} />;
export const PageSkeleton = () => (
  <div className="space-y-3" data-testid="public-skeleton"><Skeleton className="h-6 w-2/3" /><Skeleton className="h-28" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
);

export const Box = ({ className, children, ...p }) => (
  <div className={cn("rounded-2xl border border-slate-800 bg-slate-900/70 p-4", className)} {...p}>{children}</div>
);

export const PField = ({ label, error, hint, children, required, htmlFor }) => (
  <div className="block" data-field-error={error ? "true" : undefined}>
    <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-slate-200">{label}{required && <span className="text-sky-400"> *</span>}</label>
    {children}
    {error ? <span className="mt-1.5 block text-sm text-red-400" role="alert">{error}</span> : hint ? <span className="mt-1.5 block text-xs text-slate-400">{hint}</span> : null}
  </div>
);

export const inputCls = "h-12 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 text-base text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/40";

export const PButton = ({ className, variant = "primary", ...p }) => (
  <button type="button" {...p}
    className={cn("inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-4 text-base font-semibold transition-[background-color,transform,opacity] duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:opacity-50 motion-reduce:transition-none",
      variant === "primary" ? "bg-sky-500 text-white hover:bg-sky-400" : variant === "danger" ? "bg-red-500/90 text-white hover:bg-red-500" : variant === "success" ? "bg-emerald-500 text-slate-950 hover:bg-emerald-400" : "border border-slate-700 text-slate-200 hover:bg-slate-800",
      className)} />
);

export const Alert = ({ children, tone = "error", ...p }) => (
  <p role="alert" {...p} className={cn("rounded-xl border px-3 py-2.5 text-sm",
    tone === "error" ? "border-red-500/40 bg-red-500/10 text-red-300" : "border-amber-500/40 bg-amber-500/10 text-amber-200")}>{children}</p>
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
