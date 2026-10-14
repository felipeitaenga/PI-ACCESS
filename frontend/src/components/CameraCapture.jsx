import { useCallback, useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertTriangle, Camera, Check, Loader2, RotateCcw } from "lucide-react";
import { cropTo34Jpeg, dataUrlBytes } from "@/lib/image";

const LS_KEY = "nx_camera_device";
const log = (...a) => console.log("[Camera]", ...a);
const DENIED = "Permissão da câmera negada. Clique no cadeado ao lado do endereço do site, em \"Câmera\" escolha \"Permitir\" e tente novamente.";
const BUSY = "A câmera está em uso por outro programa (Teams, Zoom, outro navegador). Feche-o e tente novamente.";
const NOTFOUND = "Nenhuma câmera encontrada. Conecte uma webcam ou use \"Enviar arquivo\".";
const INSECURE = "A câmera só funciona em HTTPS ou localhost";
const ERRORS = {
  NotAllowedError: DENIED, PermissionDeniedError: DENIED,
  NotFoundError: NOTFOUND, DevicesNotFoundError: NOTFOUND,
  NotReadableError: BUSY, TrackStartError: BUSY,
  SecurityError: `${INSECURE} (página não segura ou bloqueada pela política de permissões).`,
  AbortError: "A abertura da câmera foi interrompida. Tente novamente.",
};
const friendly = (e) => ERRORS[e?.name] || `Não foi possível abrir a câmera (${e?.name || "erro"}).`;

export function cameraSupportError() {
  if (!window.isSecureContext) return INSECURE;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return "Este navegador não suporta acesso à câmera";
  return null;
}

async function openStream(deviceId) {
  const base = deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "user" };
  try {
    log("getUserMedia", deviceId || "facingMode=user");
    return await navigator.mediaDevices.getUserMedia({
      video: { ...base, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
    });
  } catch (e) {
    log("erro", e.name, e.message);
    if (e.name !== "OverconstrainedError" && e.name !== "ConstraintNotSatisfiedError") throw e;
    log("nova tentativa sem width/height");
    return navigator.mediaDevices.getUserMedia({ video: deviceId ? { deviceId } : { facingMode: "user" }, audio: false });
  }
}

