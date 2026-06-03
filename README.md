# Gaucha Sur — Servidor de Tiquetes Electrónicos

Servidor que recibe pagos con tarjeta desde Odoo y emite
tiquetes electrónicos v4.4 automáticamente en Alegra → Hacienda CR.

## Flujo

```
Cliente paga con tarjeta en Odoo POS
           ↓
Odoo dispara el webhook automáticamente
           ↓
Este servidor recibe los datos
           ↓
Llama a Alegra → firma → envía a Hacienda
           ↓
Tiquete aceptado en segundos ✅
```

## Costo: $0

## Configurar el Webhook en Odoo

1. Odoo → Ajustes → Técnico → Automatización → Webhooks
2. "Nuevo"
3. Modelo: `Orden de punto de venta (pos.order)`
4. Disparador: `Al actualizar registro`
5. Cuando el campo `state` cambia a `done`
6. URL: `https://gaucha-tiquetes.onrender.com/webhook`
7. Header: `X-Webhook-Secret: gaucha2026`

## Variables de entorno en Render

| Variable | Valor |
|----------|-------|
| ALEGRA_USER | gauchasantateresa@gmail.com |
| ALEGRA_TOKEN | 547e9754350c6ec61e81 |
| WEBHOOK_SECRET | gaucha2026 |

## Probar manualmente

```bash
curl -X POST https://gaucha-tiquetes.onrender.com/test \
  -H "X-Webhook-Secret: gaucha2026" \
  -H "Content-Type: application/json" \
  -d '{"monto": 15000, "fecha": "2026-06-02", "referencia": "TEST-001"}'
```
