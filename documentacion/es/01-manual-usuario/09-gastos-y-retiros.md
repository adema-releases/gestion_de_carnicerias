---
titulo: Gastos y retiros de efectivo
seo_title: Registrar gastos y retiros de efectivo en la caja
seo_description: Anotá lo que se paga con plata de la caja (bolsas, limpieza, flete) y el efectivo que sale hacia la caja central. Así el cierre da justo.
palabras_clave: [registrar gasto, retiro de efectivo, caja chica, egresos de caja]
slug: gastos-y-retiros
grupo: C · Caja
rol: cajera
modulo: Caja (gastos y retiros)
permiso: Registrar gasto · Retirar efectivo
estado: verificado
verificado: 2026-11-03 contra pos/views.py (api_gasto, api_retiro) y pos/templates/pos/terminal.html
version_sistema: 0.0.1
---

# Gastos y retiros de efectivo

> **Para quién es:** la cajera.  **Tiempo:** 30 segundos.

Si pagás algo con plata de la caja (bolsas, limpieza, un flete), tocá **Gasto**. Si sacás efectivo de la caja para llevarlo a la caja central, tocá **Retiro**. Las dos cosas restan del efectivo que tiene que haber al cerrar.

## Para qué sirve
Si no se anota, al cerrar la caja falta plata y no se sabe por qué. Anotado, el cierre da justo y el gerente ve en qué se gastó.

## Paso a paso

### 1. Registrá un gasto
Tocá **Gasto**.

![Ventana Registrar Gasto con importe, descripción, categoría, medio de pago y Registrar](imagenes/09-gastos-y-retiros/01-registrar-gasto.png)

1. **Importe:** cuánto se pagó.
2. **Descripción:** qué se pagó, por ejemplo «Bolsas camiseta».
3. **Categoría:** Bolsas y envases, Limpieza, Flete… (opcional).
4. **Medio de pago:** de dónde salió la plata (normalmente Efectivo).
5. Tocá **Registrar**.

### 2. Registrá un retiro
Tocá **Retiro**.

![Ventana Retiro de Efectivo con el importe, la descripción y Retirar](imagenes/09-gastos-y-retiros/02-registrar-retiro.png)

1. **Importe:** el efectivo que sale.
2. **Descripción:** el motivo (opcional).
3. Tocá **Retirar**.

### 3. Revisá las operaciones del turno
![Operaciones del turno con el retiro, el gasto, el botón para ver el detalle y los filtros por tipo](imagenes/09-gastos-y-retiros/03-operaciones-del-turno.png)

1. El **retiro**.
2. El **gasto**.
3. **👁:** abre el detalle (y permite reimprimir).
4. **Filtros:** muestran solo ventas, gastos, retiros, cobros…

## Qué pasa por detrás
- El gasto queda en el turno y en los reportes del gerente por categoría.
- El retiro siempre es en **efectivo**.
- Los dos bajan el **efectivo esperado** al cerrar.

## Problemas frecuentes
| Si te pasa… | Es porque… | Qué hacer |
|---|---|---|
| No aparece el botón **Gasto** o **Retiro** | No tenés ese permiso | Pedíselo al gerente |
| No aparece **Pago proveedor** | Ese botón es del gerente | Avisale al gerente |
| Me equivoqué de importe | — | Avisale al gerente: se corrige con un ajuste ([tutorial 22](22-controles-de-la-semana.md)) |

## Preguntas frecuentes

### ¿El pago al proveedor de mercadería es un gasto?
No. Es **Pago proveedor**, un botón que tiene el gerente. Queda en la cuenta del proveedor.

## Siguiente paso
- [Cerrar la caja](10-cerrar-la-caja.md).