export function CameraCapture({ open, onClose, onCapture }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState(() => localStorage.getItem(LS_KEY) || "");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [shot, setShot] = useState(null);

  const stop = useCallback(() => {
    const s = streamRef.current;
    if (s) { s.getTracks().forEach((t) => t.stop()); log("tracks paradas"); }
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const start = useCallback(async (id) => {
    const unsupported = cameraSupportError();
    if (unsupported) { log(unsupported); setError(unsupported); setStatus("error"); return; }
    stop(); setShot(null); setError(""); setStatus("starting");
    let stream;
    try { stream = await openStream(id); } catch (e) { log("falha", e.name); setError(friendly(e)); setStatus("error"); return; }
    streamRef.current = stream;
    if (!videoRef.current) await new Promise((r) => requestAnimationFrame(r));
    const v = videoRef.current;
    if (!v) { stop(); return; }
    v.srcObject = stream;
    await new Promise((res) => { if (v.readyState >= 1) res(); else v.onloadedmetadata = () => res(); });
    try { await v.play(); } catch (e) { log("play falhou", e.name); }
    const track = stream.getVideoTracks()[0];
    const settings = track?.getSettings?.() || {};
    log("stream ativo", track?.label, `${v.videoWidth}x${v.videoHeight}`);
    if (settings.deviceId) { localStorage.setItem(LS_KEY, settings.deviceId); setDeviceId(settings.deviceId); }
    try {
      const list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
      log("câmeras disponíveis", list.length); setDevices(list);
    } catch (e) { log("enumerateDevices falhou", e.name); }
    setStatus("live");
  }, [stop]);

  useEffect(() => {
    if (!open) return undefined;
    start(localStorage.getItem(LS_KEY) || "");
    return () => stop();
  }, [open, start, stop]);

  useEffect(() => {
    const h = () => stop();
    window.addEventListener("pagehide", h);
    return () => { window.removeEventListener("pagehide", h); stop(); };
  }, [stop]);

  const capture = () => {
    const v = videoRef.current;
    if (!v?.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    const url = cropTo34Jpeg(c, c.width, c.height);
    log("foto capturada", `${c.width}x${c.height}`, `${Math.round(dataUrlBytes(url) / 1024)} KB`);
    setShot(url); setStatus("captured"); stop();
  };

  const close = () => { stop(); onClose(); };
  const changeDevice = (id) => { setDeviceId(id); localStorage.setItem(LS_KEY, id); start(id); };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) close(); }}>
      <DialogContent className="max-h-[100dvh] max-w-xl overflow-y-auto p-4 sm:p-6" data-testid="camera-modal">
        <DialogHeader>
          <DialogTitle>Tirar foto</DialogTitle>
          <DialogDescription>Encaixe o rosto inteiro dentro do oval, de frente, sem boné ou óculos escuros, em local iluminado.</DialogDescription>
        </DialogHeader>
        {devices.length > 1 && status !== "captured" && (
          <Select value={deviceId} onValueChange={changeDevice}>
            <SelectTrigger data-testid="camera-device-select"><SelectValue placeholder="Selecione a câmera" /></SelectTrigger>
            <SelectContent>
              {devices.map((d, i) => <SelectItem key={d.deviceId || i} value={d.deviceId || `cam-${i}`}>{d.label || `Câmera ${i + 1}`}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <CameraStage videoRef={videoRef} status={status} error={error} shot={shot} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={close} data-testid="camera-cancel-button">Cancelar</Button>
          {status === "error" && <Button variant="outline" onClick={() => start(deviceId)} data-testid="camera-retry-button"><RotateCcw className="mr-2 h-4 w-4" />Tentar novamente</Button>}
          {status === "captured" ? (
            <>
              <Button variant="outline" onClick={() => start(deviceId)} data-testid="camera-retake-button"><RotateCcw className="mr-2 h-4 w-4" />Tirar outra</Button>
              <Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={() => { onCapture(shot); close(); }} data-testid="camera-use-button"><Check className="mr-2 h-4 w-4" />Usar esta foto</Button>
            </>
          ) : (
            <Button className="bg-sky-500 text-slate-950 hover:bg-sky-400" disabled={status !== "live"} onClick={capture} data-testid="camera-capture-button"><Camera className="mr-2 h-4 w-4" />Capturar</Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CameraStage({ videoRef, status, error, shot }) {
  return (
    <div className="relative mx-auto aspect-[3/4] w-full max-w-[calc(68dvh*0.75)] overflow-hidden rounded-lg bg-black" data-testid="camera-stage">
      <video ref={videoRef} autoPlay playsInline muted className={`h-full w-full object-cover -scale-x-100 ${status === "captured" ? "invisible" : ""}`} data-testid="camera-video" />
      {status === "live" && (
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/2 top-[46%] h-[74%] w-[70%] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border-[3px] border-dashed border-sky-400 shadow-[0_0_0_9999px_rgba(2,6,23,0.35)]" data-testid="camera-oval" />
        </div>
      )}
      {status === "captured" && shot && (
        <img src={shot} alt="Foto capturada" className="absolute inset-0 h-full w-full object-contain" data-testid="camera-preview" />
      )}
      {status === "starting" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-slate-300">
          <Loader2 className="h-6 w-6 animate-spin text-sky-400" /> Abrindo câmera… autorize o acesso se o navegador pedir.
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center" data-testid="camera-error">
          <AlertTriangle className="h-8 w-8 text-amber-400" />
          <p className="max-w-md text-sm text-slate-200">{error}</p>
        </div>
      )}
    </div>
  );
}
