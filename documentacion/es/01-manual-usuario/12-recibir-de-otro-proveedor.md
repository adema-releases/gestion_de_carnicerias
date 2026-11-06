---
titulo: Recibir mercadería de otro proveedor
seo_title: Recibir mercadería de otro proveedor con su remito
seo_description: Cargá lo que llega de un proveedor que no es el frigorífico (pollo, embutidos): proveedor, número de remito, foto y productos.
palabras_clave: [recibir mercadería, remito de proveedor, cargar remito, recepción]
slug: recibir-de-otro-proveedor
grupo: D · Recepción y cámara
rol: carnicero oficial, ayudante y gerente
modulo: Recepción (Recibir)
permiso: Recibir mercadería
estado: verificado
verificado: 2026-11-03 contra pos/recepcion_views.py (api_remito_crear) y pos/templates/pos/recepcion.html
version_sistema: 0.0.1
---

# Recibir mercadería de otro proveedor

> **Para quién es:** oficial, ayudante y gerente.  **Tiempo:** 2 minutos.

Cuando llega mercadería de **otro proveedor** (por ejemplo, la granja de pollos), en **Recibir** elegís el **proveedor**, escribís el **número de remito**, cargás cada **producto** con su cantidad y tocás **Confirmar recepción**.

## Para qué sirve
Todo lo que entra tiene que sumar stock. Si no se carga, el martes en la liquidación parece que «sobra» mercadería.

## Paso a paso

### 1. Cargá el remito
![Formulario de recepción con proveedor, número de remito, foto del remito, producto, botón Agregar y productos cargados](imagenes/12-recibir-de-otro-proveedor/01-remito-de-otro-proveedor.png)

1. **Proveedor:** elegilo de la lista.
2. **Número de remito:** el que figura en el papel.
3. **Foto del remito:** sacale foto al papel (opcional, pero recomendable).
4. **Producto:** buscalo y escribí la **cantidad** al lado.
5. Tocá **Agregar**. Repetí con cada producto.
6. **Lo que llegó:** revisá la lista. Quitá con **✕** lo que esté mal.

Si llegan medias reses de este proveedor, tocá **Media res colgada** y pesalas como en el [tutorial 11](11-recibir-despacho-del-frigorifico.md).

Al final, tocá **Confirmar recepción**.

### 2. El remito queda registrado
![Últimos remitos con el remito de la granja arriba de todo](imagenes/12-recibir-de-otro-proveedor/02-remito-recibido.png)

1. Aparece primero en **Últimos remitos**.

## Qué pasa por detrás
- Cada producto suma su cantidad al **stock**.
- El remito queda guardado con la foto, quién lo recibió y cuándo.

## Problemas frecuentes
| Si te pasa… | Es porque… | Qué hacer |
|---|---|---|
| «Elegí un producto de la lista» | El nombre no coincide con ningún producto | Escribí parte del nombre y elegilo de la lista |
| «Ingresá la cantidad» | La cantidad está vacía o en 0 | Escribí la cantidad, con coma si hace falta: `12,5` |
| No está el proveedor | No está cargado | El gerente lo carga en *Compras → Proveedores* |
| **Confirmar recepción** no se activa | No cargaste nada | Agregá al menos un producto o una media |

## Preguntas frecuentes

### ¿Acá se paga al proveedor?
No. Recibir solo registra la mercadería. El pago lo hace el gerente desde la caja con **Pago proveedor**.

## Siguiente paso
- [Ver el stock por corte](14-ver-el-stock.md).
