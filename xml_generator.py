"""
Módulo 2: Generador de XML v4.4 para Tiquete Electrónico (tipo 04)
Hacienda CR - Consumidor Final (sin receptor)
"""
from datetime import datetime
from lxml import etree

NS = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico "
    "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico.xsd"
)

def generar_xml_tiquete(
    clave: str,
    consecutivo: str,
    fecha_emision: datetime,
    # Emisor
    emisor_nombre: str,
    emisor_tipo_id: str,   # "02" = jurídica
    emisor_num_id: str,    # cédula sin guiones
    emisor_provincia: str,
    emisor_canton: str,
    emisor_distrito: str,
    emisor_otras_senas: str,
    emisor_email: str,
    emisor_telefono: str,
    actividad_economica: str,
    # Línea de detalle
    descripcion: str,
    cantidad: float,
    unidad_medida: str,    # "Sp" = servicios profesionales
    precio_unitario: float,  # sin IVA
    cabys: str,
    porcentaje_iva: float,  # 13.0
    # Pago
    medio_pago: str = "02",  # 02 = tarjeta
    condicion_venta: str = "01",  # 01 = contado
    moneda: str = "CRC",
    proveedor_sistemas: str = "GauchaSur-FE v1.0",
) -> bytes:
    """
    Genera el XML de tiquete electrónico v4.4 sin firma.
    Retorna bytes UTF-8.
    """
    # ── Cálculos ─────────────────────────────────────────────────────────────
    monto_total_linea = round(cantidad * precio_unitario, 5)
    monto_iva = round(monto_total_linea * porcentaje_iva / 100, 5)
    subtotal = monto_total_linea
    monto_total_linea_con_iva = round(subtotal + monto_iva, 5)

    total_serv_gravados = round(monto_total_linea, 5)
    total_gravados = total_serv_gravados
    total_ventas = total_serv_gravados
    total_ventas_neta = total_serv_gravados
    total_impuestos = monto_iva
    total_comprobante = round(monto_total_linea_con_iva, 5)

    # ── Namespace ─────────────────────────────────────────────────────────────
    root = etree.Element(
        "TiqueteElectronico",
        attrib={
            "xmlns": NS,
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": SCHEMA_LOCATION,
        }
    )

    def sub(parent, tag, text=None):
        el = etree.SubElement(parent, tag)
        if text is not None:
            el.text = str(text)
        return el

    # ── Encabezado ────────────────────────────────────────────────────────────
    sub(root, "Clave", clave)
    sub(root, "CodigoActividad", actividad_economica)
    sub(root, "NumeroConsecutivo", consecutivo)
    sub(root, "FechaEmision", fecha_emision.strftime("%Y-%m-%dT%H:%M:%S-06:00"))
    sub(root, "ProveedorSistemas", proveedor_sistemas)

    # Emisor
    emisor = sub(root, "Emisor")
    sub(emisor, "Nombre", emisor_nombre)
    ident = sub(emisor, "Identificacion")
    sub(ident, "Tipo", emisor_tipo_id)
    sub(ident, "Numero", emisor_num_id)
    ubicacion = sub(emisor, "Ubicacion")
    sub(ubicacion, "Provincia", emisor_provincia)
    sub(ubicacion, "Canton", emisor_canton)
    sub(ubicacion, "Distrito", emisor_distrito)
    sub(ubicacion, "OtrasSenas", emisor_otras_senas)
    telefono = sub(emisor, "Telefono")
    sub(telefono, "CodigoPais", "506")
    sub(telefono, "NumTelefono", emisor_telefono)
    sub(emisor, "CorreoElectronico", emisor_email)

    # Condición de venta y medio de pago
    sub(root, "CondicionVenta", condicion_venta)
    medio = sub(root, "MedioPago")
    medio.text = medio_pago

    # ── Detalle del servicio ──────────────────────────────────────────────────
    detalle_servicio = sub(root, "DetalleServicio")
    linea = sub(detalle_servicio, "LineaDetalle")
    sub(linea, "NumeroLinea", "1")
    sub(linea, "CodigoComercial").append(_codigo_cabys(cabys))
    sub(linea, "Cantidad", _fmt(cantidad))
    sub(linea, "UnidadMedida", unidad_medida)
    sub(linea, "Detalle", descripcion)
    sub(linea, "PrecioUnitario", _fmt(precio_unitario))
    sub(linea, "MontoTotal", _fmt(monto_total_linea))
    sub(linea, "SubTotal", _fmt(subtotal))

    # Impuesto
    impuesto = sub(linea, "Impuesto")
    sub(impuesto, "Codigo", "01")  # 01 = IVA
    sub(impuesto, "CodigoTarifaIVA", "08")  # 08 = 13%
    sub(impuesto, "Tarifa", _fmt(porcentaje_iva))
    sub(impuesto, "Monto", _fmt(monto_iva))

    sub(linea, "MontoTotalLinea", _fmt(monto_total_linea_con_iva))

    # ── Resumen ───────────────────────────────────────────────────────────────
    resumen = sub(root, "ResumenFactura")
    sub(resumen, "CodigoTipoMoneda").append(_moneda(moneda))
    sub(resumen, "TotalServGravados", _fmt(total_serv_gravados))
    sub(resumen, "TotalServExentos", "0")
    sub(resumen, "TotalServExonerado", "0")
    sub(resumen, "TotalMercanciasGravadas", "0")
    sub(resumen, "TotalMercanciasExentas", "0")
    sub(resumen, "TotalMercExonerada", "0")
    sub(resumen, "TotalGravado", _fmt(total_gravados))
    sub(resumen, "TotalExento", "0")
    sub(resumen, "TotalExonerado", "0")
    sub(resumen, "TotalVenta", _fmt(total_ventas))
    sub(resumen, "TotalDescuentos", "0")
    sub(resumen, "TotalVentaNeta", _fmt(total_ventas_neta))
    sub(resumen, "TotalImpuesto", _fmt(total_impuestos))
    sub(resumen, "TotalIVADevuelto", "0")
    sub(resumen, "TotalOtrosCargos", "0")
    sub(resumen, "TotalComprobante", _fmt(total_comprobante))

    # Serializar
    xml_bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True
    )
    return xml_bytes


