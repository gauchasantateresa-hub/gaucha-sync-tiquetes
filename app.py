#!/usr/bin/env python3
"""
app.py — Gaucha Sur Webhook Server
===================================
Recibe eventos de Odoo cuando se registra un pago con tarjeta
y emite automáticamente el tiquete electrónico v4.4 en Alegra.

Endpoints:
  GET  /          → Health check
  POST /webhook   → Recibe evento de pago de Odoo
  POST /test      → Prueba manual con datos de ejemplo
"""

import base64
import json
import logging
import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('gaucha_webhook')

# ── Configuración (variables de entorno en Render) ─────────────────────
ALEGRA_USER   = os.environ.get('ALEGRA_USER', 'gauchasantateresa@gmail.com')
ALEGRA_TOKEN  = os.environ.get('ALEGRA_TOKEN', '547e9754350c6ec61e81')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'gaucha2026')

# Datos del tiquete
CABYS = '5611001001000'  # Servicio de restaurante con servicio de mesa
NOMBRE_SERVICIO = 'Servicio de Restaurante'
ALEGRA_API = 'https://api.alegra.com/api/prime/v1'

# Palabras clave para detectar tarjeta
TARJETA_KW = ['tarjeta', 'card', 'visa', 'mastercard',
               'amex', 'credito', 'crédito', 'debito', 'débito']

# ── Cache del item de Alegra ──────────────────────────────────────────
_alegra_item_id = None


def alegra_headers():
    cred = base64.b64encode(f'{ALEGRA_USER}:{ALEGRA_TOKEN}'.encode()).decode()
    return {'Authorization': f'Basic {cred}', 'Content-Type': 'application/json'}


def get_alegra_item_id():
    global _alegra_item_id
    if _alegra_item_id:
        return _alegra_item_id
    # Buscar o crear item "Servicio de Restaurante"
    resp = requests.get(f'{ALEGRA_API}/items',
                        headers=alegra_headers(),
                        params={'name': NOMBRE_SERVICIO}, timeout=15)
    if resp.status_code == 200:
        items = resp.json()
        if isinstance(items, list) and items:
            _alegra_item_id = items[0]['id']
            log.info('Item Alegra encontrado: %s', _alegra_item_id)
            return _alegra_item_id
    # Crear
    payload = {
        'name': NOMBRE_SERVICIO,
        'price': 1000,
        'tax': [{'id': 5}],  # IVA 13%
        'reference': CABYS,
        'type': 'service',
    }
    resp = requests.post(f'{ALEGRA_API}/items',
                         headers=alegra_headers(), json=payload, timeout=15)
    if resp.status_code in (200, 201):
        _alegra_item_id = resp.json()['id']
        log.info('Item Alegra creado: %s', _alegra_item_id)
        return _alegra_item_id
    log.error('No se pudo obtener item Alegra: %s', resp.text[:200])
    return None


def emitir_tiquete(monto_con_iva: float, fecha: str, referencia: str) -> dict:
    """Emite un tiquete electrónico en Alegra."""
    item_id = get_alegra_item_id()
    if not item_id:
        return {'ok': False, 'error': 'No se pudo obtener item de Alegra'}

    # Precio sin IVA
    precio_sin_iva = round(monto_con_iva / 1.13, 5)

    payload = {
        'date': fecha[:10],
        'dueDate': fecha[:10],
        'paymentType': 'cash',
        'type': '04',  # Tiquete electrónico — consumidor final
        'stamp': {'generateStamp': True},
        'items': [{
            'id': item_id,
            'name': NOMBRE_SERVICIO,
            'quantity': 1,
            'price': precio_sin_iva,
            'tax': [{'id': 5}],
            'reference': CABYS,
        }],
        'notes': f'Ref: {referencia}',
    }

    resp = requests.post(f'{ALEGRA_API}/invoices',
                         headers=alegra_headers(), json=payload, timeout=30)

    if resp.status_code in (200, 201):
        data = resp.json()
        result = {
            'ok': True,
            'numero_alegra': data.get('id'),
            'consecutivo': data.get('numberTemplate', {}).get('fullNumber', ''),
            'clave': (data.get('stamp') or {}).get('electronicInvoiceId', ''),
        }
        log.info('✅ Tiquete emitido | Ref: %s | Alegra #%s | %s',
                 referencia, result['numero_alegra'], result['consecutivo'])
        return result
    else:
        error = resp.json().get('message', resp.text[:200])
        log.error('❌ Error Alegra: %s', error)
        return {'ok': False, 'error': error}


# ── ENDPOINTS ─────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'service': 'Gaucha Sur — Tiquetes Electrónicos',
        'alegra_user': ALEGRA_USER,
    })


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Recibe el evento de pago de Odoo.
    Odoo envía un JSON con los datos de la orden POS cuando se procesa un pago.
    """
    # Verificar secret
    secret = request.headers.get('X-Webhook-Secret', '')
    if secret != WEBHOOK_SECRET:
        log.warning('Secret inválido: %s', secret[:10])
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(force=True, silent=True) or {}
    log.info('Webhook recibido: %s', json.dumps(data)[:200])

    # Extraer datos del payload de Odoo
    # El webhook de Odoo envía los campos del modelo
    order_name = data.get('name', 'N/A')
    amount_total = float(data.get('amount_total', 0))
    date_order = data.get('date_order', '')
    payment_method = data.get('payment_method_name', '').lower()
    state = data.get('state', '')

    # Verificar que es pago con tarjeta y orden completada
    if state not in ('done', 'invoiced', 'paid'):
        return jsonify({'status': 'skipped', 'reason': f'Estado {state} no aplica'})

    es_tarjeta = any(k in payment_method for k in TARJETA_KW)
    if not es_tarjeta:
        return jsonify({'status': 'skipped', 'reason': 'No es pago con tarjeta'})

    if amount_total <= 0:
        return jsonify({'status': 'skipped', 'reason': 'Monto inválido'})

    # Emitir tiquete
    resultado = emitir_tiquete(amount_total, date_order, order_name)

    if resultado['ok']:
        return jsonify({
            'status': 'ok',
            'message': 'Tiquete emitido correctamente',
            'orden': order_name,
            'monto': amount_total,
            **resultado
        })
    else:
        return jsonify({
            'status': 'error',
            'message': resultado['error'],
            'orden': order_name,
        }), 500


@app.route('/test', methods=['POST'])
def test():
    """Endpoint de prueba — emite un tiquete con datos de ejemplo."""
    secret = request.headers.get('X-Webhook-Secret', '')
    if secret != WEBHOOK_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(force=True, silent=True) or {}
    monto = float(data.get('monto', 10000))
    fecha = data.get('fecha', '2026-06-02')
    ref = data.get('referencia', 'TEST-001')

    log.info('🧪 Prueba manual — monto: %s', monto)
    resultado = emitir_tiquete(monto, fecha, ref)
    return jsonify(resultado)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
