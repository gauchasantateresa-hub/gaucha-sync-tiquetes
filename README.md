# Gaucha Sur — Tiquetes Electrónicos Automáticos

Script que corre cada 30 minutos en GitHub Actions y emite
tiquetes electrónicos v4.4 ante Hacienda CR automáticamente.

## Costo: $0

## Cómo funciona

1. Lee las órdenes POS pagadas con tarjeta en Odoo (últimas 2 horas)
2. Las envía a Alegra vía API
3. Alegra genera el XML, lo firma con el certificado .p12 y lo envía a Hacienda
4. Marca la orden en Odoo como "tiquete emitido"

## Configuración en GitHub Secrets

En tu repositorio de GitHub → Settings → Secrets → Actions:

| Secret | Valor |
|--------|-------|
| `ODOO_URL` | `https://gaucha-sur.odoo.com` |
| `ODOO_DB` | `gaucha-sur` |
| `ODOO_USER` | tu email de Odoo |
| `ODOO_API_KEY` | la API key generada en Odoo |
| `ALEGRA_USER` | `gauchasantateresa@gmail.com` |
| `ALEGRA_TOKEN` | `547e9754350c6ec61e81` |
| `ALEGRA_ITEM_ID` | (dejar vacío la primera vez) |

## Cómo generar la API Key de Odoo

1. Odoo → avatar (arriba derecha) → Mi perfil
2. Tab "Cuenta" → "API Keys"
3. "Nueva clave API" → nombre: "gaucha-sync" → copiar

## Correr manualmente

GitHub → Actions → "Gaucha Sur — Tiquetes Electrónicos FE" → "Run workflow"
