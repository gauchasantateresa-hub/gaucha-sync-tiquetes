"""
Módulo 4: Token OAuth + Envío a Hacienda CR
"""
import base64
import requests
import time
import logging

log = logging.getLogger(__name__)

TOKEN_URL_PROD  = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token"
TOKEN_URL_STAG  = "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token"
API_URL_PROD    = "https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/"
API_URL_STAG    = "https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/"

_token_cache = {"token": None, "expira": 0, "refresh": None}


def obtener_token(usuario: str, password: str, produccion: bool = True) -> str:
    """Obtiene token OAuth de Hacienda, con caché automático."""
    global _token_cache

    ahora = time.time()

    # Si el token actual aún es válido (con 60s de margen)
    if _token_cache["token"] and ahora < _token_cache["expira"] - 60:
        return _token_cache["token"]

    # Intentar refresh si hay refresh_token
    if _token_cache["refresh"] and ahora < _token_cache["expira"]:
        try:
            token = _refresh_token(_token_cache["refresh"], produccion)
            if token:
                return token
        except:
            pass

    # Login fresco
    url = TOKEN_URL_PROD if produccion else TOKEN_URL_STAG
    data = {
        "client_id":  "api-prod" if produccion else "api-stag",
        "client_secret": "",
        "grant_type": "password",
        "username":   usuario,
        "password":   password,
    }

    resp = requests.post(url, data=data, timeout=30)
    resp.raise_for_status()
    j = resp.json()

    _token_cache["token"]   = j["access_token"]
    _token_cache["refresh"] = j.get("refresh_token")
    _token_cache["expira"]  = ahora + j.get("expires_in", 300)

    log.info("✅ Token Hacienda obtenido, expira en %ds", j.get("expires_in", 300))
    return _token_cache["token"]


def _refresh_token(refresh_tok: str, produccion: bool) -> str:
    url = TOKEN_URL_PROD if produccion else TOKEN_URL_STAG
    data = {
        "client_id":     "api-prod" if produccion else "api-stag",
        "client_secret": "",
        "grant_type":    "refresh_token",
        "refresh_token": refresh_tok,
    }
    resp = requests.post(url, data=data, timeout=30)
    if resp.ok:
        j = resp.json()
        _token_cache["token"]   = j["access_token"]
        _token_cache["expira"]  = time.time() + j.get("expires_in", 300)
        _token_cache["refresh"] = j.get("refresh_token", refresh_tok)
        return _token_cache["token"]
    return None


def enviar_comprobante(
    token: str,
    clave: str,
    fecha_emision: str,          # "2026-06-01T12:00:00-06:00"
    emisor_tipo_id: str,         # "02"
    emisor_num_id: str,          # "3102807442"
    xml_firmado_bytes: bytes,
    produccion: bool = True,
) -> dict:
    """
    Envía el XML firmado a la API de Hacienda.
    
    Returns: dict con {"status": 202, "mensaje": "..."}
    202 = aceptado para proceso
    400 = error de validación
    401 = token inválido
    """
    url = API_URL_PROD if produccion else API_URL_STAG

    xml_b64 = base64.b64encode(xml_firmado_bytes).decode("utf-8")

    payload = {
        "clave":   clave,
        "fecha":   fecha_emision,
        "emisor": {
            "tipoIdentificacion":  emisor_tipo_id,
            "numeroIdentificacion": emisor_num_id,
        },
        "comprobanteXml": xml_b64,
    }

    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type":  "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    resultado = {
        "status":  resp.status_code,
        "clave":   clave,
        "ok":      resp.status_code == 202,
    }

    if resp.text:
        try:
            resultado["respuesta"] = resp.json()
        except:
            resultado["respuesta"] = resp.text[:300]

    if resp.status_code == 202:
        log.info("✅ Hacienda aceptó: %s", clave)
    else:
        log.error("❌ Hacienda rechazó %s: %s %s", clave, resp.status_code, resp.text[:200])

    return resultado


def consultar_comprobante(token: str, clave: str, produccion: bool = True) -> dict:
    """Consulta el estado de un comprobante ya enviado."""
    url = (API_URL_PROD if produccion else API_URL_STAG) + clave
    headers = {"Authorization": f"bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.ok:
        return resp.json()
    return {"error": resp.status_code, "texto": resp.text[:200]}


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    
    USUARIO  = "cpj-3-102-807442@prod.comprobanteselectronicos.go.cr"
    PASSWORD = "D&^&cDVw6xzHQHIjP6Vc"
    
    print("🔐 Obteniendo token de Hacienda...")
    try:
        token = obtener_token(USUARIO, PASSWORD, produccion=True)
        print(f"✅ Token OK: {token[:40]}...")
    except Exception as e:
        print(f"❌ Error obteniendo token: {e}")
