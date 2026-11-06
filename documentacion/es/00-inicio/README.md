---
titulo: Empezá acá: qué es Gestión de Carnicerías y quién hace qué
seo_title: Qué es Gestión de Carnicerías y quién hace cada tarea
seo_description: Conocé en diez minutos la idea del negocio, los puestos de la carnicería, qué hace cada persona, un día típico y el glosario básico del sistema.
palabras_clave: [sistema para carnicerías, frigorífico con sucursales, puestos de la carnicería, glosario]
rol: todos
modulo: general
permiso: ninguno
estado: verificado
verificado: 2026-11-03 contra core/roles.py, pos/puestos.py, core/sync.py, central/views.py y docs/MANUALES.md
version_sistema: 0.0.1
---

# Empezá acá: qué es Gestión de Carnicerías y quién hace qué

> **Para quién es:** cualquiera que va a usar el sistema por primera vez.  **Tiempo:** 10 minutos.

Gestión de Carnicerías es el sistema de **un frigorífico que tiene sus propias carnicerías**. En cada carnicería se pesa y se vende la carne, se cobra, se recibe la mercadería y se controla cuánto queda. El frigorífico ve desde su oficina cómo viene cada carnicería.

## La idea del negocio

```
           FRIGORÍFICO (la central)
   compra la hacienda, faena y despacha
                    │
   medias reses, pollo, embutidos… ──► se las "vende" a cada sucursal (cuenta corriente)
                    │
     ┌──────────────┼──────────────┐
  Sucursal Centro  Sucursal Norte  Sucursal Sur      ← cada una es una carnicería
     │                                               dentro de un supermercado
     ├─ Recepción: recibe, cuelga y desposta la carne
     ├─ Mostrador: pesa los cortes y arma la comanda
     ├─ Caja: cobra la comanda al cliente
     └─ Cada martes: liquidación (cuenta lo que quedó)
```

- **El frigorífico** manda la mercadería (sobre todo **medias reses**) y la anota como deuda de la sucursal. La sucursal le va pagando con **remesas**.
- **La sucursal** convierte cada media res en cortes (**desposte**), los vende por kilo y cobra.
- Lo que importa controlar es **la plata** (que la caja cierre) y **los kilos** (que no se pierda carne entre lo que entra y lo que se vende). Por eso, una vez por semana, se cuenta todo: es la **liquidación**.

> **Sin internet también se vende.** Cada carnicería tiene su PC con el sistema instalado. La PC se sincroniza sola con el frigorífico cada minuto; si se corta internet, la carnicería sigue trabajando y sube todo cuando vuelve la conexión.

## Los puestos de la carnicería

Cada **dispositivo** (PC, tablet o celular) se configura como un **puesto**. El puesto decide qué pantalla aparece.

| Puesto | Dónde está | Qué se hace | Quién lo usa |
|---|---|---|---|
| **Mostrador** | Tablet o celular en el mostrador | Pesar los cortes, armar la **comanda** y mandarla a caja. **No se cobra** | Carnicero ayudante y oficial |
| **Caja** | PC de la caja | Abrir y cerrar la caja, **cobrar** comandas, vender por unidad, fiado, gastos y retiros | Cajera |
| **Recepción** | PC o tablet cerca de la cámara | **Recibir** la mercadería, colgar y **despostar** las medias reses, ver **stock** y **contar** | Oficial, ayudante y gerente |
| **Admin** | Cualquier PC, desde el navegador | Personal, puestos, medios de pago, reportes | Gerente |
| **Panel central** | Oficina del frigorífico | Ver todas las sucursales, despachar, cuenta corriente, catálogo y precios | Frigorífico |

## Quién puede hacer qué

| Rol | Puede | No puede |
|---|---|---|
| **Carnicero ayudante** | Armar y anular sus comandas, recibir mercadería, ver stock, contar | Cobrar, despostar, cerrar conteos |
| **Carnicero oficial** | Lo del ayudante, más despostar, anular comandas de otros, cerrar conteos y liquidaciones | Cobrar |
| **Cajera** | Abrir y cerrar la caja, cobrar, gastos, retiros, fiado y cobro de deudas | Recepción, stock y conteos |
| **Gerente de sucursal** | Todo lo anterior, más el admin y el dashboard | — |
| **Frigorífico** | Catálogo, precios, despachos y cuenta corriente de las sucursales | Tocar ventas o conteos de una sucursal |

Al elegir el **rol** de una persona, el sistema le carga estos permisos solo. Ver [Dar de alta a una persona](../01-manual-usuario/18-alta-de-personal.md).

## Un día en la sucursal