def _fmt(n) -> str:
    """Formato numérico: sin ceros innecesarios pero con hasta 5 decimales."""
    return f"{float(n):.5f}".rstrip("0").rstrip(".")


def _codigo_cabys(cabys: str):
    el = etree.Element("Tipo")
    el.text = "04"  # 04 = CABYS
    parent = etree.Element("CodigoComercial")
    tipo = etree.SubElement(parent, "Tipo")
    tipo.text = "04"
    cod = etree.SubElement(parent, "Codigo")
    cod.text = cabys
    return parent


def _moneda(codigo: str):
    el = etree.Element("CodigoTipoMoneda")
    cod = etree.SubElement(el, "CodigoMoneda")
    cod.text = codigo
    tc = etree.SubElement(el, "TipoCambio")
    tc.text = "1"
    return el


# Override para estructura correcta
def _codigo_cabys_fix(parent_el, cabys: str):
    cod = etree.SubElement(parent_el, "CodigoComercial")
    tipo = etree.SubElement(cod, "Tipo")
    tipo.text = "04"
    codigo = etree.SubElement(cod, "Codigo")
    codigo.text = cabys
    return cod


def _moneda_fix(parent_el, codigo: str):
    ctm = etree.SubElement(parent_el, "CodigoTipoMoneda")
    cm = etree.SubElement(ctm, "CodigoMoneda")
    cm.text = codigo
    tc = etree.SubElement(ctm, "TipoCambio")
    tc.text = "1"


# ─── Reescritura limpia ────────────────────────────────────────────────────────

