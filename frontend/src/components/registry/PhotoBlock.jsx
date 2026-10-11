import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CameraCapture, cameraSupportError } from "@/components/CameraCapture";
import { cropTo34Jpeg, fileToImage } from "@/lib/image";
import { Camera, CheckCircle2, Loader2, Trash2, Upload, UserRound, XCircle } from "lucide-react";
import { toast } from "sonner";

export function PhotoBlock({ photo, onChange }) {
  const [cam, setCam] = useState(false);
  const [quality, setQuality] = useState(null);
  const [checking, setChecking] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    if (!photo || !photo.startsWith("data:")) { setQuality(null); return undefined; }
    let alive = true;
    setChecking(true);
    api.post("/registry/photo/check", { image: photo })
      .then(({ data }) => alive && setQuality(data))
      .catch(() => alive && setQuality(null))
      .finally(() => alive && setChecking(false));
    return () => { alive = false; };
  }, [photo]);

  const openCam = () => {
    const err = cameraSupportError();
    if (err) { console.log("[Camera]", err); toast.error(err); return; }
    setCam(true);
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!f.type.startsWith("image/")) { toast.error("Selecione um arquivo de imagem"); return; }
    try {
      const img = await fileToImage(f);
      onChange(cropTo34Jpeg(img, img.naturalWidth, img.naturalHeight));
    } catch { toast.error("Não foi possível ler a imagem"); }
  };

  return (
    <div className="flex flex-col gap-2" data-testid="photo-block">
      <div className="relative aspect-[3/4] w-full overflow-hidden rounded-lg border border-border bg-secondary/60">
        {photo ? <img src={photo} alt="Foto" className="h-full w-full object-cover" data-testid="photo-preview" /> : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <UserRound className="h-12 w-12" /><span className="text-xs">Foto 3x4</span>
          </div>
        )}
      </div>
      <input ref={fileRef} type="file" accept="image/*" capture="user" className="hidden" onChange={onFile} data-testid="photo-file-input" />
      <Button type="button" size="sm" variant="outline" onClick={openCam} data-testid="photo-webcam-button"><Camera className="mr-2 h-4 w-4" />Capturar webcam</Button>
      <Button type="button" size="sm" variant="outline" onClick={() => fileRef.current?.click()} data-testid="photo-upload-button"><Upload className="mr-2 h-4 w-4" />Enviar arquivo</Button>
      <Button type="button" size="sm" variant="ghost" disabled={!photo} onClick={() => onChange("")} className="text-red-400" data-testid="photo-remove-button"><Trash2 className="mr-2 h-4 w-4" />Remover</Button>
      <QualityNote checking={checking} quality={quality} />
      <CameraCapture open={cam} onClose={() => setCam(false)} onCapture={onChange} />
    </div>
  );
}

function QualityNote({ checking, quality }) {
  if (checking) return <p className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="photo-quality-checking"><Loader2 className="h-3 w-3 animate-spin" />Validando qualidade…</p>;
  if (!quality) return null;
  if (quality.ok) return <p className="flex items-start gap-1.5 text-xs text-emerald-400" data-testid="photo-quality-ok"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />Foto aprovada: 1 rosto, centralizado, nítido e iluminado.</p>;
  return (
    <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300" data-testid="photo-quality-fail">
      <p className="mb-1 flex items-center gap-1.5 font-medium"><XCircle className="h-3.5 w-3.5" />Foto reprovada para reconhecimento</p>
      <ul className="list-disc space-y-0.5 pl-4">{quality.issues.map((i) => <li key={i}>{i}</li>)}</ul>
    </div>
  );
}
