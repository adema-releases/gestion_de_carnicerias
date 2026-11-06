---
titulo: Documentación de Gestión de Carnicerías
seo_title: Manual de Gestión de Carnicerías: tutoriales paso a paso
seo_description: Aprendé a usar el sistema de la carnicería por puesto: mostrador, caja, recepción, liquidación, gerente y central, con capturas y lenguaje simple.
palabras_clave: [manual sistema carnicería, tutoriales, mostrador, caja, liquidación semanal]
rol: todos
modulo: general
permiso: ninguno
estado: verificado
verificado: 2026-11-03 (estructura); cada tutorial lleva su propia fecha
version_sistema: 0.0.1
---

# Documentación de Gestión de Carnicerías

> **Para quién es:** el frigorífico, los gerentes de sucursal, las cajeras y los carniceros.  **Qué encontrás:** tutoriales paso a paso con capturas, organizados **por puesto**, y las ideas que explican el negocio.

Gestión de Carnicerías es el sistema de **un frigorífico con sus propias carnicerías**. Cada carnicería pesa y arma comandas en el **mostrador**, cobra en la **caja**, recibe y desposta la carne en **recepción** y cada martes hace la **liquidación** de kilos. El frigorífico controla todas las sucursales desde la **central**. Funciona **sin internet** en cada local.

Los tutoriales están en **lenguaje simple**, con capturas que llevan **flechas y números** explicados en el texto, y fueron **verificados contra el código** del sistema.

> 中文版: [../zh/README.md](../zh/README.md)

## Por dónde empezar

| Soy… | Empiezo por… |
|---|---|
| **Nuevo**, no conozco el sistema | [Empezá acá: qué es y quién hace qué](00-inicio/README.md) |
| **Carnicero** (ayudante u oficial) | 01 Ingresar → 03 Armar una comanda → 04 Anular → 15 Contar en la liquidación |
| **Cajera** | 01 Ingresar → 05 Abrir la caja → 06 Cobrar una comanda → 10 Cerrar la caja |
| **Oficial** en recepción | 11 Recibir el despacho → 13 Despostar → 15–16 Liquidación |
| **Gerente** de sucursal | 18 Alta de personal → 19 Puestos y cámaras → 20 Medios de pago → 22 Controles de la semana |
| **Frigorífico** | 23 Panel central → 24 Despachar → 25 Cuenta corriente → 26 Catálogo |

## Cómo está organizada

| Carpeta | Contenido | Para quién |
|---|---|---|
| [`00-inicio/`](00-inicio/README.md) | La idea del negocio, los puestos, quién hace qué, un día en la sucursal, glosario | Todos |
| [`01-manual-usuario/`](01-manual-usuario/) | **Tutoriales paso a paso con capturas**, por puesto | Todos |
| [`02-referencia/`](02-referencia/README.md) | Permisos por rol, estados y reglas de cada módulo | Gerente, soporte |
| [`03-conceptos/`](03-conceptos/README.md) | Comanda y venta, desposte y merma, balance de kilos, sincronización | Todos |
| [`04-operacion/`](04-operacion/README.md) | Instalación, sincronización, impresora, respaldos | Soporte |
| [`05-faq/`](05-faq/README.md) | Problemas frecuentes, por tema | Todos |

## Tutoriales

Estado: 🔲 pendiente · 🟡 borrador · ✅ verificado contra el código y con capturas.

<!-- TUTORIALES:INICIO -->
### A · Para empezar
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 01 | [Ingresar al sistema y elegir el puesto del dispositivo](01-manual-usuario/01-ingresar-y-elegir-puesto.md) | Todos | ✅ |
| 02 | [Cambiar el idioma: español o chino](01-manual-usuario/02-cambiar-idioma.md) | Todos | ✅ |

### B · Mostrador
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 03 | [Armar una comanda y mandarla a caja](01-manual-usuario/03-armar-una-comanda.md) | Carnicero | ✅ |
| 04 | [Mis comandas del día y cómo anular una](01-manual-usuario/04-mis-comandas-y-anular.md) | Carnicero | ✅ |

