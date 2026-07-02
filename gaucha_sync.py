#!/usr/bin/env python3
"""
gaucha_sync.py
===============
Sincronizacion automatica Odoo -> FACTURATica para tiquetes electronicos CR
Tres Bochas Sociedad De Responsabilidad Limitada (Gaucha Sur)

Flujo:
  1. Lee pagos con tarjeta del POS de Odoo (desde el 1 de julio en adelante)
  2. Filtra los que aun no tienen tiquete emitido
  3. Para cada uno, timbra un tiquete via FACTURATica
  4. FACTURATica lo firma y envia a Hacienda automaticamente
  5. Registra el resultado en una nota de Odoo

Corre cada 30 minutos via GitHub Actions.
"""

import base64
import json
import logging
import os
import sys
import xmlrpc.client
from datetime import datetime, timedelta, timezone

import requests
import facturatica

# -- Logging --------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('gaucha_sync')
TICKET_OK_MSG = 'Tiquete FACTURATica OK: %s -> clave %s'
TICKET_ERROR_MSG = 'Error emitiendo tiquete FACTURATica para %s: %s'

# -- Configuracion -- se lee de variables de entorno (GitHub Secrets) --
ODOO_URL      = os.environ.get('ODOO_URL', 'https://gaucha-sur.odoo.com')
ODOO_DB       = os.environ.get('ODOO_DB', 'gaucha-sur')
ODOO_USER     = os.environ.get('ODOO_USER', 'gauchasantateresa@gmail.com')
ODOO_API_KEY  = os.environ.get('ODOO_API_KEY', '35283b24ba813e5ea0014fe25aa600680be4ba9a')

ALEGRA_USER   = os.environ.get('ALEGRA_USER', 'gauchasantateresa@gmail.com')
ALEGRA_TOKEN  = os.environ.get('ALEGRA_TOKEN', '547e9754350c6ec61e81')

CABYS_RESTAURANTE = '5611001001000'
NOMBRE_SERVICIO   = 'Servicio de Restaurante'
ALEGRA_ITEM_ID    = os.environ.get('ALEGRA_ITEM_ID', '')

ALEGRA_API    = 'https://api.alegra.com/api/prime/v1'
desde_default = os.environ.get('FECHA_INICIO_FACTURACION', '2026-07-01 15:45:46')

TARJETA_KW = ['tarjeta', 'card', 'visa', 'mastercard',
              'amex', 'credito', 'credito', 'debito', 'debito']

def alegra_headers():
    credencial = base64.b64encode(
        f'{ALEGRA_USER}:{ALEGRA_TOKEN}'.encode()).decode()
    return {
        'Authorization': f'Basic {credencial}',
        'Content-Type': 'application/json',
    }

def odoo_connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})
    if not uid:
        raise Exception('No se pudo autenticar en Odoo. Verifica usuario y API key.')
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    log.info('Conectado a Odoo como uid=%s', uid)
    return uid, models

def get_ordenes_pendientes(uid, models):
    desde = desde_default

    ordenes = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        'pos.order', 'search_read',
        [[
            ['state', '=', 'done'],
            ['date_order', '>=', desde],
            ['name', 'like', 'Gaucha Sur'],
        ]],
        {'fields': ['id', 'name', 'amount_total', 'date_order',
                    'payment_ids', 'amount_tax', 'amount_return'],
         'limit': 200}
    )

    pendientes = []
    for orden in ordenes:
        if not orden.get('payment_ids'):
            continue

        pagos = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            'pos.payment', 'read',
            [orden['payment_ids']],
            {'fields': ['payment_method_id', 'amount']}
        )

        es_tarjeta = False
        monto_tarjeta = 0
        for pago in pagos:
            nombre_metodo = (pago.get('payment_method_id') or ['', ''])[1].lower()
            if any(k in nombre_metodo for k in TARJETA_KW):
                es_tarjeta = True
                monto_tarjeta += pago.get('amount', 0)

        if not es_tarjeta or monto_tarjeta <= 0:
            continue

        if ya_tiene_tiquete(uid, models, orden['id']):
            log.debug('Orden %s ya tiene tiquete - omitiendo', orden['name'])
            continue

        pendientes.append({
            'pos_order_id': orden['id'],
            'pos_order_name': orden['name'],
            'monto_total': orden['amount_total'],
            'monto_tarjeta': monto_tarjeta,
            'monto_impuesto': orden.get('amount_tax', 0),
            'fecha': orden['date_order'],
        })

    log.info('Ordenes con tarjeta pendientes de tiquete: %d', len(pendientes))
    return pendientes

