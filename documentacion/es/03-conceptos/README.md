---
titulo: Conceptos clave de Gestión de Carnicerías
seo_title: Conceptos clave: comanda, desposte, merma y balance de kilos
seo_description: Las ideas que explican todo el sistema: de la comanda a la venta, del desposte a la merma, el balance de kilos semanal y la sincronización con la central.
palabras_clave: [merma carnicería, balance de kilos, desposte, sincronización sin internet]
rol: todos
modulo: comandas, recepción, liquidación, sincronización
permiso: ninguno
estado: verificado
verificado: 2026-11-03 contra ventas/models.py (Comanda), recepcion/models.py, recepcion/liquidacion.py, inventario/stock.py y core/sincronizacion.py
version_sistema: 0.0.1
---

# Conceptos clave

> **Para quién es:** todos.  **Tiempo:** 10 minutos.

Seis ideas explican casi todo lo que hace el sistema. Cada una remite a los tutoriales donde se usa.

## 1. Comanda y venta: el que pesa no cobra

- El carnicero arma la **comanda**: cortes pesados, con precio. Queda **abierta**.
- La cajera la **cobra**: se convierte en **venta** y la comanda pasa a **cobrada**.
- Si el cliente no paga, se **anula** (queda registrado quién y por qué).
- Una comanda se cobra **una sola vez**: si dos cajas la tocan a la vez, la segunda recibe un aviso.
- El **stock baja al cobrar**, no al armar la comanda.

→ [03 Armar una comanda](../01-manual-usuario/03-armar-una-comanda.md) · [04 Anular](../01-manual-usuario/04-mis-comandas-y-anular.md) · [06 Cobrar](../01-manual-usuario/06-cobrar-una-comanda.md)

## 2. De la media res a los cortes: el desposte

- El frigorífico manda **medias reses**. Al recibirlas se **pesan** (con foto del visor) y se **cuelgan** en una cámara.
- Al **despostar**, la **plantilla de despiece** reparte el peso entre los cortes:

  `kilos del corte = peso de la media × (1 − merma %) × % del corte`

  Ejemplo: media de 120 kg, merma 2 %, asado de tira 15 % → 120 × 0,98 × 0,15 = **17,64 kg** de asado.
- Si se pesan algunos cortes, se usan esos kilos reales; los demás, los de la plantilla.
- La **merma de desposte** es el peso de la media menos la suma de los cortes.

→ [11 Recibir](../01-manual-usuario/11-recibir-despacho-del-frigorifico.md) · [13 Despostar](../01-manual-usuario/13-camara-y-desposte.md) · [26 Plantillas](../01-manual-usuario/26-catalogo-precios-y-plantillas.md)

## 3. El stock es lo que *debería* haber

El stock de cada producto es la suma de sus movimientos:

| Suma | Resta |
|---|---|
| Recibido (productos) · Desposte (cortes) | Vendido · Tirado (merma) |

Más los **ajustes** que deja cada conteo. Lo que hay **de verdad** solo se sabe contando. Un stock **negativo** avisa un error: un desposte sin cargar, un corte vendido con otro nombre o mercadería que entró sin cargar.

→ [14 Ver el stock](../01-manual-usuario/14-ver-el-stock.md)

## 4. La liquidación y el balance de kilos

Cada semana (martes, antes de abrir y antes de recibir la carne nueva) se cuenta todo. Quien cuenta **no ve** lo esperado. Al cerrar, el sistema arma el **balance de kilos**:

```
  Había al cierre anterior
+ Recibido (medias y productos)
− Vendido
− Merma de desposte
− Se tiró
± Faltante o sobrante de conteo
= Queda
```

**Merma total** = merma de desposte + lo tirado + el faltante, en % de lo que hubo en la semana.

| Merma total | Lectura |
|---|---|
| Hasta 4 % | Normal |
| 4 % a 6 % | Atención (naranja en la central) |
| Más de 6 % | Problema (rojo): buscar la causa |

Al cerrar, el stock queda **igual a lo contado**. No se deshace.

→ [15 Contar](../01-manual-usuario/15-liquidacion-semanal-contar.md) · [16 Cerrar](../01-manual-usuario/16-liquidacion-cerrar.md) · [17 Control](../01-manual-usuario/17-conteo-de-control.md)

## 5. La caja: lo que entra, lo que sale y el arqueo

- El **turno** empieza con el efectivo inicial (que sale de la **Caja Central**).
- Cada venta suma en su medio de pago; gastos y retiros restan del efectivo.
- El **fiado** no es plata: es deuda del cliente. Cuando paga, entra plata y se cancela la deuda más vieja.
- Al cerrar, **efectivo contado − esperado** = diferencia, que va a la cuenta **Diferencias de Caja** con su motivo.
- Un turno cerrado no se modifica: los errores se corrigen con un **ajuste de cuenta**.

→ [05 Abrir](../01-manual-usuario/05-abrir-la-caja.md) · [08 Fiado](../01-manual-usuario/08-fiado-y-cobro-de-deuda.md) · [10 Cerrar](../01-manual-usuario/10-cerrar-la-caja.md) · [22 Controles](../01-manual-usuario/22-controles-de-la-semana.md)

## 6. Sucursal y central: cada dato tiene un solo dueño

- La **PC de cada sucursal** tiene el sistema completo y vende **sin internet**.
- Cada minuto, si hay internet, **sube** lo suyo y **baja** lo de la central.

| Lo escribe la central | Lo escribe cada sucursal |
|---|---|
| Productos, precios, fotos, rubros | Ventas, comandas, turnos de caja |
| Plantillas de despiece | Recepciones, despostes, stock |
| Despachos | Cámaras, conteos y liquidaciones |
| Cuenta corriente de cada sucursal | Personal y puestos |

- Un dato se cambia **solo donde se escribe**. Si una sucursal cambia un precio, ese cambio se pierde; si la central toca una venta, no llega a la sucursal.
- Cada sucursal se identifica con su **token**: la central solo acepta sus datos.

→ [23 Panel central](../01-manual-usuario/23-panel-central.md) · [27 Sucursal nueva](../01-manual-usuario/27-abrir-una-sucursal-nueva.md)
