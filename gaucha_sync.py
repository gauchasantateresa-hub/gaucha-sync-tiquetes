#!/usr/bin/env python3
"""
gaucha_sync.py
==============
Sincronización automática Odoo → Alegra para tiquetes electrónicos CR
Tres Bochas Sociedad De Responsabilidad Limitada (Gaucha Sur)

Flujo:
  1. Lee pagos con tarjeta del POS de Odoo (últimas 2 horas)
  2. Filtra los que aún no tienen tiquete emitido
  3. Para cada uno, crea un tiquete en Alegra
  4. Alegra lo firma y envía a Hacienda automáticamente
  5. Registra el resultado en un log

Corre cada 30 minutos vía GitHub Actions — sin computadora en el local.
Costo: $0
"""

import base64
import json
import logging
import os
import sys
import xmlrpc.client
from datetime import datetime, timedelta, timezone

import requests

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('gaucha_sync')

# ── Configuración — se lee de variables de entorno (GitHub Secrets) ───
ODOO_URL      = os.environ.get('ODOO_URL', 'https://gaucha-sur.odoo.com')
ODOO_DB       = os.environ.get('ODOO_DB', 'gaucha-sur')
ODOO_USER     = os.environ.get('ODOO_USER', '')       # email admin
ODOO_API_KEY  = os.environ.get('ODOO_API_KEY', '')    # API key de Odoo

ALEGRA_USER   = os.environ.get('ALEGRA_USER', 'gauchasantateresa@gmail.com')
ALEGRA_TOKEN  = os.environ.get('ALEGRA_TOKEN', '547e9754350c6ec61e81')

# CABYS para "Servicios de restaurante con servicio de mesa" = 5611001001000
CABYS_RESTAURANTE = '5611001001000'
NOMBRE_SERVICIO   = 'Servicio de Restaurante'
# ID del item en Alegra (se crea automáticamente si no existe)
ALEGRA_ITEM_ID    = os.environ.get('ALEGRA_ITEM_ID', '')

ALEGRA_API    = 'https://api.alegra.com/api/prime/v1'
# Ventana de tiempo: revisar pagos de las últimas N horas
VENTANA_HORAS = int(os.environ.get('VENTANA_HORAS', '2'))

# Palabras clave para detectar tarjeta
TARJETA_KW = ['tarjeta', 'card', 'visa', 'mastercard',
               'amex', 'credito', 'crédito', 'debito', 'débito']

# ── Autenticación Alegra ──────────────────────────────────────────────
def alegra_headers():
    credencial = base64.b64encode(
        f'{ALEGRA_USER}:{ALEGRA_TOKEN}'.encode()).decode()
    return {
        'Authorization': f'Basic {credencial}',
        'Content-Type': 'application/json',
    }

# ── Conexión Odoo vía XML-RPC ─────────────────────────────────────────
def odoo_connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})
    if not uid:
        raise Exception('❌ No se pudo autenticar en Odoo. Verificá usuario y API key.')
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    log.info('✅ Conectado a Odoo como uid=%s', uid)
    return uid, models

# ── Leer órdenes POS con tarjeta sin tiquete ──────────────────────────
def get_ordenes_pendientes(uid, models):
    desde = (datetime.now(timezone.utc) - timedelta(hours=VENTANA_HORAS))\
            .strftime('%Y-%m-%d %H:%M:%S')

    # Buscar órdenes POS en estado 'done' de las últimas N horas
    ordenes = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY,
        'pos.order', 'search_read',
        [[
            ['state', '=', 'done'],
            ['date_order', '>=', desde],
        ]],
        {'fields': ['id', 'name', 'amount_total', 'date_order',
                    'payment_ids', 'amount_tax', 'amount_return'],
         'limit': 200}
    )

    pendientes = []
    for orden in ordenes:
        # Verificar si tiene pago con tarjeta
        if not orden.get('payment_ids'):
            continue

        # Leer métodos de pago de esta orden
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

        # Verificar si ya tiene tiquete emitido (usando campo en notas internas)
        # Buscamos en account.move vinculada si tiene referencia a Alegra
        if ya_tiene_tiquete(uid, models, orden['id']):
            log.debug('Orden %s ya tiene tiquete — omitiendo', orden['name'])
            continue

        pendientes.append({
            'pos_order_id': orden['id'],
            'pos_order_name': orden['name'],
            'monto_total': orden['amount_total'],
            'monto_tarjeta': monto_tarjeta,
            'monto_impuesto': orden.get('amount_tax', 0),
            'fecha': orden['date_order'],
        })

    log.info('📋 Órdenes con tarjeta pendientes de tiquete: %d', len(pendientes))
    return pendientes

def ya_tiene_tiquete(uid, models, pos_order_id):
    """Verifica si la orden ya tiene un tiquete emitido buscando en notas."""
    try:
        notas = models.execute_kw(
            ODOO_DB, uid, ODOO_API_KEY,
            'mail.message', 'search_read',
            [[
                ['res_id', '=', pos_order_id],
                ['model', '=', 'pos.order'],
                ['body', 'like', 'TIQUETE_ALEGRA:'],
            ]],
            {'fields': ['id'], 'limit': 1}
        )
        return len(notas) > 0
    except Exception:
        return False

