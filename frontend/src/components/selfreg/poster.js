import { jsPDF } from "jspdf";
import { toast } from "sonner";

const loadLogo = () => new Promise((resolve) => {
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext("2d").drawImage(img, 0, 0);
    resolve({ data: c.toDataURL("image/png"), w: img.naturalWidth, h: img.naturalHeight });
  };
  img.onerror = () => resolve(null);
  img.src = "/brand/pilares-logo.webp";
});

const STEPS = ["Aponte a câmera do celular para o QR Code", "Preencha seus dados e tire uma selfie", "Aguarde a aprovação e entre pelo leitor facial"];

// Cartaz A4 com logo, nome da empresa, QR e 3 passos
export async function downloadPoster(name, link, qr) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = 210;
  doc.setFillColor(239, 125, 37); doc.rect(0, 0, W, 8, "F");
  const logo = await loadLogo();
  if (logo) { const h = 22, w = (logo.w / logo.h) * h; doc.addImage(logo.data, "PNG", (W - w) / 2, 16, w, h); }
  doc.setTextColor(15, 23, 42); doc.setFont("helvetica", "bold"); doc.setFontSize(30);
  doc.text("Visitante? Faça seu cadastro", W / 2, 56, { align: "center" });
  if (name) { doc.setFontSize(20); doc.setFont("helvetica", "normal"); doc.setTextColor(51, 65, 85); doc.text(name, W / 2, 67, { align: "center", maxWidth: 180 }); }
  doc.addImage(qr, "PNG", (W - 110) / 2, 76, 110, 110);
  doc.setFontSize(16); doc.setTextColor(15, 23, 42);
  STEPS.forEach((s, i) => {
    const y = 204 + i * 16;
    doc.setFillColor(239, 125, 37); doc.circle(32, y - 2, 5, "F");
    doc.setTextColor(255, 255, 255); doc.setFont("helvetica", "bold"); doc.text(String(i + 1), 32, y, { align: "center" });
    doc.setTextColor(15, 23, 42); doc.setFont("helvetica", "normal"); doc.text(s, 42, y);
  });
  doc.setFontSize(9); doc.setTextColor(100, 116, 139); doc.text(link, W / 2, 282, { align: "center", maxWidth: 190 });
  doc.save(`cartaz-autocadastro${name ? `-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` : ""}.pdf`);
}

export async function shareLink(name, link) {
  const data = { title: "Cadastro de visitante", text: `Faça seu cadastro de visitante${name ? ` (${name})` : ""}:`, url: link };
  if (navigator.share) {
    try { await navigator.share(data); return; } catch (e) { if (e?.name === "AbortError") return; }
  }
  navigator.clipboard?.writeText(link).then(() => toast.success("Link copiado"), () => toast.error("Não foi possível copiar"));
}
