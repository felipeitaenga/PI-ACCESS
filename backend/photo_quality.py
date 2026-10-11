import base64
import io
import cv2
import numpy as np
from PIL import Image

CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _decode(data_url: str):
    b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
    raw = base64.b64decode(b64)
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    return img, len(raw)


def check_photo(data_url: str) -> dict:
    try:
        img, size = _decode(data_url)
    except Exception:
        img, size = None, 0
    if img is None:
        return {"ok": False, "issues": ["Imagem inválida ou corrompida"], "metrics": {}}
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    side = int(min(w, h) * 0.12)
    faces = CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(side, side))
    issues = []
    metrics = {"width": w, "height": h, "size_kb": round(size / 1024, 1), "faces": int(len(faces)),
               "brightness": round(float(gray.mean()), 1)}
    if len(faces) == 0:
        issues.append("Nenhum rosto detectado — olhe de frente para a câmera")
    elif len(faces) > 1:
        issues.append("Mais de um rosto detectado — apenas 1 pessoa na foto")
    else:
        x, y, fw, fh = [int(v) for v in faces[0]]
        roi = gray[y:y + fh, x:x + fw]
        cx, cy = (x + fw / 2) / w, (y + fh / 2) / h
        sharp = float(cv2.Laplacian(roi, cv2.CV_64F).var())
        face_b = float(roi.mean())
        metrics.update({"sharpness": round(sharp, 1), "face_brightness": round(face_b, 1),
                        "face_ratio": round(fw / w, 2), "center": [round(cx, 2), round(cy, 2)]})
        if abs(cx - 0.5) > 0.15 or abs(cy - 0.45) > 0.2:
            issues.append("Rosto fora do centro — centralize o rosto na guia oval")
        if fw / w < 0.25:
            issues.append("Rosto muito pequeno — aproxime-se da câmera")
        if sharp < 40:
            issues.append("Imagem desfocada — mantenha a cabeça parada")
        if face_b < 70:
            issues.append("Pouca iluminação no rosto — melhore a luz do ambiente")
        elif face_b > 215:
            issues.append("Rosto com excesso de luz — evite luz direta")
    return {"ok": not issues, "issues": issues, "metrics": metrics}


def make_thumb(photo: str) -> str:
    if not photo or not photo.startswith("data:"):
        return photo or ""
    try:
        b64 = photo.split(",", 1)[1]
        im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        im.thumbnail((96, 128))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=75)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""
