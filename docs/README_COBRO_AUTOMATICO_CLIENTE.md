# Cobro Automático de Deudas de Clientes (Modo Automático)

Este documento describe la mejora que implementa el **modo automático para el cobro de deudas (Cuenta Corriente / Fiado)** utilizando los adelantos de clientes, evitando la necesidad de realizar conciliaciones manuales.

## Objetivo
Optimizar el flujo de trabajo del cajero en el POS permitiendo que, al registrar un adelanto o saldo a favor de un cliente, el sistema lo aplique de forma **inmediata** y **en cascada (FIFO)** sobre sus deudas pendientes más antiguas.

---

## Cómo Funciona

1. **Configuración de Empresa:**
   Se ha añadido una nueva opción en la configuración global de la empresa (`Configuracion`):
   * **Cobro automático de deudas**: Si está activo, el sistema habilita el procesamiento automático en el POS. Si está inactivo, el comportamiento permanece manual (el cajero decide qué deudas conciliar individualmente usando el saldo disponible).

2. **Criterio FIFO (First-In, First-Out):**
   Al registrar un adelanto de cliente (`AdelantoCliente`) desde el POS con la opción activa, el sistema:
   * Busca todas las deudas pendientes de cobro (tanto **saldos iniciales** como **ventas fiadas**).
   * Las ordena bajo un criterio cronológico estricto (de más antigua a más nueva).
   * Consume el saldo del adelanto y va saldando en cascada cada una de las deudas hasta donde alcance el importe.

3. **Inocuidad Contable (Sin Doble Entrada):**
   * El dinero físico real entra en caja únicamente en el momento de registrar el `AdelantoCliente`.
   * El cobro de deuda automático generado registra `monto_recibido = 0` y `monto_adelanto_aplicado = total_cancelado_en_cascada`. Esto previene duplicaciones en arqueos de caja o reportes de tesorería.

---

## Archivos Modificados

* [core/models.py](core/models.py): Se añade el campo boolean `cobro_automatico_deudas` al modelo `Configuracion`.
* [pos/views.py](pos/views.py):
  * Se implementa la función auxiliar `_intentar_cobro_automatico_por_adelanto` que calcula la antigüedad y reparte el saldo automáticamente.
  * Se integra dentro de la API transaccional `api_adelanto_cliente`.
* [pos/tests.py](pos/tests.py): Se agrega la prueba unitaria `test_cobro_automatico_deudas_por_adelanto` para garantizar que la cascada e importes funcionen correctamente en ambos estados de la configuración.