# ── Obtener o crear item "Servicio de Restaurante" en Alegra ──────────
def get_or_create_item_alegra():
    """Obtiene el ID del producto en Alegra, o lo crea si no existe."""
    global ALEGRA_ITEM_ID
    if ALEGRA_ITEM_ID:
        return int(ALEGRA_ITEM_ID)

    # Buscar item existente
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

    # Crear el item
    payload = {
        'name': NOMBRE_SERVICIO,
        'price': 1000,  # Precio base (se sobreescribe en cada tiquete)
        'tax': [{'id': 5}],  # IVA 13% en Alegra CR
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

# ── Emitir tiquete en Alegra ──────────────────────────────────────────
def emitir_tiquete(orden, item_id):
    """
    Emite un tiquete electrónico en Alegra para la orden dada.
    El monto ya incluye IVA — Alegra lo desglosa automáticamente.
    """
    monto_tarjeta = orden['monto_tarjeta']
    # Calcular precio sin IVA (monto_tarjeta / 1.13)
    precio_sin_iva = round(monto_tarjeta / 1.13, 5)
    fecha_orden = orden['fecha'][:10]  # YYYY-MM-DD

    payload = {
        'date': fecha_orden,
        'dueDate': fecha_orden,
        'paymentType': 'cash',
        'type': '04',  # 04 = Tiquete electrónico (consumidor final)
        'stamp': {'generateStamp': True},
        'items': [{
            'id': item_id,
            'name': NOMBRE_SERVICIO,
            'description': NOMBRE_SERVICIO,
            'quantity': 1,
            'price': precio_sin_iva,
            'tax': [{'id': 5}],  # IVA 13%
            'reference': CABYS_RESTAURANTE,
        }],
        'notes': f'Orden POS: {orden["pos_order_name"]}',
    }

    resp = requests.post(
        f'{ALEGRA_API}/invoices',
        headers=alegra_headers(),
        json=payload,
        timeout=30
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        numero_alegra = data.get('id', '')
        consecutivo = data.get('numberTemplate', {}).get('fullNumber', '')
        stamp = data.get('stamp', {})
        clave = stamp.get('electronicInvoiceId', '') if stamp else ''
        log.info('✅ Tiquete emitido — Orden: %s | Alegra #%s | Consecutivo: %s',
                 orden['pos_order_name'], numero_alegra, consecutivo)
        return {
            'ok': True,
            'numero_alegra': numero_alegra,
            'consecutivo': consecutivo,
            'clave': clave,
        }
    else:
        error = resp.json().get('message', resp.text[:200])
        log.error('❌ Error emitiendo tiquete para %s: %s',
                  orden['pos_order_name'], error)
        return {'ok': False, 'error': error}

# ── Marcar orden en Odoo como tiquete emitido ─────────────────────────
def marcar_tiquete_emitido(uid, models, orden, resultado):
    """Agrega una nota interna en la orden POS con los datos del tiquete."""
    nota = (
        f'TIQUETE_ALEGRA: ✅<br/>'
        f'N° Alegra: {resultado["numero_alegra"]}<br/>'
        f'Consecutivo: {resultado["consecutivo"]}<br/>'
        f'Clave: {resultado.get("clave", "Pendiente")}<br/>'
        f'Monto tarjeta: ₡{orden["monto_tarjeta"]:,.2f}'
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

# ── MAIN ──────────────────────────────────────────────────────────────
def main():
    log.info('=' * 60)
    log.info('🚀 Gaucha Sur — Sincronización FE iniciada')
    log.info('Ventana de tiempo: últimas %d horas', VENTANA_HORAS)
    log.info('=' * 60)

    if not ODOO_USER or not ODOO_API_KEY:
        log.error('Faltan credenciales de Odoo (ODOO_USER, ODOO_API_KEY)')
        sys.exit(1)

    # 1. Conectar a Odoo
    try:
        uid, models = odoo_connect()
    except Exception as e:
        log.error('Error conectando a Odoo: %s', e)
        sys.exit(1)

    # 2. Obtener item de Alegra
    item_id = get_or_create_item_alegra()
    if not item_id:
        log.error('No se pudo obtener item de Alegra')
        sys.exit(1)

    # 3. Leer órdenes pendientes
    ordenes = get_ordenes_pendientes(uid, models)

    if not ordenes:
        log.info('✨ No hay órdenes pendientes. Todo al día.')
        return

    # 4. Emitir tiquetes
    exitosos = 0
    fallidos = 0
    for orden in ordenes:
        log.info('📄 Procesando orden %s — ₡%s',
                 orden['pos_order_name'],
                 f"{orden['monto_tarjeta']:,.2f}")
        resultado = emitir_tiquete(orden, item_id)
        if resultado['ok']:
            marcar_tiquete_emitido(uid, models, orden, resultado)
            exitosos += 1
        else:
            fallidos += 1

    log.info('=' * 60)
    log.info('📊 Resumen: %d tiquetes emitidos, %d errores', exitosos, fallidos)
    log.info('=' * 60)

    if fallidos > 0:
        sys.exit(1)  # Hace que GitHub Actions lo marque como fallido

if __name__ == '__main__':
    main()