### C · Caja
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 05 | [Abrir la caja](01-manual-usuario/05-abrir-la-caja.md) | Cajera | ✅ |
| 06 | [Cobrar una comanda](01-manual-usuario/06-cobrar-una-comanda.md) | Cajera | ✅ |
| 07 | [Vender por unidad y cobrar con dos medios de pago](01-manual-usuario/07-venta-por-unidad-y-pago-dividido.md) | Cajera | ✅ |
| 08 | [Fiado: vender a cuenta corriente y cobrar la deuda](01-manual-usuario/08-fiado-y-cobro-de-deuda.md) | Cajera | ✅ |
| 09 | [Gastos y retiros de efectivo](01-manual-usuario/09-gastos-y-retiros.md) | Cajera | ✅ |
| 10 | [Cerrar la caja](01-manual-usuario/10-cerrar-la-caja.md) | Cajera | ✅ |

### D · Recepción y cámara
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 11 | [Recibir un despacho del frigorífico](01-manual-usuario/11-recibir-despacho-del-frigorifico.md) | Oficial y ayudante | ✅ |
| 12 | [Recibir mercadería de otro proveedor](01-manual-usuario/12-recibir-de-otro-proveedor.md) | Oficial y ayudante | ✅ |
| 13 | [La cámara: mover y despostar una media res](01-manual-usuario/13-camara-y-desposte.md) | Oficial | ✅ |
| 14 | [Ver el stock por corte](01-manual-usuario/14-ver-el-stock.md) | Oficial, ayudante y gerente | ✅ |

### E · Conteo y liquidación
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 15 | [Liquidación semanal: contar lo que queda y lo que se tira](01-manual-usuario/15-liquidacion-semanal-contar.md) | Ayudante y oficial | ✅ |
| 16 | [Ver las diferencias y cerrar la liquidación](01-manual-usuario/16-liquidacion-cerrar.md) | Oficial y gerente | ✅ |
| 17 | [Conteo de control e historial](01-manual-usuario/17-conteo-de-control.md) | Oficial y gerente | ✅ |

### F · Gerente de sucursal
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 18 | [Dar de alta a una persona: usuario, rol y puestos](01-manual-usuario/18-alta-de-personal.md) | Gerente | ✅ |
| 19 | [Puestos, cámaras y datos de la sucursal](01-manual-usuario/19-puestos-camaras-y-configuracion.md) | Gerente | ✅ |
| 20 | [Qué medios de pago usa cada cajera](01-manual-usuario/20-medios-de-pago-de-la-cajera.md) | Gerente | ✅ |
| 21 | [Dashboard financiero y reportes](01-manual-usuario/21-dashboard-y-reportes.md) | Gerente | ✅ |
| 22 | [Controles de la semana: caja, comandas anuladas y mermas](01-manual-usuario/22-controles-de-la-semana.md) | Gerente | ✅ |

### G · Central del frigorífico
| # | Tutorial | Puesto | Estado |
|---|---|---|---|
| 23 | [El panel de la central: cómo viene cada sucursal](01-manual-usuario/23-panel-central.md) | Frigorífico | ✅ |
| 24 | [Despachar mercadería a una sucursal](01-manual-usuario/24-despachar-a-una-sucursal.md) | Frigorífico | ✅ |
| 25 | [Cuenta corriente de cada sucursal: remesas y ajustes](01-manual-usuario/25-cuenta-corriente-de-sucursales.md) | Frigorífico | ✅ |
| 26 | [Catálogo: productos, precios, fotos y plantillas de despiece](01-manual-usuario/26-catalogo-precios-y-plantillas.md) | Frigorífico | ✅ |
| 27 | [Abrir una sucursal nueva](01-manual-usuario/27-abrir-una-sucursal-nueva.md) | Frigorífico | ✅ |
<!-- TUTORIALES:FIN -->

## Para quien mantiene esta documentación
- Las capturas se generan con scripts sobre una **base de demostración con datos inventados**. Si cambia una pantalla, se corre el script y las imágenes (en español y en chino) se rehacen solas. Ver [`../_herramientas/README.md`](../_herramientas/README.md).
- [Guía de estilo](../_guia-de-estilo.md) · [Plantilla de tutorial](../_plantilla-tutorial.md) · [Hallazgos del código](../_hallazgos.md).