def generar_xml(
    clave, consecutivo, fecha_emision,
    emisor_nombre, emisor_tipo_id, emisor_num_id,
    emisor_provincia, emisor_canton, emisor_distrito,
    emisor_otras_senas, emisor_email, emisor_telefono,
    actividad_economica,
    descripcion, cantidad, unidad_medida,
    precio_unitario, cabys, porcentaje_iva,
    medio_pago="02", condicion_venta="01",
    moneda="CRC", proveedor_sistemas="GauchaSur-FE v1.0",
) -> bytes:

    monto_linea = round(cantidad * precio_unitario, 5)
    monto_iva   = round(monto_linea * porcentaje_iva / 100, 5)
    total       = round(monto_linea + monto_iva, 5)

    R = etree.Element("TiqueteElectronico", nsmap={
        None: NS,
        "xsi": XSI,
    })
    R.set("{%s}schemaLocation" % XSI, SCHEMA_LOCATION)

    def t(parent, tag, text=""):
        el = etree.SubElement(parent, tag)
        el.text = str(text)
        return el

    def f(n):
        s = f"{float(n):.5f}".rstrip("0").rstrip(".")
        return s or "0"

    t(R, "Clave", clave)
    t(R, "CodigoActividad", actividad_economica)
    t(R, "NumeroConsecutivo", consecutivo)
    t(R, "FechaEmision", fecha_emision.strftime("%Y-%m-%dT%H:%M:%S-06:00"))
    t(R, "ProveedorSistemas", proveedor_sistemas)

    E = etree.SubElement(R, "Emisor")
    t(E, "Nombre", emisor_nombre)
    I = etree.SubElement(E, "Identificacion")
    t(I, "Tipo", emisor_tipo_id)
    t(I, "Numero", emisor_num_id)
    U = etree.SubElement(E, "Ubicacion")
    t(U, "Provincia", emisor_provincia)
    t(U, "Canton", emisor_canton)
    t(U, "Distrito", emisor_distrito)
    t(U, "OtrasSenas", emisor_otras_senas)
    T = etree.SubElement(E, "Telefono")
    t(T, "CodigoPais", "506")
    t(T, "NumTelefono", emisor_telefono.replace("-","").replace(" ",""))
    t(E, "CorreoElectronico", emisor_email)

    t(R, "CondicionVenta", condicion_venta)
    t(R, "MedioPago", medio_pago)

    DS = etree.SubElement(R, "DetalleServicio")
    L  = etree.SubElement(DS, "LineaDetalle")
    t(L, "NumeroLinea", "1")
    CC = etree.SubElement(L, "CodigoComercial")
    t(CC, "Tipo", "04")
    t(CC, "Codigo", cabys)
    t(L, "Cantidad", f(cantidad))
    t(L, "UnidadMedida", unidad_medida)
    t(L, "Detalle", descripcion)
    t(L, "PrecioUnitario", f(precio_unitario))
    t(L, "MontoTotal", f(monto_linea))
    t(L, "SubTotal", f(monto_linea))
    IMP = etree.SubElement(L, "Impuesto")
    t(IMP, "Codigo", "01")
    t(IMP, "CodigoTarifaIVA", "08")
    t(IMP, "Tarifa", f(porcentaje_iva))
    t(IMP, "Monto", f(monto_iva))
    t(L, "MontoTotalLinea", f(total))

    RF = etree.SubElement(R, "ResumenFactura")
    CTM = etree.SubElement(RF, "CodigoTipoMoneda")
    t(CTM, "CodigoMoneda", moneda)
    t(CTM, "TipoCambio", "1")
    t(RF, "TotalServGravados",        f(monto_linea))
    t(RF, "TotalServExentos",         "0")
    t(RF, "TotalServExonerado",       "0")
    t(RF, "TotalMercanciasGravadas",  "0")
    t(RF, "TotalMercanciasExentas",   "0")
    t(RF, "TotalMercExonerada",       "0")
    t(RF, "TotalGravado",             f(monto_linea))
    t(RF, "TotalExento",              "0")
    t(RF, "TotalExonerado",           "0")
    t(RF, "TotalVenta",               f(monto_linea))
    t(RF, "TotalDescuentos",          "0")
    t(RF, "TotalVentaNeta",           f(monto_linea))
    t(RF, "TotalImpuesto",            f(monto_iva))
    t(RF, "TotalIVADevuelto",         "0")
    t(RF, "TotalOtrosCargos",         "0")
    t(RF, "TotalComprobante",         f(total))

    return etree.tostring(R, xml_declaration=True, encoding="UTF-8", pretty_print=True)


if __name__ == "__main__":
    xml = generar_xml(
        clave="50605062600310280744200100001040000000001164227489",
        consecutivo="00100001040000000001",
        fecha_emision=datetime(2026, 6, 1, 12, 0, 0),
        emisor_nombre="Tres Bochas Sociedad De Responsabilidad Limitada",
        emisor_tipo_id="02",
        emisor_num_id="3102807442",
        emisor_provincia="6",
        emisor_canton="01",
        emisor_distrito="01",
        emisor_otras_senas="Frente Antigua Discoteca Lora Amarilla, Santa Teresa",
        emisor_email="gauchasantateresa@gmail.com",
        emisor_telefono="60000000",
        actividad_economica="5610000",
        descripcion="Servicio de Restaurante",
        cantidad=1,
        unidad_medida="Sp",
        precio_unitario=20638.94,  # 23320 / 1.13
        cabys="6331000000000",
        porcentaje_iva=13.0,
        medio_pago="02",
    )
    print("✅ XML generado:")
    print(xml.decode("utf-8")[:800])
    print("...")
    print(f"\nTamaño: {len(xml)} bytes")
