---
titulo: Qué medios de pago usa cada cajera
seo_title: Asignar medios de pago a cada cajera
seo_description: Definí con qué medios cobra cada cajera (Efectivo, Mercado Pago, Fiado) para que no vea las cuentas internas de la tesorería.
palabras_clave: [medios de pago, asignar medios a cajera, mercado pago, tesorería]
slug: medios-de-pago-de-la-cajera
grupo: F · Gerente de sucursal
rol: gerente
modulo: Admin · Tesorería
permiso: superusuario
estado: verificado
verificado: 2026-11-03 contra tesoreria/models.py (medios_permitidos_para, AsignacionMedioPagoCajero) y pos/views.py (_check_medio)
version_sistema: 0.0.1
---

# Qué medios de pago usa cada cajera

> **Para quién es:** el gerente.  **Tiempo:** 2 minutos.

En **Tesorería → Asignaciones de medios de pago a cajeros** elegís con qué medios cobra cada cajera. Lo normal: **Efectivo**, **Mercado Pago** y **Fiado**.

## Para qué sirve
La tesorería tiene cuentas internas (Caja Central, Diferencias de Caja) que no son para cobrar. Si la cajera no tiene asignaciones, ve **todas**, incluidas esas.

## Paso a paso

### 1. Los medios de pago
**Tesorería → Medios de pago**.

![Lista de medios de pago y cuentas](imagenes/20-medios-de-pago-de-la-cajera/01-medios-de-pago.png)

1. Los **medios y cuentas**: Efectivo, Mercado Pago, Fiado y las cuentas internas.

### 2. Las asignaciones
**Tesorería → Asignaciones de medios de pago a cajeros**.

![Lista de asignaciones con usuario, medio y activo](imagenes/20-medios-de-pago-de-la-cajera/02-asignaciones.png)

1. **Quién usa qué medio.**
2. **Añadir** una asignación.

### 3. Asigná un medio
![Formulario con la cajera, el medio de pago y la casilla Activo](imagenes/20-medios-de-pago-de-la-cajera/03-nueva-asignacion.png)

1. **Usuario:** la cajera.
2. **Medio de pago.**
3. **Activo:** tildado. Destildalo para quitarle ese medio sin borrar la asignación.

Repetí con cada medio.

## Qué pasa por detrás
- En la caja, la cajera ve solo sus medios activos. Si intenta usar otro, el sistema lo rechaza.
- El gerente (superusuario) ve siempre todos.

## Preguntas frecuentes

### ¿Cómo agrego un medio nuevo, por ejemplo tarjeta de débito?
En **Medios de pago → Añadir**, con su **categoría** (Tarjeta de Crédito/Débito). Después asignáselo a la cajera.

## Siguiente paso
- [Dashboard financiero y reportes](21-dashboard-y-reportes.md).
