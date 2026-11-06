# Manual de Turno de Caja — Gestion de Carnicerias

> Actualizado 2026-07-07 tras la refactorización del flujo de caja (modelo
> "terminal de supermercado"). El diagnóstico y diseño completos están en
> [docs/AUDITORIA-CIERRE-CAJA.md](docs/AUDITORIA-CIERRE-CAJA.md).
> Para el manejo de cuentas a nivel administrador (tipos de medios de pago,
> ajustes, faltantes/sobrantes, rutina de control), ver el
> [Manual de Medios de Pago y Cuentas](MEDIOS_DE_PAGO_MANUAL.md).

## Índice
1. [Conceptos básicos](#1-conceptos-básicos)
2. [Cuentas del sistema](#2-cuentas-del-sistema)
3. [Configuración inicial](#3-configuración-inicial)
4. [Flujo de apertura de turno](#4-flujo-de-apertura-de-turno)
5. [Flujo de cierre de turno](#5-flujo-de-cierre-de-turno)
6. [Diferencias de arqueo](#6-diferencias-de-arqueo)
7. [Trazabilidad de cuentas](#7-trazabilidad-de-cuentas)
8. [Inmutabilidad y correcciones](#8-inmutabilidad-y-correcciones)
9. [Preguntas frecuentes](#9-preguntas-frecuentes)

---

## 1. Conceptos básicos

El flujo replica una terminal de supermercado:

```
APERTURA:  CAJA CENTRAL ──$1.000──► EFECTIVO (drawer)
  (tesorería entrega el fondo inicial al cajero — obligatorio declarar origen)

Durante el turno:
  Ventas ──────────────────────► EFECTIVO  (ingresos)
  Gastos/Pagos ◄──────────────── EFECTIVO  (egresos)
  Retiros: EFECTIVO ──────────► CAJA CENTRAL  (sangría)

CIERRE:    EFECTIVO ──$declarado──► CAJA CENTRAL
  (a la caja central entra EXACTAMENTE lo contado por el cajero)
  La diferencia contra lo esperado se asienta en DIFERENCIAS DE CAJA
  → EFECTIVO (drawer) queda SIEMPRE en $0
```

**Reglas de oro:**
- Ningún peso entra o sale del sistema sin asiento con contrapartida.
- Los saldos solo se corrigen con **Ajustes de cuenta** (documento con usuario, fecha y motivo).
- Un **turno cerrado es inmutable**: ni el turno ni sus operaciones pueden editarse o borrarse.

## 2. Cuentas del sistema

| Cuenta | Qué representa | Categoría |
|---|---|---|
| **Efectivo** (caja POS / drawer) | El dinero en mano del cajero durante el turno. Termina cada turno en $0. | `Efectivo` |
| **Caja Central** | El efectivo fuera de los turnos (tesorería / caja fuerte). Origen del fondo y destino del cierre. | `Efectivo` |
| **Diferencias de Caja** | Cuenta virtual que acumula faltantes (+) y sobrantes (−) de arqueo. Es el "ticket de diferencia". | `Otro` |
| **Mercado Pago** | Cobros por MP. Sus saldos de apertura/cierre de turno son informativos. | `Transferencia Bancaria` |
| **Fiado** | Crédito de clientes (cuenta corriente): registra deuda por cobrar, no dinero físico. | `Cuenta Corriente` |

`python manage.py init_system` crea todo esto y lo vincula en la Configuración automáticamente.

## 3. Configuración inicial

### En Admin → Core → Configuración → "Tesorería — Cuentas del sistema"

| Campo | Valor sugerido |
|---|---|
| **Cuenta caja POS (drawer)** | `Efectivo` |
| **Cuenta caja central** | `Caja Central` |
| **Cuenta diferencias de caja** | `Diferencias de Caja` |
| **Cuenta Mercado Pago** | `Mercado Pago` |

### En "POS — Apertura de caja"

| Campo | Valor sugerido |
|---|---|
| **Cuenta de origen por defecto** | `Caja Central` |
| **Cajero puede cambiar cuenta de origen** | según preferencia (si se desactiva, siempre usa el default) |

### Carga inicial de dinero

La Caja Central arranca en $0. El dinero real se declara **una sola vez** con un
**Ajuste de cuenta** (Admin → Tesorería → Ajustes de cuenta): monto positivo
sobre `Caja Central` con descripción (ej: "Carga inicial de tesorería").
Desde ahí, todo se mueve por asientos automáticos.

### Validaciones del sistema (apertura)

- Si se declara efectivo inicial, la **cuenta de origen es obligatoria**.
- La cuenta de origen debe ser de tipo `Efectivo` y **no puede ser el propio drawer**.
- El fondo inicial **no puede superar el saldo real** de la cuenta de origen
  (no se puede sacar plata que no existe → no hay saldos ficticios).

## 4. Flujo de apertura de turno

### Lo que hace el cajero en el POS

1. Presiona **Abrir turno**
2. Ingresa el **fondo inicial en efectivo** (ej: $1.000)
3. Selecciona **de qué cuenta sale** (default: Caja Central)
4. Opcionalmente declara el saldo de **Mercado Pago** (informativo)

### Lo que genera el sistema

| # | Cuenta | Tipo | Signo | Monto |
|---|---|---|---|---|
| 1 | CAJA CENTRAL | Apertura de caja | **EGRESO** | $1.000 |
| 2 | EFECTIVO | Apertura de caja | **INGRESO** | $1.000 |

> Doble asiento balanceado, con fecha estable (la de apertura del turno).

## 5. Flujo de cierre de turno

### Lo que hace el cajero en el POS

1. Presiona **Cerrar turno**
2. Cuenta el efectivo físico y lo ingresa como **saldo final declarado**
3. Si hay diferencia contra lo esperado, el POS **exige un motivo** (queda en el asiento y en el PDF)
4. Declara el saldo de Mercado Pago (informativo, para el control del reporte)

### Lo que genera el sistema

Ejemplo: esperado $1.800 (fondo $1.000 + ventas $800), declarado $1.500 → faltante $300:

| # | Cuenta | Tipo | Signo | Monto |
|---|---|---|---|---|
| 1 | EFECTIVO | Cierre — devolución | **EGRESO** | $1.500 (lo declarado) |
| 2 | CAJA CENTRAL | Cierre — devolución | **INGRESO** | $1.500 (lo declarado) |
| 3 | EFECTIVO | Diferencia de arqueo | **EGRESO** | $300 (faltante) |
| 4 | DIFERENCIAS DE CAJA | Diferencia de arqueo | **INGRESO** | $300 (a regularizar) |

> **A la Caja Central entra exactamente lo contado.** El drawer queda en $0.
> El faltante no desaparece: queda visible en Diferencias de Caja con turno,
> cajero, fecha y motivo. Con sobrante, los signos se invierten.

## 6. Diferencias de arqueo

- La cuenta **Diferencias de Caja** es el registro acumulado de faltantes/sobrantes
  (saldo positivo = plata faltante pendiente de explicación).
- Cada asiento lleva: turno, cajero, fecha y el **motivo escrito por el cajero**.
- El gerente la revisa periódicamente y la **regulariza con un Ajuste de cuenta**
  (ej: "Se asume pérdida faltante turno #12" con monto negativo), dejando el
  rastro documental completo.

## 7. Trazabilidad de cuentas

| Evento | Cuenta | Signo |
|---|---|---|
| Apertura | CAJA CENTRAL / EFECTIVO | EGRESO / INGRESO |
| Venta en efectivo | EFECTIVO | INGRESO |
| Venta en tarjeta / MP | TARJETA / MERCADO PAGO | INGRESO |
| Venta fiada (CC) | FIADO | INGRESO (crédito por cobrar) |
| Cobro de deuda | medio real + FIADO | INGRESO real / EGRESO CC |
| Gasto / pago proveedor (efectivo) | EFECTIVO | EGRESO |
| Compra fiada a proveedor (CC) | FIADO/CC proveedor | EGRESO (deuda por pagar) |
| Retiro (sangría) | EFECTIVO / CAJA CENTRAL | EGRESO / INGRESO |
| Cierre — devolución | EFECTIVO / CAJA CENTRAL | EGRESO / INGRESO (declarado) |
| Diferencia de arqueo | EFECTIVO / DIFERENCIAS | según faltante o sobrante |
| Ajuste de cuenta | la cuenta elegida | según signo del monto |

### Ejemplo de turno completo

```
Estado inicial: CAJA CENTRAL = $5.000 (cargada por Ajuste), EFECTIVO = $0

→ Apertura ($1.000):        CENTRAL $4.000 | EFECTIVO $1.000
→ Venta $500 efectivo:                       EFECTIVO $1.500
→ Gasto $200 efectivo:                       EFECTIVO $1.300
→ Retiro $300:              CENTRAL $4.300 | EFECTIVO $1.000
→ Cierre (declara $1.000):  CENTRAL $5.300 | EFECTIVO $0   ✓ sin diferencia

Total del sistema: $5.300 = $5.000 iniciales + $500 venta − $200 gasto ✓
```

## 8. Inmutabilidad y correcciones

- **Turno cerrado = congelado.** El sistema bloquea (a nivel de modelo, admin y
  API) crear, editar o borrar el turno y sus operaciones (ventas, gastos,
  cobros, retiros, pagos, adelantos). En el admin quedan en modo solo-lectura.
- **¿Cómo corrijo un error detectado después del cierre?** Con un
  **Ajuste de cuenta** sobre la cuenta afectada, describiendo el motivo. Nunca
  editando la operación original.
- **Excepción documentada:** la anulación de un *adelanto de cliente* (acción
  del admin con evento de auditoría propio) sigue permitida.

### Señales de alerta

| Síntoma | Causa probable |
|---|---|
| EFECTIVO no queda en $0 tras un cierre | Turno legacy (anterior a la refactorización) sin cuenta de origen |
| Saldo creciente en DIFERENCIAS DE CAJA | Faltantes recurrentes → revisar motivos por turno y cajero |
| No me deja abrir caja ("saldo insuficiente") | La Caja Central no tiene el fondo cargado → registrar el efectivo real con un Ajuste de cuenta |

## 9. Preguntas frecuentes

**¿Puedo abrir caja sin indicar de dónde sale el dinero?**
Solo si el fondo inicial es $0. Si declarás efectivo, el origen es obligatorio —
así es imposible crear saldos ficticios.

**¿Qué pasa si el cajero declara mal el saldo final?**
La diferencia queda asentada en Diferencias de Caja con su motivo, y a la Caja
Central entra lo declarado. El gerente regulariza con un Ajuste de cuenta.

**¿Mercado Pago genera movimientos en la apertura/cierre?**
No. `saldo_inicial_mercado_pago` y `saldo_final_mercado_pago` son informativos:
el PDF de cierre muestra saldo inicial → movimientos → declarado → diferencia.
Los cobros reales por MP se asientan como ventas en la cuenta Mercado Pago.

**¿Qué pasa si se intenta editar un turno cerrado?**
El sistema lo rechaza (`PermissionDenied`) y el admin lo muestra solo-lectura.
Las correcciones van por Ajustes de cuenta.

**¿Puedo tener más de una caja?**
Cada cajero abre su propio turno. Todos comparten el mismo drawer configurado
(`cuenta_caja_pos`); los saldos por cajero se ven por separado en el POS.
