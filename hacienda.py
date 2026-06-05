"""
Módulo 4: Token OAuth + Envío a Hacienda CR v4.4
"""
import base64, requests, time, logging, os

log = logging.getLogger(__name__)

TOKEN_URL_PROD = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token"
TOKEN_URL_STAG = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"
API_URL_PROD   = "https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/"
API_URL_STAG   = "https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/"

_token_cache = {"token": None, "expira": 0, "refresh": None}

def obtener_token(usuario: str, password: str, produccion: bool = True) -> str:
    global _token_cache
    ahora = time.time()
    if _token_cache["token"] and ahora < _token_cache["expira"] - 60:
        return _token_cache["token"]
    
    url  = TOKEN_URL_PROD if produccion else TOKEN_URL_STAG
    data = {
        "client_id":     "api-prod" if produccion else "api-stag",
        "client_secret": "",
        "grant_type":    "password",
        "username":      usuario,
        "password":      password,
    }
    resp = requests.post(url, data=data, timeout=30)
    if not resp.ok:
        raise Exception(f"Error token Hacienda: {resp.status_code} {resp.text[:200]}")
    j = resp.json()
    _token_cache["token"]   = j["access_token"]
    _token_cache["refresh"] = j.get("refresh_token")
    _token_cache["expira"]  = ahora + j.get("expires_in", 300)
    log.info("✅ Token Hacienda OK, expira en %ds", j.get("expires_in", 300))
    return _token_cache["token"]

def enviar_comprobante(token: str, clave: str, fecha_emision: str,
                       emisor_tipo_id: str, emisor_num_id: str,
                       xml_firmado_bytes: bytes, produccion: bool = True) -> dict:
    url    = API_URL_PROD if produccion else API_URL_STAG
    xml_b64 = base64.b64encode(xml_firmado_bytes).decode("utf-8")
    payload = {
        "clave": clave,
        "fecha": fecha_emision,
        "emisor": {
            "tipoIdentificacion":  emisor_tipo_id,
            "numeroIdentificacion": emisor_num_id,
        },
        "comprobanteXml": xml_b64,
    }
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resultado = {
        "status": resp.status_code,
        "clave":  clave,
        "ok":     resp.status_code == 202,
    }
    if resp.text:
        try:    resultado["respuesta"] = resp.json()
        except: resultado["respuesta"] = resp.text[:300]
    if resp.status_code == 202:
        log.info("✅ Hacienda aceptó: %s", clave[:20])
    else:
        log.error("❌ Hacienda rechazó %s: %s %s", clave[:20], resp.status_code, resp.text[:200])
    return resultado

def consultar_comprobante(token: str, clave: str, produccion: bool = True) -> dict:
    url = (API_URL_PROD if produccion else API_URL_STAG) + clave
    resp = requests.get(url, headers={"Authorization": f"bearer {token}"}, timeout=30)
    return resp.json() if resp.ok else {"error": resp.status_code, "texto": resp.text[:200]}
