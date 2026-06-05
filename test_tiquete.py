#!/usr/bin/env python3
import sys
sys.path.insert(0, ".")
from datetime import datetime
from clave import generar_clave
from xml_generator import generar_xml
from firmador import firmar
from hacienda import obtener_token, enviar_comprobante

print("=== TEST TIQUETE ELECTRONICO v4.4 ===")

# 1. Generar clave
cl = generar_clave("3102807442", 1, "02", "04", datetime(2026, 6, 1, 12, 0, 0))
print(f"✅ Clave ({cl["longitud"]} digitos): {cl["clave"][:25]}...")

# 2. Generar XML  
precio_sin_iva = round(23320 / 1.13, 5)
xml = generar_xml(
    clave=cl["clave"], consecutivo=cl["consecutivo"],
    fecha_emision=datetime(2026, 6, 1, 12, 0, 0),
    emisor_nombre="Tres Bochas Sociedad De Responsabilidad Limitada",
    emisor_tipo_id="02", emisor_num_id="3102807442",
    emisor_provincia="6", emisor_canton="01", emisor_distrito="01",
    emisor_otras_senas="Frente Antigua Discoteca Lora Amarilla, Santa Teresa",
    emisor_email="gauchasantateresa@gmail.com",
    emisor_telefono="60000000",
    actividad_economica="5610000",
    descripcion="Servicio de Restaurante",
    cantidad=1, unidad_medida="Sp",
    precio_unitario=precio_sin_iva,
    cabys="6331000000000",
    porcentaje_iva=13.0,
    medio_pago="02"
)
print(f"✅ XML generado: {len(xml)} bytes")

# 3. Firmar
xf = firmar("./certificado.p12", "5561", xml, "04")
print(f"✅ XML firmado: {len(xf)} bytes")

# 4. Token Hacienda
tok = obtener_token(
    "cpj-3-102-807442@prod.comprobanteselectronicos.go.cr",
    "D&^&cDVw6xzHQHIjP6Vc", True
)
print(f"✅ Token Hacienda: {tok[:30]}...")

# 5. Enviar a Hacienda
res = enviar_comprobante(
    token=tok,
    clave=cl["clave"],
    fecha_emision="2026-06-01T12:00:00-06:00",
    emisor_tipo_id="02",
    emisor_num_id="3102807442",
    xml_firmado_bytes=xf,
    produccion=True
)
print(f"RESULTADO HACIENDA: {res}")
if res["ok"]:
    print("🎉🎉🎉 TIQUETE ENVIADO A HACIENDA EXITOSAMENTE!")
else:
    print("❌ Error:", res.get("respuesta", ""))
