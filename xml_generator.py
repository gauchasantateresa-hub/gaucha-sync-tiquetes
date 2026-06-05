"""
Generador TiqueteElectronico v4.4 — orden campo a campo según XSD oficial
"""
from datetime import datetime

NS_DOC = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico"
NS_DS  = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

def f(n):
    s = f"{float(n):.5f}".rstrip("0").rstrip(".")
    return s or "0"

def generar_xml(
    clave, consecutivo, fecha_emision,
    emisor_nombre, emisor_tipo_id, emisor_num_id,
    emisor_provincia, emisor_canton, emisor_distrito,
    emisor_otras_senas, emisor_email, emisor_telefono,
    actividad_economica, descripcion, cantidad, unidad_medida,
    precio_unitario, cabys, porcentaje_iva,
    medio_pago="02", condicion_venta="01",
    moneda="CRC", proveedor_sistemas="GauchaSur-FE v3.0",
) -> bytes:

    p = float(precio_unitario)
    iva = round(p * porcentaje_iva / 100, 5)
    tot = round(p + iva, 5)

    if isinstance(fecha_emision, datetime):
        fech = fecha_emision.strftime("%Y-%m-%dT%H:%M:%S-06:00")
    else:
        fech = str(fecha_emision)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<TiqueteElectronico xmlns="{NS_DOC}" xmlns:ds="{NS_DS}" xmlns:xsi="{NS_XSI}" xsi:schemaLocation="{NS_DOC}.xsd">',
        # Encabezado
        f'<Clave>{clave}</Clave>',
        f'<ProveedorSistemas>{proveedor_sistemas}</ProveedorSistemas>',
        f'<CodigoActividadEmisor>{actividad_economica}</CodigoActividadEmisor>',
        f'<NumeroConsecutivo>{consecutivo}</NumeroConsecutivo>',
        f'<FechaEmision>{fech}</FechaEmision>',
        # Emisor
        '<Emisor>',
        f'<Nombre>{emisor_nombre}</Nombre>',
        f'<Identificacion><Tipo>{emisor_tipo_id}</Tipo><Numero>{emisor_num_id}</Numero></Identificacion>',
        '<Ubicacion>',
        f'<Provincia>{emisor_provincia}</Provincia>',
        f'<Canton>{str(emisor_canton).zfill(2)}</Canton>',
        f'<Distrito>{str(emisor_distrito).zfill(2)}</Distrito>',
        f'<OtrasSenas>{emisor_otras_senas}</OtrasSenas>',
        '</Ubicacion>',
        f'<Telefono><CodigoPais>506</CodigoPais><NumTelefono>{emisor_telefono}</NumTelefono></Telefono>',
        f'<CorreoElectronico>{emisor_email}</CorreoElectronico>',
        '</Emisor>',
        # Condicion venta
        f'<CondicionVenta>{condicion_venta}</CondicionVenta>',
        # Detalle
        '<DetalleServicio><LineaDetalle>',
        '<NumeroLinea>1</NumeroLinea>',
        f'<CodigoCABYS>{cabys}</CodigoCABYS>',
        f'<Cantidad>{f(cantidad)}</Cantidad>',
        f'<UnidadMedida>{unidad_medida}</UnidadMedida>',
        f'<Detalle>{descripcion}</Detalle>',
        f'<PrecioUnitario>{f(p)}</PrecioUnitario>',
        f'<MontoTotal>{f(p)}</MontoTotal>',
        f'<SubTotal>{f(p)}</SubTotal>',
        f'<BaseImponible>{f(p)}</BaseImponible>',
        '<Impuesto>',
        '<Codigo>01</Codigo>',
        '<CodigoTarifaIVA>08</CodigoTarifaIVA>',
        '<Tarifa>13</Tarifa>',
        f'<Monto>{f(iva)}</Monto>',
        '</Impuesto>',
        f'<ImpuestoNeto>{f(iva)}</ImpuestoNeto>',
        f'<MontoTotalLinea>{f(tot)}</MontoTotalLinea>',
        '</LineaDetalle></DetalleServicio>',
        # Resumen
        '<ResumenFactura>',
        f'<CodigoTipoMoneda><CodigoMoneda>{moneda}</CodigoMoneda><TipoCambio>1</TipoCambio></CodigoTipoMoneda>',
        f'<TotalServGravados>{f(p)}</TotalServGravados>',
        '<TotalServExentos>0</TotalServExentos>',
        '<TotalServExonerado>0</TotalServExonerado>',
        '<TotalMercanciasGravadas>0</TotalMercanciasGravadas>',
        '<TotalMercanciasExentas>0</TotalMercanciasExentas>',
        '<TotalMercExonerada>0</TotalMercExonerada>',
        f'<TotalGravado>{f(p)}</TotalGravado>',
        '<TotalExento>0</TotalExento>',
        '<TotalExonerado>0</TotalExonerado>',
        f'<TotalVenta>{f(p)}</TotalVenta>',
        '<TotalDescuentos>0</TotalDescuentos>',
        f'<TotalVentaNeta>{f(p)}</TotalVentaNeta>',
        f'<TotalImpuesto>{f(iva)}</TotalImpuesto>',
        '<TotalIVADevuelto>0</TotalIVADevuelto>',
        '<TotalOtrosCargos>0</TotalOtrosCargos>',
        '<MedioPago>',
        f'<TipoMedioPago>{medio_pago}</TipoMedioPago>',
        f'<TotalMedioPago>{f(tot)}</TotalMedioPago>',
        '</MedioPago>',
        f'<TotalComprobante>{f(tot)}</TotalComprobante>',
        '</ResumenFactura>',
        '</TiqueteElectronico>',
    ]
    return "".join(parts).encode("utf-8")
