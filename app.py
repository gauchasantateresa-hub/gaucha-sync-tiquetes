#!/usr/bin/env python3
import base64, json, logging, os, requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('gaucha_webhook')

ALEGRA_USER   = os.environ.get('ALEGRA_USER', 'gauchasantateresa@gmail.com')
ALEGRA_TOKEN  = os.environ.get('ALEGRA_TOKEN', '547e9754350c6ec61e81')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'gaucha2026')
CABYS = '5611001001000'
NOMBRE_SERVICIO = 'Servicio de Restaurante'
ALEGRA_API = 'https://api.alegra.com/api/prime/v1'
TARJETA_KW = ['tarjeta', 'card', 'visa', 'mastercard', 'amex', 'credito', 'debito']
_alegra_item_id = None

def alegra_headers():
    cred = base64.b64encode(f'{ALEGRA_USER}:{ALEGRA_TOKEN}'.encode()).decode()
    return {'Authorization': f'Basic {cred}', 'Content-Type': 'application/json'}

def get_alegra_item_id():
    global _alegra_item_id
    if _alegra_item_id:
        return _alegra_item_id
    resp = requests.get(f'{ALEGRA_API}/items', headers=alegra_headers(), params={'name': NOMBRE_SERVICIO}, timeout=15)
    if resp.status_code == 200:
        items = resp.json()
        if isinstance(items, list) and items:
            _alegra_item_id = items[0]['id']
            return _alegra_item_id
    payload = {'name': NOMBRE_SERVICIO, 'price': 1000, 'tax': [{'id': 5}], 'reference': CABYS, 'type': 'service'}
    resp = requests.post(f'{ALEGRA_API}/items', headers=alegra_headers(), json=payload, timeout=15)
    if resp.status_code in (200, 201):
        _alegra_item_id = resp.json()['id']
        return _alegra_item_id
    return None

def emitir_tiquete(monto_con_iva, fecha, referencia):
    item_id = get_alegra_item_id()
    if not item_id:
        return {'ok': False, 'error': 'No se pudo obtener item de Alegra'}
    precio_sin_iva = round(monto_con_iva / 1.13, 5)
    payload = {
        'date': str(fecha)[:10], 'dueDate': str(fecha)[:10],
        'paymentType': 'cash', 'type': '04',
        'stamp': {'generateStamp': True},
        'items': [{'id': item_id, 'name': NOMBRE_SERVICIO, 'quantity': 1,
                   'price': precio_sin_iva, 'tax': [{'id': 5}], 'reference': CABYS}],
        'notes': f'Ref: {referencia}',
    }
    resp = requests.post(f'{ALEGRA_API}/invoices', headers=alegra_headers(), json=payload, timeout=30)
    if resp.status_code in (200, 201):
        data = resp.json()
        result = {'ok': True, 'numero_alegra': data.get('id'),
                  'consecutivo': data.get('numberTemplate', {}).get('fullNumber', ''),
                  'clave': (data.get('stamp') or {}).get('electronicInvoiceId', '')}
        log.info('✅ Tiquete emitido — %s | Alegra #%s | %s', referencia, result['numero_alegra'], result['consecutivo'])
        return result
    else:
        error = resp.json().get('message', resp.text[:200])
        log.error('❌ Error Alegra: %s', error)
        return {'ok': False, 'error': error}

@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'Gaucha Sur — Tiquetes FE'})

@app.route('/app', methods=['GET'])
def serve_app():
    return send_file('app_odoo.html')

@app.route('/webhook', methods=['POST'])
def webhook():
    secret = request.headers.get('X-Webhook-Secret', '')
    if secret != WEBHOOK_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(force=True, silent=True) or {}
    order_name = data.get('name', 'N/A')
    amount_total = float(data.get('amount_total', 0))
    date_order = data.get('date_order', '')
    payment_method = data.get('payment_method_name', '').lower()
    state = data.get('state', '')
    if state not in ('done', 'invoiced', 'paid'):
        return jsonify({'status': 'skipped', 'reason': f'Estado {state} no aplica'})
    es_tarjeta = any(k in payment_method for k in TARJETA_KW)
    if not es_tarjeta:
        return jsonify({'status': 'skipped', 'reason': 'No es pago con tarjeta'})
    if amount_total <= 0:
        return jsonify({'status': 'skipped', 'reason': 'Monto inválido'})
    resultado = emitir_tiquete(amount_total, date_order, order_name)
    if resultado['ok']:
        return jsonify({'status': 'ok', 'message': 'Tiquete emitido', 'orden': order_name, **resultado})
    else:
        return jsonify({'status': 'error', 'message': resultado['error']}), 500

@app.route('/test', methods=['POST'])
def test():
    secret = request.headers.get('X-Webhook-Secret', '')
    if secret != WEBHOOK_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(force=True, silent=True) or {}
    resultado = emitir_tiquete(float(data.get('monto', 10000)), data.get('fecha', '2026-06-02'), data.get('referencia', 'TEST-001'))
    return jsonify(resultado)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
