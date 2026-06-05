#!/usr/bin/env python3
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, ".")
from datetime import datetime
from clave import generar_clave
from xml_generator import generar_xml
from firmador import firmar
from hacienda import obtener_token, enviar_comprobante

print("=== TEST TIQUETE ELECTRONICO v4.4 ===")

cl = generar_clave("3102807442", 1, "02", "04", datetime.now())
print(f"✅Clave (50 digitos): {cl['clave'][:25]}...")

precio_sin_iva = round(23320 / 1.13, 5)
xml = generar_xml(
    clave=cl["clave"], consecutivo=cl["consecutivo"],
    fecha_emision=datetime.now(),
    emisor_nombre="Tres Bochas Sociedad De Responsabilidad Limitada",
    emisor_tipo_id="02", emisor_num_id="3102807442",
    emisor_provincia="6", emisor_canton="01", emisor_distrito="01",
    emisor_otras_senas="Frente Antigua Discoteca Lora Amarilla, Santa Teresa",
    emisor_email="gauchasantateresa@gmail.com",
    emisor_telefono="60000000",
    actividad_economica="561000",
    descripcion="Servicio de Restaurante",
    cantidad=1, unidad_medida="Sp",
    precio_unitario=precio_sin_iva,
    cabys="6331000000000",
    porcentaje_iva=13.0,
    medio_pago="02"
)
print(f"✅XML generado: {len(xml)} bytes")

xf = firmar("./certificado.p12", "5561", xml, "04")
print(f"✅XML firmado: {len(xf)} bytes")

tok = obtener_token(
    "cpj-3-102-807442@prod.comprobanteselectronicos.go.cr",
    "D&^&cDVw6xzHQHIjP6Vc", True
)
print(f"✅Token Hacienda: {tok[:30]}...")

res = enviar_comprobante(
    token=tok,
    clave=cl["clave"],
    fecha_emision=datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00"),
    emisor_tipo_id="02",
    emisor_num_id="3102807442",
    xml_firmado_bytes=xf,
    produccion=True
)
print(f"RESULTADO HACIENDA: {res}")
if res["ok"]:
    print("🎉🎉🎉 TIQUETE ENVIADO A HACIENDA EXITOSAMENTE!")
    print(f"CLAVE: {cl['clave']}")
else:
    print("❌ Error:", res.get("respuesta", ""))
