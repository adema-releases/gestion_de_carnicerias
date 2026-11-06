# Pago Automático de Deudas a Proveedores (Modo Automático)

Este documento describe la mejora que implementa el **modo automático para el pago de deudas de cuenta corriente** utilizando los adelantos entregados a proveedores.

## Objetivo
Agilizar el flujo de pagos a proveedores desde el POS. Al entregar y registrar un adelanto o saldo a favor a un proveedor, el sistema lo aplica de forma **inmediata** y **en cascada (FIFO)** sobre sus facturas de compra a crédito o saldos iniciales pendientes más antiguos.

---

## Cómo Funciona

1. **Configuración de Empresa:**
   Se ha añadido una nueva opción en la configuración global de la empresa (`Configuracion`):
   * **Pago automático de deudas a proveedores**: Si está activo, el sistema habilita el procesamiento automático de saldos a favor al registrar adelantos. Si está inactivo, el comportamiento permanece manual (el cajero decide qué deudas conciliar individualmente usando el saldo de adelanto disponible).

2. **Criterio FIFO (First-In, First-Out):**
   Al registrar un adelanto a un proveedor (`AdelantoProveedor`) desde el POS con la opción activa, el sistema:
   * Busca todas las deudas pendientes de pago (tanto **saldos iniciales** como **compras cargadas a Cuenta Corriente**).
   * Las ordena bajo un criterio cronológico estricto (de más antigua a más nueva).
   * Consume el saldo del adelanto y va saldando en cascada cada una de las deudas hasta donde alcance el importe.

3. **Inocuidad Contable (Sin Doble Salida de Caja):**
   * El dinero físico real sale de caja únicamente en el momento de registrar el `AdelantoProveedor`.
   * La cancelación de deuda automática generada registra `monto_pagado = 0` y `monto_adelanto_aplicado = total_cancelado_en_cascada`, previniendo duplicaciones en los reportes de egresos de caja o tesorería.

---

## Archivos Modificados

* [core/models.py](core/models.py): Se añade el campo boolean `pago_automatico_deudas_proveedores` al modelo `Configuracion`.
* [pos/views.py](pos/views.py):
  * Se implementa la función auxiliar `_intentar_pago_automatico_por_adelanto_proveedor` que calcula la antigüedad de deudas y reparte el saldo automáticamente.
  * Se integra dentro de la API transaccional `api_adelanto_proveedor`.
* [pos/tests.py](pos/tests.py): Se agrega el test unitario `test_pago_automatico_deudas_proveedor_por_adelanto` para garantizar que la cascada e importes de proveedores funcionen correctamente en ambos estados de la configuración.
