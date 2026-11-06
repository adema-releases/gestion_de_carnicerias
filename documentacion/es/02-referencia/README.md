---
titulo: Referencia: permisos, estados y reglas
seo_title: Referencia del sistema: permisos por rol, estados y reglas
seo_description: Tabla completa de permisos por rol, estados de comandas, despachos, medias reses y conteos, y las reglas que aplica el sistema en cada módulo.
palabras_clave: [permisos por rol, estados del sistema, reglas de negocio, referencia]
rol: gerente | soporte
modulo: general
permiso: ninguno
estado: verificado
verificado: 2026-11-03 contra core/roles.py, core/models.py, ventas/models.py, recepcion/models.py y central/models.py
version_sistema: 0.0.1
---

# Referencia: permisos, estados y reglas

> **Para quién es:** el gerente y soporte. Los pasos de pantalla están en los [tutoriales](../01-manual-usuario/).

## Permisos por rol

Al elegir el rol de una persona, se cargan estos permisos. Después se pueden ajustar a mano en *Permisos de cajero*; si se cambia el rol, vuelven a los del rol nuevo.

| Permiso | Ayudante | Oficial | Cajera | Gerente |
|---|:-:|:-:|:-:|:-:|
| Registrar venta | | | ✓ | ✓ |
| Registrar gasto | | | ✓ | ✓ |
| Pagar a proveedor o cancelar cuenta | | | | ✓ |
| Retirar efectivo | | | ✓ | ✓ |
| Cobrar deuda de cliente | | | ✓ | ✓ |
| Registrar adelanto de cliente | | | ✓ | ✓ |
| Registrar adelanto a proveedor | | | | ✓ |
| Crear o editar clientes | | | ✓ | ✓ |
| Crear o editar proveedores | | | | ✓ |
| Crear categorías de venta | | | | ✓ |
| Abrir o cerrar caja | | | ✓ | ✓ |
| Armar comandas | ✓ | ✓ | | ✓ |
| Anular comandas de otros | | ✓ | | ✓ |
| Recibir mercadería | ✓ | ✓ | | ✓ |
| Despostar | | ✓ | | ✓ |
| Ver stock | ✓ | ✓ | | ✓ |
| Contar stock | ✓ | ✓ | | ✓ |
| Cerrar conteos y liquidaciones | | ✓ | | ✓ |

Además: **Es staff** da entrada al admin y **Es superusuario** da acceso a todo (incluido el dashboard). El rol no los tilda solo.

Fuente: `core/roles.py`.

## Estados

| Qué | Estados | Cuándo cambia |
|---|---|---|
| **Comanda** | abierta → cobrada · abierta → anulada | Al cobrarla en caja · al anularla en el mostrador |
| **Turno de caja** | abierto → cerrado | Al confirmar el cierre. Cerrado no se modifica |
| **Despacho** | Enviado → Recibido | Cuando la sucursal confirma la recepción |
| **Media res** | En cámara → despostada | Al confirmar el desposte |
| **Conteo** | abierto → cerrado · abierto → anulado | Al cerrar (ajusta stock) · al anular (no toca el stock) |

## Reglas que conviene conocer

| Módulo | Regla |
|---|---|
| Comandas | Número diario por sucursal. Se cobra una sola vez. El stock baja al cobrar |
| Comandas | El ayudante anula solo las suyas; oficial y gerente, las de cualquiera |
| Caja | Sin turno abierto no se opera. Si quedó abierto un turno de otro día, hay que cerrarlo primero |
| Caja | La diferencia del cierre exige motivo y va a la cuenta *Diferencias de Caja* |
| Caja | Fiado solo aparece al elegir un cliente. No suma efectivo |
| Medios de pago | Sin asignaciones, la cajera ve todos los medios; con asignaciones, solo los activos |
| Recepción | La primera cámara activa de tipo cámara es la que se ofrece al recibir medias |
| Cámara | Con 4 días o más colgada, la media se marca en naranja |
| Conteo | Un solo conteo abierto por vez. Quien solo cuenta no ve lo esperado |
| Liquidación | Cerrar deja el stock igual a lo contado y guarda el balance. No se deshace |
| Catálogo | Productos, precios, plantillas y despachos se escriben en la central |
| Idioma | Tickets, PDF y Excel siempre en español |

## Pantallas y direcciones

| Pantalla | Dirección |
|---|---|
| Ingreso | `/accounts/login/` |
| Elegir puesto | `/pos/puesto/` |
| Caja | `/pos/` (con puesto de tipo Caja) |
| Mostrador | `/pos/mostrador/` |
| Recepción | `/pos/recepcion/` |
| Dashboard financiero | `/dash/` (superusuario) |
| Admin | `/admin/` |
| Panel central | `/central/` (en la central, staff) |
