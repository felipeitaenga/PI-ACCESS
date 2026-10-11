export const onlyDigits = (s = "") => String(s ?? "").replace(/\D/g, "");

export const maskCpf = (v) => {
  const d = onlyDigits(v).slice(0, 11);
  return d
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
};

export const validCpf = (v) => {
  const d = onlyDigits(v);
  if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false;
  for (const i of [9, 10]) {
    let s = 0;
    for (let k = 0; k < i; k++) s += Number(d[k]) * (i + 1 - k);
    if (((s * 10) % 11) % 10 !== Number(d[i])) return false;
  }
  return true;
};

export const maskPhone = (v) => {
  const d = onlyDigits(v).slice(0, 11);
  if (!d.length) return "";
  if (d.length <= 2) return `(${d}`;
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
};

export const maskCnpj = (v) => {
  const d = onlyDigits(v).slice(0, 14);
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
};

export const maskPlate = (v) => String(v || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);

export const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export const fromLocalInput = (v) => (v ? new Date(v).toISOString() : "");

export const nowLocal = (hours = 0) => toLocalInput(new Date(Date.now() + hours * 3600e3).toISOString());

export const fmtDateTime = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

export const daysUntil = (date) => {
  if (!date) return null;
  const t = new Date(new Date().toISOString().slice(0, 10));
  return Math.round((new Date(date.slice(0, 10)) - t) / 86400000);
};
