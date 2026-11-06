---
titulo: Dashboard financiero y reportes
seo_title: Dashboard financiero de la carnicería y reportes PDF y Excel
seo_description: Mirá ventas, compras, fiado y gastos por período, compará con el período anterior y exportá el reporte a PDF o Excel.
palabras_clave: [dashboard financiero, reporte de ventas, exportar excel, reporte pdf]
slug: dashboard-y-reportes
grupo: F · Gerente de sucursal
rol: gerente
modulo: Dashboard · Admin
permiso: superusuario
estado: verificado
verificado: 2026-11-03 contra dashboard/views.py, dashboard/services.py y gestion_de_carnicerias/admin_override.py
version_sistema: 0.0.1
---

# Dashboard financiero y reportes

> **Para quién es:** el gerente (superusuario).  **Tiempo:** 5 minutos.

El botón **Dash** de la caja abre el **dashboard financiero**: ventas, compras, cuentas corrientes y gastos del período, comparados con el período anterior. Se exporta a **PDF** o **Excel**. El **panel de control** del admin tiene otro resumen con filtro por cajero.

## Para qué sirve
Ver de un vistazo cuánto se vendió, cuánto se fió, cuánto se cobró y en qué se gastó, sin sumar tickets a mano.

## Paso a paso

### 1. Abrí el dashboard
![Encabezado de la caja con el botón Dash](imagenes/21-dashboard-y-reportes/01-boton-dash.png)

1. **Dash**: solo lo ven los superusuarios.

### 2. Elegí el período y exportá
![Dashboard general con los períodos rápidos y los botones Exportar PDF y Exportar Excel](imagenes/21-dashboard-y-reportes/02-dashboard.png)

1. **Período:** Mes actual, Últimos 7 días, Últimos 30 días, Mes anterior, o fechas a mano + **Aplicar período**.
2. **Exportar PDF.**
3. **Exportar Excel.**

### 3. Leé cada panel
![Panel de ventas con el gráfico diario y las tarjetas de venta total, fiado, cobrado directo y deuda cobrada](imagenes/21-dashboard-y-reportes/03-panel-de-ventas.png)

Hay cuatro paneles: **Ventas**, **Compras**, **Cuentas corrientes** y **Gastos**. Cada uno tiene la evolución día por día y tarjetas con el total y la comparación con el período anterior. Abajo de cada panel, el **Top 10** (clientes, proveedores, saldos o gastos).

### 4. El panel de control del admin
En el admin, **Panel de control**.

![Panel de control del admin con los filtros, Excel y PDF](imagenes/21-dashboard-y-reportes/04-panel-del-admin.png)

1. **Filtrar** por fechas y por cajero.
2. **Excel.**
3. **PDF.**

## Qué pasa por detrás
- Los dos tableros usan el mismo cálculo: no pueden mostrar números distintos para lo mismo.
- El dashboard funciona sin internet.
- Los PDF y Excel salen siempre en español.

## Preguntas frecuentes

### ¿Dónde está el PDF de cada cierre de caja?
En **Ventas → Turnos de caja**, columna **Cierre PDF** ([tutorial 22](22-controles-de-la-semana.md)).

### ¿El dashboard muestra los kilos y la merma?
No: es financiero. Los kilos y la merma están en la [liquidación](16-liquidacion-cerrar.md) y en el [panel de la central](23-panel-central.md).

## Siguiente paso
- [Controles de la semana](22-controles-de-la-semana.md).
