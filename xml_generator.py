"""
Generador XML TiqueteElectronico v4.4
Orden de campos según XSD oficial de Hacienda v4.4 (descargado hoy)

LineaDetalle:
  NumeroLinea → CodigoCABYS → [CodigoComercial 0-5] → Cantidad → UnidadMedida
  → [Detalle] → [PrecioUnitario] → [MontoTotal] → [SubTotal] → [Impuesto] → MontoTotalLinea

ResumenFactura:
  CodigoTipoMoneda → TotalServGravados → TotalServExentos → TotalServExonerado
  → TotalMercanciasGravadas → TotalMercanciasExentas → TotalMercExonerada
  → TotalGravado → TotalExento → TotalExonerado → TotalVenta → TotalDescuentos
  → TotalVentaNeta → TotalImpuesto → TotalIVADevuelto → TotalOtrosCargos
  → MedioPago{TipoMedioPago,TotalMedioPago} → TotalComprobante
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
    actividad_economica,
    descripcion, cantidad, unidad_medida,
    precio_unitario, cabys, porcentaje_iva,
    medio_pago="02", condicion_venta="01",
    moneda="CRC", proveedor_sistemas="GauchaSur-FE v3.0",
) -> bytes:

    precio_sin_iva = float(precio_unitario)
    monto_iva      = round(precio_sin_iva * porcentaje_iva / 100, 5)
    total          = round(precio_sin_iva + monto_iva, 5)

    if isinstance(fecha_emision, datetime):
        fecha_str = fecha_emision.strftime("%Y-%m-%dT%H:%M:%S-06:00")
    else:
        fecha_str = str(fecha_emision)

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<TiqueteElectronico'
        f' xmlns="{NS_DOC}"'
        f' xmlns:ds="{NS_DS}"'
        f' xmlns:xsi="{NS_XSI}"'
        f' xsi:schemaLocation="{NS_DOC}.xsd">'

        # Encabezado — orden XSD v4.4
        f'<Clave>{clave}</Clave>'
        f'<ProveedorSistemas>{proveedor_sistemas}</ProveedorSistemas>'
        f'<CodigoActividadEmisor>{actividad_economica}</CodigoActividadEmisor>'
        f'<NumeroConsecutivo>{consecutivo}</NumeroConsecutivo>'
        f'<FechaEmision>{fecha_str}</FechaEmision>'

        # Emisor
        f'<Emisor>'
        f'<Nombre>{emisor_nombre}</Nombre>'
        f'<Identificacion><Tipo>{emisor_tipo_id}</Tipo><Numero>{emisor_num_id}</Numero></Identificacion>'
        f'<Ubicacion>'
        f'<Provincia>{emisor_provincia}</Provincia>'
        f'<Canton>{str(emisor_canton).zfill(2)}</Canton>'
        f'<Distrito>{str(emisor_distrito).zfill(2)}</Distrito>'
        f'<OtrasSenas>{emisor_otras_senas}</OtrasSenas>'
        f'</Ubicacion>'
        f'<Telefono><CodigoPais>506</CodigoPais><NumTelefono>{emisor_telefono}</NumTelefono></Telefono>'
        f'<CorreoElectronico>{emisor_email}</CorreoElectronico>'
        f'</Emisor>'

        # CondicionVenta directamente después del Emisor
        f'<CondicionVenta>{condicion_venta}</CondicionVenta>'

        # DetalleServicio
        f'<DetalleServicio>'
        f'<LineaDetalle>'
        f'<NumeroLinea>1</NumeroLinea>'
        # CodigoCABYS va primero (13 dígitos obligatorio en v4.4)
        f'<CodigoCABYS>{cabys}</CodigoCABYS>'
        f'<Cantidad>{f(cantidad)}</Cantidad>'
        f'<UnidadMedida>{unidad_medida}</UnidadMedida>'
        f'<Detalle>{descripcion}</Detalle>'
        f'<PrecioUnitario>{f(precio_sin_iva)}</PrecioUnitario>'
        f'<MontoTotal>{f(precio_sin_iva)}</MontoTotal>'
        f'<SubTotal>{f(precio_sin_iva)}</SubTotal>'
        f'<Impuesto>'
        f'<Codigo>01</Codigo>'
        f'<CodigoTarifaIVA>08</CodigoTarifaIVA>'
        f'<Tarifa>13</Tarifa>'
        f'<Monto>{f(monto_iva)}</Monto>'
        f'</Impuesto>'
        f'<MontoTotalLinea>{f(total)}</MontoTotalLinea>'
        f'</LineaDetalle>'
        f'</DetalleServicio>'

        # ResumenFactura — MedioPago DENTRO, antes de TotalComprobante
        f'<ResumenFactura>'
        f'<CodigoTipoMoneda><CodigoMoneda>{moneda}</CodigoMoneda><TipoCambio>1</TipoCambio></CodigoTipoMoneda>'
        f'<TotalServGravados>{f(precio_sin_iva)}</TotalServGravados>'
        f'<TotalServExentos>0</TotalServExentos>'
        f'<TotalServExonerado>0</TotalServExonerado>'
        f'<TotalMercanciasGravadas>0</TotalMercanciasGravadas>'
        f'<TotalMercanciasExentas>0</TotalMercanciasExentas>'
        f'<TotalMercExonerada>0</TotalMercExonerada>'
        f'<TotalGravado>{f(precio_sin_iva)}</TotalGravado>'
        f'<TotalExento>0</TotalExento>'
        f'<TotalExonerado>0</TotalExonerado>'
        f'<TotalVenta>{f(precio_sin_iva)}</TotalVenta>'
        f'<TotalDescuentos>0</TotalDescuentos>'
        f'<TotalVentaNeta>{f(precio_sin_iva)}</TotalVentaNeta>'
        f'<TotalImpuesto>{f(monto_iva)}</TotalImpuesto>'
        f'<TotalIVADevuelto>0</TotalIVADevuelto>'
        f'<TotalOtrosCargos>0</TotalOtrosCargos>'
        f'<MedioPago>'
        f'<TipoMedioPago>{medio_pago}</TipoMedioPago>'
        f'<TotalMedioPago>{f(total)}</TotalMedioPago>'
        f'</MedioPago>'
        f'<TotalComprobante>{f(total)}</TotalComprobante>'
        f'</ResumenFactura>'
        f'</TiqueteElectronico>'
    )
    return xml.encode('utf-8')
