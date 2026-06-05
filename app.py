import os, sys, logging, base64
from datetime import datetime
from flask import Flask, request, jsonify, Response, send_file, make_response

# Agregar directorio actual al path para importar módulos propios
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clave         import generar_clave
from xml_generator import generar_xml
from firmador      import firmar
from hacienda      import obtener_token, enviar_comprobante

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gaucha-fe")

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
MH_USUARIO     = os.environ.get("MH_USUARIO",   "cpj-3-102-807442@prod.comprobanteselectronicos.go.cr")
MH_PASSWORD    = os.environ.get("MH_PASSWORD",  "D&^&cDVw6xzHQHIjP6Vc")
CERT_PIN       = os.environ.get("CERT_PIN",      "5561")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET","gaucha2026")
PRODUCCION     = os.environ.get("PRODUCCION",   "true").lower() == "true"

EMPRESA = {
    "nombre":      "Tres Bochas Sociedad De Responsabilidad Limitada",
    "tipo_id":     "02",
    "num_id":      "3102807442",
    "provincia":   "6", "canton": "001", "distrito": "001",
    "otras_senas": "Frente Antigua Discoteca Lora Amarilla, Santa Teresa",
    "email":       "gauchasantateresa@gmail.com",
    "telefono":    "60000000",
    "actividad":   "5610000",
}

TARJETA_KW = ["tarjeta","card","visa","mastercard","amex","credito","debito"]
_consecutivo = int(os.environ.get("CONSECUTIVO_INICIO", "1"))

def get_cert():
    rutas = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "certificado.p12"),
        "./certificado.p12",
        "/app/certificado.p12",
    ]
    for r in rutas:
        if os.path.exists(r):
            return r
    raise FileNotFoundError("No se encontró certificado.p12")

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

    # Parsear fecha
    try:
        if "T" in fecha_str:
            fecha = datetime.fromisoformat(fecha_str.replace("Z","").split("+")[0])
        else:
            fecha = datetime.strptime(fecha_str[:10], "%Y-%m-%d")
    except:
        fecha = datetime.now()

    # 1. Clave
    cl = generar_clave(EMPRESA["num_id"], _consecutivo, "02", "04", fecha)

    # 2. XML
    xml = generar_xml(
        clave=cl["clave"], consecutivo=cl["consecutivo"],
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
        cantidad=1, unidad_medida="Sp",
        precio_unitario=precio_sin_iva,
        cabys="6331000000000",
        porcentaje_iva=13.0,
        medio_pago=medio_pago,
    )

    # 3. Firmar
    xf = firmar(get_cert(), CERT_PIN, xml, "04")

    # 4. Token + Enviar
    token = obtener_token(MH_USUARIO, MH_PASSWORD, PRODUCCION)
    res   = enviar_comprobante(
        token=token,
        clave=cl["clave"],
        fecha_emision=fecha.strftime("%Y-%m-%dT%H:%M:%S-06:00"),
        emisor_tipo_id=EMPRESA["tipo_id"],
        emisor_num_id=EMPRESA["num_id"],
        xml_firmado_bytes=xf,
        produccion=PRODUCCION,
    )

    if res["ok"]:
        _consecutivo += 1
        res["consecutivo"] = cl["consecutivo"]
        res["clave"]       = cl["clave"]
        res["referencia"]  = referencia
        log.info("✅ Hacienda 202: %s | clave: %s...", referencia, cl["clave"][:20])
    else:
        log.error("❌ Error Hacienda: %s | %s", referencia, res.get("respuesta",""))

    return res

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "facturador": "Gaucha FE v4.4 — Directo a Hacienda CR",
        "consecutivo": _consecutivo,
        "produccion": PRODUCCION,
        "empresa": EMPRESA["nombre"],
    })

@app.route("/script")
def script():
    try:
        with open(os.path.join(os.path.dirname(__file__), "gaucha_tiquetes.js")) as f:
            content = f.read()
        return Response(content, mimetype="application/javascript",
                       headers={"Cache-Control": "no-cache"})
    except:
        return Response("// script not found", mimetype="application/javascript")

@app.route("/instalar")
def instalar():
    try:
        return send_file(os.path.join(os.path.dirname(__file__), "instalar.html"))
    except:
        return "not found", 404

@app.route("/webhook", methods=["POST","OPTIONS"])
def webhook():
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    if request.headers.get("X-Webhook-Secret","") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    d      = request.get_json(force=True, silent=True) or {}
    name   = d.get("name", "N/A")
    amount = float(d.get("amount_total", 0))
    date   = d.get("date_order", "")
    method = d.get("payment_method_name", "").lower()
    state  = d.get("state", "")

    log.info("Webhook: %s | ₡%.0f | método=%s | estado=%s", name, amount, method, state)

    if state not in ("done","invoiced","paid"):
        return jsonify({"status": "skipped", "razon": f"Estado {state}"})
    if not any(k in method for k in TARJETA_KW):
        return jsonify({"status": "skipped", "razon": "No es tarjeta"})
    if amount <= 0:
        return jsonify({"status": "skipped", "razon": "Monto inválido"})

    res = emitir(amount, date, name)

    if res["ok"]:
        return jsonify({"status": "ok", "orden": name,
                        "clave": res.get("clave",""),
                        "consecutivo": res.get("consecutivo","")})
    return jsonify({"status": "error",
                    "message": str(res.get("respuesta","Error Hacienda"))}), 500

@app.route("/tiquete", methods=["POST","OPTIONS"])
def tiquete():
    """Endpoint directo para emitir un tiquete."""
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    if request.headers.get("X-Webhook-Secret","") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    d     = request.get_json(force=True, silent=True) or {}
    monto = float(d.get("monto", 0))
    fecha = d.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    ref   = d.get("referencia", "SIN-REF")
    medio = d.get("medio_pago", "02")
    if monto <= 0:
        return jsonify({"error": "Monto inválido"}), 400
    res = emitir(monto, fecha, ref, medio)
    if res["ok"]:
        return jsonify({"status": "ok", **res})
    return jsonify({"status": "error",
                    "message": str(res.get("respuesta",""))}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
