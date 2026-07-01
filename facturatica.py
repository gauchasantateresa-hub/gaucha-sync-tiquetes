# facturatica.py -- Cliente del API de Factura Electronica de FACTURATica
# Reemplaza la integracion con Alegra. Probado y funcionando en produccion:
# NOMBRE -> success:true (valida credenciales)
# TIMBRAR_TIQUETE -> clave de 50 digitos (aceptado por Hacienda, verificado con ESTADO)

import os
import json
import logging
import requests

log = logging.getLogger('facturatica')

FACTURATICA_URL = os.environ.get('FACTURATICA_URL', 'https://mi.facturatica.com/_api.php')
FACTURATICA_API_KEY = os.environ.get('FACTURATICA_API_KEY', 'YZPCZCX37WTQJBRFMTKF5T9K2TAEDGNP')
FACTURATICA_CORREO = os.environ.get('FACTURATICA_CORREO', 'gauchasantateresa@gmail.com')
FACTURATICA_IDENTIFICACION = os.environ.get('FACTURATICA_IDENTIFICACION', '3102807442')


def _auth():
    return {
        'CORREO': FACTURATICA_CORREO,
        'API_KEY': FACTURATICA_API_KEY,
        'IDENTIFICACION': FACTURATICA_IDENTIFICACION,
    }


def validar_nombre(numero_cedula):
    """Valida credenciales + consulta nombre en padron de Hacienda. No gasta documentos."""
    params = _auth()
    params['ACTION'] = 'NOMBRE'
    params['NUMERO'] = numero_cedula
    r = requests.post(FACTURATICA_URL, data=params, timeout=30)
    try:
        return r.json()
    except Exception:
        return {'success': False, 'raw': r.text[:300]}


def timbrar_tiquete(monto_total, descripcion='Servicio de Restaurante', medio_pago='02', tarifa_iva=13):
    """
    Timbra un tiquete electronico de una linea por monto_total (precio final, IVA incluido).
    medio_pago: '01' efectivo, '02' tarjeta, '03' cheque, '04' transferencia, '06' sinpe movil.
    Retorna {'ok': True, 'clave': '<50 digitos>'} o {'ok': False, 'error': '...'}
    """
    monto_total = round(float(monto_total), 2)
    factor = 1 + (tarifa_iva / 100.0)
    subtotal = round(monto_total / factor, 2)
    iva = round(monto_total - subtotal, 2)

    lineas = [{
        "NumeroLinea": "1",
        "Cantidad": "1.00",
        "UnidadMedida": "Sp",
        "Detalle": descripcion,
        "PrecioUnitario": f"{subtotal:.2f}",
        "MontoTotal": f"{subtotal:.2f}",
        "SubTotal": f"{subtotal:.2f}",
        "Tarifa": str(tarifa_iva),
        "Monto": f"{iva:.2f}",
        "MontoTotalLinea": f"{monto_total:.2f}",
    }]

    params = _auth()
    params.update({
        'ACTION': 'TIMBRAR_TIQUETE',
        'LINEAS': json.dumps(lineas),
        'SUBTOTAL': f"{subtotal:.2f}",
        'IV': f"{iva:.2f}",
        'TOTALIVI': f"{monto_total:.2f}",
        'CONDICIONVENTA': '01',
        'MEDIOPAGO': medio_pago,
    })

    try:
        r = requests.post(FACTURATICA_URL, data=params, timeout=30)
        texto = r.text.strip()
        if len(texto) == 50 and texto.isdigit():
            return {'ok': True, 'clave': texto, 'subtotal': subtotal, 'iva': iva, 'total': monto_total}
        else:
            return {'ok': False, 'error': texto[:400]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def consultar_estado(clave_numerica):
    """Consulta ind-estado (aceptado/rechazado/procesando) de un documento ya timbrado."""
    params = _auth()
    params['ACTION'] = 'ESTADO'
    params['CLAVENUMERICA'] = clave_numerica
    try:
        r = requests.post(FACTURATICA_URL, data=params, timeout=30)
        return r.json()
    except Exception as e:
        return {'error': str(e)}
