"""Catálogo de equipamentos: fabricante → modelo → driver e recursos.

Para incluir um modelo novo de uma marca que já tem driver, basta uma linha em MODELS.
status:
  homologado  testado em aparelho real
  em_teste    driver existe, ainda validando em campo
  em_breve    aparece na lista, mas não pode ser cadastrado (driver não implementado)
family: liga o modelo ao driver/recursos de equipment.MODEL_TYPES (simulado, beward_facial, ...).
"""

MANUFACTURERS = [
    {"id": "beward", "name": "Beward"},
    {"id": "intelbras", "name": "Intelbras"},
    {"id": "controlid", "name": "Control iD"},
    {"id": "hikvision", "name": "Hikvision"},
    {"id": "ct", "name": "Controladoras CT"},
    {"id": "simulado", "name": "Simulado"},
]

_FACE = {"face": True, "card": False, "finger": False, "qrcode": False}


def _m(id, manufacturer, name, family, status, *, protocol, features=None, online=False, screen_msg=False,
       min_fw="", max_points=1, notes=""):
    return {"id": id, "manufacturer": manufacturer, "name": name, "family": family, "status": status,
            "protocol": protocol, "features": {**_FACE, **(features or {})}, "online_mode": online,
            "screen_message": screen_msg, "min_firmware": min_fw, "max_points": max_points, "notes": notes}


_INTEL = "HTTP (CGI) · Digest"
_INTEL_NOTE = "Modo Online: o servidor decide e mostra mensagem na tela. Sem resposta do servidor o facial libera todos os cadastrados."

MODELS = [
    _m("simulado", "simulado", "Simulado (demonstração)", "simulado", "homologado", protocol="—", online=True, max_points=8,
       features={"card": True, "qrcode": True}),
    _m("beward_face", "beward", "Facial (Face Server)", "beward_facial", "homologado", protocol="MQTT ou HTTP local",
       online=True, features={"card": True},
       notes="Servidor decide com o facial em “Verificação local Aberta à distância” (sem mensagem na tela; só áudio)."),
    # Intelbras — linha Bio-T (mesma API CGI; firmware mínimo do Modo Online conforme documentação Intelbras)
    *[_m(f"intelbras_{k}", "intelbras", n, "intelbras_facial", "em_breve", protocol=_INTEL, online=bool(fw),
         screen_msg=bool(fw), min_fw=fw, features=f, notes=_INTEL_NOTE if fw else "Sem Modo Online: o facial decide sozinho.")
      for k, n, fw, f in [
          ("ss3530mf", "SS 3530 MF FACE", "20240601", {"card": True}),
          ("ss3530mfw", "SS 3530 MF FACE W", "20240601", {"card": True}),
          ("ss3532mf", "SS 3532 MF", "", {"card": True}),
          ("ss3532mfw", "SS 3532 MF W", "20231018", {"card": True}),
          ("ss3540mf", "SS 3540 MF FACE", "231129", {"card": True}),
          ("ss3540mfbio", "SS 3540 MF FACE BIO", "231129", {"card": True, "finger": True}),
          ("ss3542mfw", "SS 3542 MF W", "20231018", {"card": True}),
          ("ss5530", "SS 5530 MF FACE", "220708", {"card": True}),
          ("ss5530lite", "SS 5530 MF FACE LITE", "230307", {"card": True}),
          ("ss5531mfw", "SS 5531 MF W", "20231018", {"card": True}),
          ("ss5532mfw", "SS 5532 MF W", "20231018", {"card": True}),
          ("ss5541mfw", "SS 5541 MF W", "20231018", {"card": True}),
          ("ss5542mfw", "SS 5542 MF W", "20231018", {"card": True}),
          ("ss3430bio", "SS 3430 BIO", "20240315", {"face": False, "finger": True}),
          ("ss3430mfbio", "SS 3430 MF BIO", "20240315", {"face": False, "card": True, "finger": True}),
      ]],
    _m("controlid_idface", "controlid", "iDFace", "controlid_facial", "em_breve", protocol="HTTP (Access API) · Push",
       online=True, screen_msg=True, features={"card": True, "qrcode": True}),
    _m("controlid_idfacemax", "controlid", "iDFace Max", "controlid_facial", "em_breve", protocol="HTTP (Access API) · Push",
       online=True, screen_msg=True, features={"card": True, "qrcode": True}),
    _m("hikvision_dsk1t", "hikvision", "Facial série DS-K1T", "hikvision_facial", "em_breve", protocol="HTTP (ISAPI) · Digest",
       features={"card": True}),
    _m("ct300_2l", "ct", "CT300-2L", "ct300_2l", "em_breve", protocol="—", max_points=2,
       features={"face": False, "card": True}),
]

BY_ID = {m["id"]: m for m in MODELS}
# cadastro antigo (só model_type) → modelo do catálogo
DEFAULT_BY_FAMILY = {"simulado": "simulado", "beward_facial": "beward_face", "intelbras_facial": "intelbras_ss3532mfw",
                     "controlid_facial": "controlid_idface", "hikvision_facial": "hikvision_dsk1t", "ct300_2l": "ct300_2l"}
MANUFACTURER_NAME = {m["id"]: m["name"] for m in MANUFACTURERS}


def resolve(doc):
    """Modelo do catálogo de um cadastro de controladora (novo ou antigo)."""
    return BY_ID.get(doc.get("catalog_model") or "") or BY_ID.get(DEFAULT_BY_FAMILY.get(doc.get("model_type") or "", ""))


def catalog():
    return {"manufacturers": MANUFACTURERS, "models": MODELS}
