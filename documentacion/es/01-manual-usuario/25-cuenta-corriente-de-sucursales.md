---
titulo: Cuenta corriente de cada sucursal: remesas y ajustes
seo_title: Cuenta corriente de sucursales: remesas y ajustes
seo_description: Registrá la plata que manda cada sucursal (remesa) y las correcciones (ajuste). Los despachos suman deuda solos.
palabras_clave: [cuenta corriente sucursal, remesa, ajuste de deuda, saldo de sucursal]
slug: cuenta-corriente-de-sucursales
grupo: G · Central del frigorífico
rol: frigorífico
modulo: Central · Cuenta corriente de sucursales
permiso: staff en la central
estado: verificado
verificado: 2026-11-03 contra central/models.py (MovimientoCuentaSucursal) y central/admin.py
version_sistema: 0.0.1
---

# Cuenta corriente de cada sucursal: remesas y ajustes

> **Para quién es:** el frigorífico.  **Tiempo:** 1 minuto.

Cada sucursal **debe** lo que se le despacha y **paga** con **remesas**. Cuando llega una remesa, la cargás en **Cuenta corriente de sucursales → Añadir**, con tipo **Remesa** y el importe **en positivo**: el sistema la resta de la deuda.

## Los tres tipos de movimiento
| Tipo | Qué es | Cómo se carga |
|---|---|---|
| **Despacho (debe)** | La mercadería enviada | **Solo**, al guardar el despacho |
| **Remesa recibida (haber)** | La plata que manda la sucursal | A mano, en positivo: se guarda restando |
| **Ajuste** | Una corrección (por ejemplo una bonificación) | A mano: positivo suma deuda, negativo la baja. Siempre con descripción |

## Paso a paso

### 1. Mirá los movimientos
![Movimientos de cuenta de las sucursales y el botón para agregar](imagenes/25-cuenta-corriente-de-sucursales/01-movimientos.png)

1. **Despachos, remesas y ajustes** de todas las sucursales. Se filtran por sucursal.
2. **Añadir** un movimiento.

### 2. Registrá una remesa
![Formulario con la sucursal, el tipo Remesa, el importe en positivo y la descripción](imagenes/25-cuenta-corriente-de-sucursales/02-registrar-remesa.png)

1. **Sucursal.**
2. **Tipo:** Remesa recibida.
3. **Importe:** en positivo.
4. **Descripción:** por ejemplo «Remesa en efectivo». Tocá **Guardar**.

### 3. La remesa baja la deuda
![La remesa registrada con importe negativo](imagenes/25-cuenta-corriente-de-sucursales/03-remesa-registrada.png)

1. Se guarda **en negativo**: baja el saldo. El saldo de cada sucursal está en el [panel](23-panel-central.md), columna **Saldo cuenta**.

## Preguntas frecuentes

### ¿Hay que cargar los despachos acá?
No: se cargan solos al guardar el despacho.

## Siguiente paso
- [Catálogo: productos, precios, fotos y plantillas](26-catalogo-precios-y-plantillas.md).
