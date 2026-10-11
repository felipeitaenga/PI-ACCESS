export const dataUrlBytes = (u) => Math.round(((u?.length || 0) - (u?.indexOf(",") ?? 0) - 1) * 0.75);

// Recorta centralizado em 3x4, máx. 1080p, JPEG 0.85, limitado a maxBytes.
export function cropTo34Jpeg(source, sw, sh, maxBytes = 200 * 1024) {
  let cw = sw;
  let ch = Math.round((sw * 4) / 3);
  if (ch > sh) {
    ch = sh;
    cw = Math.round((sh * 3) / 4);
  }
  const sx = Math.round((sw - cw) / 2);
  const sy = Math.round((sh - ch) / 2);
  let scale = Math.min(1, 1080 / ch);
  let q = 0.85;
  let out = "";
  for (let i = 0; i < 14; i++) {
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(cw * scale));
    c.height = Math.max(1, Math.round(ch * scale));
    c.getContext("2d").drawImage(source, sx, sy, cw, ch, 0, 0, c.width, c.height);
    out = c.toDataURL("image/jpeg", q);
    if (dataUrlBytes(out) <= maxBytes) break;
    if (q > 0.6) q -= 0.1;
    else scale *= 0.8;
  }
  return out;
}

export function fileToImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Imagem inválida")); };
    img.src = url;
  });
}

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