def ya_tiene_tiquete(uid, models, pos_order_id):
    try:
        notas = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            'mail.message', 'search_read',
            [[
                ['res_id', '=', pos_order_id],
                ['model', '=', 'pos.order'],
                ['body', 'like', 'TIQUETE ELECTRONICO'],
            ]],
            {'fields': ['id'], 'limit': 1}
        )
        return len(notas) > 0
    except Exception:
        return False

def get_or_create_item_alegra():
    global ALEGRA_ITEM_ID
    if ALEGRA_ITEM_ID:
        return int(ALEGRA_ITEM_ID)

    resp = requests.get(
        f'{ALEGRA_API}/items',
        headers=alegra_headers(),
        params={'name': NOMBRE_SERVICIO},
        timeout=15
    )
    if resp.status_code == 200:
        items = resp.json()
        if isinstance(items, list) and items:
            item_id = items[0]['id']
            log.info('Item Alegra encontrado: id=%s', item_id)
            return item_id

    payload = {
        'name': NOMBRE_SERVICIO,
        'price': 1000,
        'tax': [{'id': 5}],
        'reference': CABYS_RESTAURANTE,
        'type': 'service',
    }
    resp = requests.post(
        f'{ALEGRA_API}/items',
        headers=alegra_headers(),
        json=payload,
        timeout=15
    )
    if resp.status_code in (200, 201):
        item_id = resp.json()['id']
        log.info('Item Alegra creado: id=%s', item_id)
        return item_id
    else:
        log.warning('No se pudo crear item en Alegra: %s', resp.text[:200])
        return None

def emitir_tiquete(orden, item_id):
    monto = orden['monto_tarjeta']
    resultado = facturatica.timbrar_tiquete(
        monto_total=monto,
        descripcion=NOMBRE_SERVICIO,
        medio_pago='02',
    )
    if resultado.get('ok'):
        log.info(TICKET_OK_MSG, orden['pos_order_name'], resultado['clave'])
        return {'ok': True, 'clave': resultado['clave']}
    else:
        error = resultado.get('error', 'error desconocido')
        log.error(TICKET_ERROR_MSG, orden['pos_order_name'], error)
        return {'ok': False, 'error': error}

def marcar_tiquete_emitido(uid, models, orden, resultado):
    nota = (
        f'TIQUETE ELECTRONICO (FACTURATica)<br/>'
        f'Clave Hacienda: {resultado.get("clave", "Pendiente")}<br/>'
        f'Monto tarjeta: c{orden["monto_tarjeta"]:,.2f}'
    )
    try:
        models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            'pos.order', 'message_post',
            [[orden['pos_order_id']]],
            {'body': nota, 'message_type': 'comment'}
        )
    except Exception as e:
        log.warning('No se pudo agregar nota en Odoo: %s', e)

def main():
    log.info('=' * 60)
    log.info('Gaucha Sur - Sincronizacion FE iniciada')
    log.info('Fecha de inicio de facturacion: %s', desde_default)
    log.info('=' * 60)

    if not ODOO_USER or not ODOO_API_KEY:
        log.error('Faltan credenciales de Odoo (ODOO_USER, ODOO_API_KEY)')
        sys.exit(1)

    try:
        uid, models = odoo_connect()
    except Exception as e:
        log.error('Error conectando a Odoo: %s', e)
        sys.exit(1)

    item_id = None

    ordenes = get_ordenes_pendientes(uid, models)

    if not ordenes:
        log.info('No hay ordenes pendientes. Todo al dia.')
        return

    exitosos = 0
    fallidos = 0
    for orden in ordenes:
        log.info('Procesando orden %s - c%s',
                 orden['pos_order_name'],
                 f"{orden['monto_tarjeta']:,.2f}")
        resultado = emitir_tiquete(orden, item_id)
        if resultado['ok']:
            marcar_tiquete_emitido(uid, models, orden, resultado)
            exitosos += 1
        else:
            fallidos += 1

    log.info('=' * 60)
    log.info('Resumen: %d tiquetes emitidos, %d errores', exitosos, fallidos)
    log.info('=' * 60)

    if fallidos > 0:
        sys.exit(1)

if __name__ == '__main__':
    main()