| Momento | Mostrador | Caja | Recepción |
|---|---|---|---|
| Antes de abrir | — | [Abre la caja](../01-manual-usuario/05-abrir-la-caja.md) | [Recibe el despacho](../01-manual-usuario/11-recibir-despacho-del-frigorifico.md), cuelga y [desposta](../01-manual-usuario/13-camara-y-desposte.md) |
| **Martes**, antes de abrir | Ayuda a contar | — | [Liquidación](../01-manual-usuario/15-liquidacion-semanal-contar.md): cuenta, [cierra](../01-manual-usuario/16-liquidacion-cerrar.md) y recién después recibe la carne nueva |
| Durante el día | [Pesa y manda comandas](../01-manual-usuario/03-armar-una-comanda.md) | [Cobra comandas](../01-manual-usuario/06-cobrar-una-comanda.md) y lo que se vende por unidad | Desposta según haga falta |
| Al cerrar | — | [Cuenta la plata y cierra la caja](../01-manual-usuario/10-cerrar-la-caja.md) | — |

## Cómo viaja una venta

1. El carnicero **pesa** 1,350 kg de vacío en el mostrador y lo agrega a la **comanda**.
2. Toca **Enviar a caja**: el sistema le da un **número** (por ejemplo #19) y se lo dice al cliente.
3. El cliente va a la caja y dice «la 19». La cajera la **trae** con un toque, cobra y entrega el ticket.
4. Esos kilos **bajan del stock** del corte.
5. El martes, en la **liquidación**, se compara lo que debería quedar con lo que realmente quedó.
6. Todo eso **sube al frigorífico**, que lo ve en su panel.

## Glosario

| Palabra | Qué significa |
|---|---|
| **Frigorífico / central** | La empresa dueña. Despacha la mercadería y controla todas las sucursales |
| **Sucursal** | Cada carnicería, en un local dentro de un supermercado |
| **Puesto** | El papel de un dispositivo: Caja, Mostrador o Recepción |
| **Comanda** | El pedido que arma el carnicero en el mostrador, con los cortes pesados. Se cobra en caja |
| **Venta** | La comanda (o lo que sea) ya cobrada en caja |
| **Media res** | La mitad de un animal faenado, como llega del frigorífico. Se cuelga en la cámara |
| **Garrón / tropa** | El código que identifica a cada media res |
| **Desposte** | Cortar una media res en sus cortes (asado, vacío, nalga…) |
| **Plantilla de despiece** | Los porcentajes que da cada corte de una media res. Ejemplo: asado de tira 15 % |
| **Merma** | Kilos que se pierden: hueso y grasa que no se venden, lo que se tira y lo que falta al contar |
| **Cámara** | Cámara frigorífica, exhibidora o freezer donde está la carne |
| **Remito** | El papel con lo que llegó. El del frigorífico se llama **despacho** |
| **Stock** | Lo que **debería** haber de cada producto según el sistema |
| **Conteo** | Contar lo que hay de verdad. Puede ser de **control** o la **liquidación semanal** |
| **Liquidación** | El conteo completo de cada martes, que cierra el **balance de kilos** de la semana |
| **Turno de caja** | El período entre que se abre y se cierra la caja |
| **Medio de pago** | Efectivo, Mercado Pago, Fiado… |
| **Fiado / cuenta corriente** | Vender a un cliente conocido que paga después |
| **Remesa** | La plata que la sucursal le manda al frigorífico |
| **Sincronización** | El intercambio automático de datos entre la PC de la sucursal y la central, cada minuto |

## Siguiente paso

- Todos: [Ingresar al sistema y elegir el puesto](../01-manual-usuario/01-ingresar-y-elegir-puesto.md).
- Las ideas de fondo (merma, balance de kilos, sincronización): [Conceptos clave](../03-conceptos/README.md).
- Si algo no funciona: [Preguntas frecuentes](../05-faq/README.md).

## Usuarios de la demostración

Las capturas se sacaron sobre una **base de demostración con datos inventados** (precios, clientes y ventas de ejemplo). Clave de todos: `Carne1234`.

| Usuario | Persona | Rol | Puestos |
|---|---|---|---|
| `gerente1` | Gabriela Gerente | Gerente de sucursal | Todos |
| `cajera1` | Carla Cajera | Cajera | Caja 1 |
| `oficial1` | Oscar Oficial | Carnicero oficial | Mostrador 1 y 2, Recepción |
| `ayudante1` | Andrés Ayudante | Carnicero ayudante | Mostrador 1 y 2 |
| `frigorifico` | Federico Frigorífico | Central (solo en la base de la central) | — |
