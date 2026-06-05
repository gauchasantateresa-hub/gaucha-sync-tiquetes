"""
API Flask — Facturador Electrónico CR v4.4
Tres Bochas SRL / Gaucha Sur
"""
import base64
import logging
import os
import sys
import tempfile
import requests
from datetime import datetime
from flask import Flask, request, jsonify, Response, make_response

sys.path.insert(0, os.path.dirname(__file__))
from clave         import generar_clave
from xml_generator import generar_xml
from firmador      import firmar
from hacienda      import obtener_token, enviar_comprobante

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gaucha-fe")

app = Flask(__name__)

# ── Config desde variables de entorno ────────────────────────────────────────
MH_USUARIO   = os.environ.get("MH_USUARIO",   "cpj-3-102-807442@prod.comprobanteselectronicos.go.cr")
MH_PASSWORD  = os.environ.get("MH_PASSWORD",  "D&^&cDVw6xzHQHIjP6Vc")
CERT_PIN     = os.environ.get("CERT_PIN",     "5561")
CERT_B64     = os.environ.get("CERT_B64",     "")   # certificado en base64
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "gaucha2026")
PRODUCCION   = os.environ.get("PRODUCCION",   "true").lower() == "true"
CONSECUTIVO  = int(os.environ.get("CONSECUTIVO_INICIO", "1"))

EMPRESA = {
    "nombre":      "Tres Bochas Sociedad De Responsabilidad Limitada",
    "tipo_id":     "02",
    "num_id":      "3102807442",
    "provincia":   "6", "canton": "01", "distrito": "01",
    "otras_senas": "Frente Antigua Discoteca Lora Amarilla, Santa Teresa",
    "email":       "gauchasantateresa@gmail.com",
    "telefono":    "60000000",
    "actividad":   "5610000",
}

TARJETA_KW = ["tarjeta","card","visa","mastercard","amex","credito","debito"]
_consecutivo = CONSECUTIVO
_cert_path   = None


def get_cert_path():
    """Obtiene la ruta del certificado (lo descomprime de base64 si es necesario)."""
    global _cert_path
    if _cert_path and os.path.exists(_cert_path):
        return _cert_path
    if CERT_B64:
        tmp = tempfile.NamedTemporaryFile(suffix=".p12", delete=False)
        tmp.write(base64.b64decode(CERT_B64))
        tmp.close()
        _cert_path = tmp.name
        return _cert_path
    # Buscar en rutas conocidas
    for ruta in ["/app/certificado.p12", "./certificado.p12",
                 "/mnt/user-data/uploads/certificado1__1_.p12"]:
        if os.path.exists(ruta):
            _cert_path = ruta
            return ruta
    raise FileNotFoundError("No se encontró el certificado .p12")


def cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Webhook-Secret"
    return resp

@app.after_request
def after(r): return cors(r)


def emitir(monto_con_iva: float, fecha_str: str, referencia: str,
           medio_pago: str = "02") -> dict:
    global _consecutivo

    precio_sin_iva = round(monto_con_iva / 1.13, 5)
    fecha = datetime.fromisoformat(fecha_str.replace("Z", "+00:00")) \
            if "T" in fecha_str else datetime.strptime(fecha_str[:10], "%Y-%m-%d")

    datos_clave = generar_clave(
        cedula=EMPRESA["num_id"],
        consecutivo_num=_consecutivo,
        tipo_cedula="02",
        tipo_doc="04",
        fecha=fecha,
    )

    xml_bytes = generar_xml(
        clave=datos_clave["clave"],
        consecutivo=datos_clave["consecutivo"],
        fecha_emision=fecha,
        emisor_nombre=EMPRESA["nombre"],
        emisor_tipo_id=EMPRESA["tipo_id"],
        emisor_num_id=EMPRESA["num_id"],
        emisor_provincia=EMPRESA["provincia"],
        emisor_canton=EMPRESA["canton"],
        emisor_distrito=EMPRESA["distrito"],
        emisor_otras_senas=EMPRESA["otras_senas"],
        emisor_email=EMPRESA["email"],
        emisor_telefono=EMPRESA["telefono"],
        actividad_economica=EMPRESA["actividad"],
        descripcion="Servicio de Restaurante",
        cantidad=1,
        unidad_medida="Sp",
        precio_unitario=precio_sin_iva,
        cabys="6331000000000",
        porcentaje_iva=13.0,
        medio_pago=medio_pago,
    )

    xml_firmado = firmar(get_cert_path(), CERT_PIN, xml_bytes, "04")

    token = obtener_token(MH_USUARIO, MH_PASSWORD, PRODUCCION)

    resultado = enviar_comprobante(
        token=token,
        clave=datos_clave["clave"],
        fecha_emision=fecha.strftime("%Y-%m-%dT%H:%M:%S-06:00"),
        emisor_tipo_id=EMPRESA["tipo_id"],
        emisor_num_id=EMPRESA["num_id"],
        xml_firmado_bytes=xml_firmado,
        produccion=PRODUCCION,
    )

    if resultado["ok"]:
        _consecutivo += 1
        resultado["consecutivo"] = datos_clave["consecutivo"]
        resultado["clave"] = datos_clave["clave"]

    return resultado


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/")
def health():
    return jsonify({
        "status":       "ok",
        "version":      "1.0.0",
        "facturador":   "Gaucha Sur FE v4.4",
        "consecutivo":  _consecutivo,
        "produccion":   PRODUCCION,
    })

@app.route("/tiquete", methods=["POST", "OPTIONS"])
def tiquete():
    """Emite un tiquete directamente."""
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    if request.headers.get("X-Webhook-Secret", "") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    d = request.get_json(force=True, silent=True) or {}
    monto    = float(d.get("monto", 0))
    fecha    = d.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    ref      = d.get("referencia", "SIN-REF")
    medio    = d.get("medio_pago", "02")

    if monto <= 0:
        return jsonify({"error": "Monto inválido"}), 400

    log.info("🧾 Tiquete: %s ₡%.0f", ref, monto)
    resultado = emitir(monto, fecha, ref, medio)

    if resultado["ok"]:
        return jsonify({"status": "ok", **resultado})
    return jsonify({"status": "error", "mensaje": str(resultado.get("respuesta", "Error"))}), 500


@app.route("/webhook", methods=["POST", "OPTIONS"])
def webhook():
    """Webhook compatible con el panel de Odoo."""
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    if request.headers.get("X-Webhook-Secret", "") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    d = request.get_json(force=True, silent=True) or {}
    name   = d.get("name", "N/A")
    amount = float(d.get("amount_total", 0))
    date   = d.get("date_order", "")
    method = d.get("payment_method_name", "").lower()
    state  = d.get("state", "")

    log.info("Webhook: %s ₡%.0f método=%s estado=%s", name, amount, method, state)

    if state not in ("done", "invoiced", "paid"):
        return jsonify({"status": "skipped", "razon": f"Estado {state}"})
    if not any(k in method for k in TARJETA_KW):
        return jsonify({"status": "skipped", "razon": "No es tarjeta"})
    if amount <= 0:
        return jsonify({"status": "skipped", "razon": "Monto inválido"})

    resultado = emitir(amount, date, name)
    if resultado["ok"]:
        log.info("✅ OK: %s clave=%s", name, resultado.get("clave", "")[:20])
        return jsonify({"status": "ok", "orden": name, **resultado})

    log.error("❌ Error: %s - %s", name, resultado.get("respuesta", ""))
    return jsonify({"status": "error", "mensaje": str(resultado.get("respuesta", ""))}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
