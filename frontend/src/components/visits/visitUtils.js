import { maskCpf, toLocalInput, validCpf } from "@/lib/br";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let settingsCache = null;
export function useDocSettings() {
  const [s, setS] = useState(settingsCache || { validate_cpf: true, validate_rg: false, default_hours: 8 });
  useEffect(() => { api.get("/visits/settings").then(({ data }) => { settingsCache = data; setS(data); }).catch(() => {}); }, []);
  return s;
}

export const DOC_TYPES = [["cpf", "CPF"], ["rg", "RG"], ["passaporte", "Passaporte"], ["outro", "Outro"]];
export const ID_TYPES = [["facial", "Facial"], ["cartao", "Cartão"], ["qrcode", "QR Code"]];

export const addHours = (local, h) => (local ? toLocalInput(new Date(new Date(local).getTime() + h * 3600e3).toISOString()) : "");
export const endOfDay = (local) => `${(local || toLocalInput(new Date().toISOString())).slice(0, 10)}T23:59`;
export const typeHours = (t, s) => Number(t?.default_hours) || Number(s?.default_hours) || 8;

export const maskDoc = (type, v, s) => {
  const x = String(v || "");
  if (type === "cpf") return s?.validate_cpf !== false ? maskCpf(x) : x;
  if (type === "rg" && s?.validate_rg) return x.toUpperCase().replace(/[^0-9X]/g, "").slice(0, 14);
  if (type === "passaporte") return x.toUpperCase();
  return x;
};

export const docError = (type, v, s) => {
  if (!String(v || "").trim()) return "Informe o número do documento";
  if (type === "cpf" && s?.validate_cpf !== false && !validCpf(v)) return "CPF inválido";
  if (type === "rg" && s?.validate_rg && !/^[0-9X]{5,14}$/.test(v)) return "RG inválido: somente números/X, 5 a 14 caracteres";
  return null;
};

export const maskPlate = (v) => {
  const r = String(v || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);
  return /^[A-Z]{3}\d{4}$/.test(r) ? `${r.slice(0, 3)}-${r.slice(3)}` : r;
};
export const plateError = (v) => (!v || /^[A-Z]{3}-?\d[A-Z0-9]\d{2}$/.test(v) ? null : "Placa inválida (AAA0A00 ou AAA-0000)");

export const fmtRemaining = (min) => (min < 0 ? "vencida" : `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`);
