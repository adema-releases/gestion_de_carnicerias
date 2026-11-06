---
titulo: Controles de la semana: caja, comandas anuladas y mermas
seo_title: Controles semanales del gerente: caja, anuladas y merma
seo_description: Revisá cada semana las diferencias de caja, las comandas anuladas y la merma de la liquidación, y corregí errores con un ajuste de cuenta.
palabras_clave: [control semanal, diferencias de caja, comandas anuladas, ajuste de cuenta]
slug: controles-de-la-semana
grupo: F · Gerente de sucursal
rol: gerente
modulo: Admin · Ventas · Recepción · Tesorería
permiso: superusuario
estado: verificado
verificado: 2026-11-03 contra ventas/admin.py, recepcion/admin.py y tesoreria/models.py (AjusteCuenta)
version_sistema: 0.0.1
---

# Controles de la semana: caja, comandas anuladas y mermas

> **Para quién es:** el gerente.  **Tiempo:** 15 minutos por semana.

Una vez por semana, conviene revisar tres cosas en el admin: las **diferencias de caja**, las **comandas anuladas** y la **merma de la liquidación**. Los errores de caja se corrigen con un **ajuste de cuenta**.

## Para qué sirve
Un faltante chico todos los días o muchas comandas anuladas por la misma persona son señales que solo se ven mirando la semana entera.

## Paso a paso

### 1. Diferencias de caja
**Ventas → Turnos de caja**.

![Turnos de caja con saldo inicial, saldo final, diferencia de cierre y PDF](imagenes/22-controles-de-la-semana/01-turnos-de-caja.png)

1. Cada cierre con su **saldo inicial**, **saldo final**, **diferencia de cierre** (en rojo si faltó) y el **PDF** del cierre. Abrí el turno para ver el **motivo** que escribió la cajera.

### 2. Comandas anuladas
**Ventas → Comandas**, filtrando por estado **anulada**.

![Comandas anuladas con quién la anuló y el motivo, y el filtro por estado](imagenes/22-controles-de-la-semana/02-comandas-anuladas.png)

1. Cada comanda anulada, con **quién** la anuló y el **motivo**.
2. **Filtro por estado:** abierta, cobrada o anulada.

### 3. Merma de la liquidación
**Recepción y desposte → Conteos y liquidaciones**.

![Conteos y liquidaciones con la merma y las diferencias de cada semana](imagenes/22-controles-de-la-semana/03-liquidaciones.png)

1. Cada liquidación con su **merma** y sus **diferencias**. Si la merma pasa del **6 %**, buscá la causa: carne vieja, despostes sin cargar o kilos mal tipeados en las comandas.

### 4. Corregir un error de caja: ajuste de cuenta
**Tesorería → Ajustes de cuenta → Añadir**.

![Ajuste de cuenta con la cuenta, el monto y el motivo](imagenes/22-controles-de-la-semana/04-ajuste-de-cuenta.png)

1. **Cuenta** a corregir (por ejemplo Efectivo o Diferencias de Caja).
2. **Monto:** positivo suma, negativo resta.
3. **Descripción:** el motivo, siempre.

## Qué pasa por detrás
- El turno cerrado no se toca: el ajuste es un movimiento nuevo que deja rastro.

## Preguntas frecuentes

### ¿Puedo editar un turno cerrado para corregirlo?
No conviene: se pierde el registro. Usá un ajuste de cuenta.

## Siguiente paso
- Para el frigorífico: [El panel de la central](23-panel-central.md).
