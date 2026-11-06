# Manual de Medios de Pago y Cuentas — Gestion de Carnicerias

> **Para quién es este manual:** para el dueño o administrador general del
> negocio, incluso si nunca manejó uno. Explica a bajo nivel cómo funcionan
> las cuentas del sistema, qué significa cada saldo, y qué hacer en cada
> situación (falta plata, sobra plata, corregir cuentas, controlar cajeros).
>
> Es **complementario** al [Manual de Turno de Caja](CAJA_MANUAL.md), que
> explica el día a día del cajero (abrir, vender, cerrar). Este manual explica
> el "detrás de escena": dónde vive la plata y cómo controlarla.

## Índice
1. [La idea central: cajones y un cuaderno](#1-la-idea-central-cajones-y-un-cuaderno)
2. [Los tres pilares del sistema](#2-los-tres-pilares-del-sistema)
3. [Tipos de medios de pago, uno por uno](#3-tipos-de-medios-de-pago-uno-por-uno)
4. [Las cuentas que crea el sistema y su rol](#4-las-cuentas-que-crea-el-sistema-y-su-rol)
5. [Cómo VER las cuentas](#5-cómo-ver-las-cuentas)
6. [Cómo MODIFICAR las cuentas](#6-cómo-modificar-las-cuentas)
7. [Recetario: qué hacer en cada situación](#7-recetario-qué-hacer-en-cada-situación)
8. [Control de cajeros: asignaciones de medios de pago](#8-control-de-cajeros-asignaciones-de-medios-de-pago)
9. [Rutina de control del administrador](#9-rutina-de-control-del-administrador)
10. [Preguntas frecuentes](#10-preguntas-frecuentes)

---

## 1. La idea central: cajones y un cuaderno

Imaginá tu negocio así:

- Cada **medio de pago** es un **cajón donde hay plata** (o donde se anota
  plata que te deben): el cajón del mostrador, la caja fuerte, la cuenta de
  Mercado Pago, la libreta del fiado.
- Cada vez que la plata se mueve, el sistema lo anota en un **cuaderno**
  (los *Movimientos de cuenta*): cuánto, cuándo, quién, de qué cajón salió y
  a qué cajón entró.
- El **saldo** de cada cajón no es un número que alguien escribe: es el
  resultado de sumar todas las anotaciones del cuaderno. Si el cuaderno dice
  que entraron $10.000 y salieron $4.000, el cajón tiene $6.000. Punto.

**La regla más importante de todo el sistema:** el cuaderno **nunca se
escribe a mano**. Cada anotación nace de una operación real (una venta, un
gasto, una apertura de caja, un ajuste). Por eso todo saldo se puede explicar:
tocás cualquier número y el sistema te muestra de dónde salió.

---

## 2. Los tres pilares del sistema

| Pilar | En el sistema | Qué es |
|---|---|---|
| **Cuenta** | Admin → Tesorería → **Medios de pago** | El "cajón". Tiene nombre (ej: "Efectivo"), tipo (categoría) y saldo actual. |
| **Movimiento** | Admin → Tesorería → **Movimientos de cuenta** | Una línea del cuaderno: fecha, cuenta, ingreso o egreso, monto, usuario, turno y descripción. **Solo lectura**: no se puede crear ni editar a mano. |
| **Documento de origen** | Ventas, Gastos, Ajustes, Transferencias, Turnos… | La operación real que generó el movimiento. Si se corrige el documento (cuando está permitido), el movimiento se regenera solo. |

### La regla de la contrapartida (doble asiento)

Desde la versión 0.9.0, **ningún peso aparece ni desaparece sin explicación**:

- Si la plata *se mueve de lugar* (apertura de caja, cierre, retiro,
  transferencia), siempre hay **dos** anotaciones: sale de un cajón y entra a
  otro. La suma total del sistema no cambia.
- Si la plata *entra o sale del negocio de verdad* (una venta, un gasto, un
  ajuste), hay **una** anotación, pero siempre atada a un documento con
  usuario, fecha y motivo.

Si alguna vez ves un saldo que no entendés, la respuesta **siempre** está en
los movimientos de esa cuenta.

---

## 3. Tipos de medios de pago, uno por uno

Cuando creás un medio de pago (Admin → Tesorería → Medios de pago → Añadir),
elegís una **categoría**. La categoría le dice al sistema cómo comportarse.

### 🟢 Efectivo

**Qué representa:** plata física, billetes que se pueden tocar.

**Por qué importa la categoría:** el sistema tiene reglas especiales que solo
aplican a cuentas Efectivo:

- La **caja POS (drawer)** y la **Caja Central** *deben* ser de tipo Efectivo
  (el sistema lo valida y no te deja configurar otra cosa). ¿Por qué? Porque
  el flujo de apertura/cierre de caja mueve billetes reales de un lado a otro,
  y solo tiene sentido entre cuentas de plata física.
- Al abrir caja, el selector **"¿De qué cuenta sale el efectivo?"** solo
  muestra cuentas de tipo Efectivo (excluyendo el propio drawer). Si creás una
  cuenta "RESERVA" de tipo Efectivo, aparecerá como origen posible.

**Qué significa su saldo:** cuántos billetes debería haber físicamente en ese
lugar. Si el sistema dice que Caja Central tiene $50.000, en la caja fuerte
tiene que haber $50.000. Si no coinciden, algo pasó — y se corrige con un
Ajuste (nunca "dibujando" el número).

**Ejemplos:** `Efectivo` (el cajón del mostrador), `Caja Central` (la caja
fuerte), `RESERVA` (una segunda caja fuerte o la bolsita de emergencia).

### 🔵 Transferencia Bancaria

**Qué representa:** plata digital que entra a una cuenta virtual o bancaria.

**Qué significa su saldo:** cuánto se cobró por ese canal (menos lo que salió).
Sirve para conciliar contra la app: si el sistema dice que Mercado Pago
acumuló $30.000 esta semana, en la app de MP deberían figurar esos cobros.

**Ejemplos:** `Mercado Pago`, `Banco Galicia`, `Cuenta DNI`.

> El saldo inicial/final de Mercado Pago que declara el cajero al abrir y
> cerrar caja es **solo informativo** (para el control del reporte de cierre).
> No genera movimientos. Los cobros reales sí: cada venta cobrada por MP es un
> INGRESO en esta cuenta.

### 🟣 Tarjeta de Crédito / Tarjeta de Débito

**Qué representa:** cobros con posnet. Igual que Transferencia Bancaria, pero
separado para que puedas ver cuánto facturás por tarjeta.

**Detalle del mundo real:** la tarjeta te deposita días después y con
comisión. El saldo de la cuenta "Tarjeta" refleja lo *cobrado*, no lo
*depositado*. En la sección de recetas está cómo registrar la comisión.

### 🟠 Cuenta Corriente (el "fiado")

**Esta es la categoría más distinta de todas.** No representa plata: representa
**promesas de plata**.

- Cuando vendés fiado, la plata no entró — pero el sistema anota un INGRESO en
  la cuenta CC: "me deben $500 más".
- Cuando el cliente paga su deuda, el sistema anota dos cosas: INGRESO en la
  cuenta real donde entró la plata (Efectivo, MP…) y EGRESO en la cuenta CC:
  "me deben $500 menos".

**Qué significa su saldo:** con la cuenta `Fiado` de clientes, un saldo
positivo = **cuánta plata te deben los clientes en total**. Es tu "libreta de
fiados" consolidada. El detalle por cliente está en Admin → Ventas → Clientes
(columna Saldo CC y el PDF de estado de cuenta).

**Ojo con los proveedores:** si comprás fiado a proveedores usando una cuenta
CC, esas deudas se anotan como EGRESOS en la cuenta CC (plata que *debés*).
Si usás **la misma** cuenta CC para clientes y proveedores, el saldo se vuelve
una "posición neta" (lo que te deben menos lo que debés) y es más difícil de
leer. **Recomendación:** creá dos cuentas CC — `Fiado` (clientes, creala
primero) y `Fiado Proveedores`. *Nota técnica:* las deudas cargadas como
"saldo inicial" de cliente o proveedor siempre se asientan en la primera
cuenta CC creada.

**Nunca uses una cuenta CC para movimientos de plata real** (no es un cajón,
es una libreta).

### ⚪ Otro

**Qué representa:** cuentas "virtuales" que no son ni plata física, ni un canal
de cobro, ni crédito. Se usan para registro y control.

**El ejemplo clave: `Diferencias de Caja`.** Es de tipo "Otro" a propósito:
no es plata que exista en ningún cajón — es el registro de la plata que
**faltó o sobró** en los arqueos de cierre. Al ser "Otro", queda claro que no
es un canal de cobro y no debe asignarse a ningún cajero.

---

## 4. Las cuentas que crea el sistema y su rol

`python manage.py init_system` crea estas cuentas y las vincula en
Admin → Core → Configuración → **"Tesorería — Cuentas del sistema"**:

| Cuenta | Categoría | Rol | Su saldo significa |
|---|---|---|---|
| **Efectivo** | Efectivo | Caja POS (drawer): la plata en manos del cajero durante el turno | Billetes en el cajón del mostrador. **Debe ser $0 cuando no hay turnos abiertos.** |
| **Caja Central** | Efectivo | La tesorería: donde vive el efectivo fuera de los turnos. Origen del fondo de apertura y destino del cierre | Billetes en la caja fuerte |
| **Diferencias de Caja** | Otro | Acumula faltantes (+) y sobrantes (−) de cada arqueo, con turno, cajero y motivo | Plata pendiente de explicar. **Debería tender a $0** (ver recetas) |
| **Mercado Pago** | Transferencia Bancaria | Cobros por MP + control informativo en el cierre | Lo cobrado por MP |
| **Fiado** | Cuenta Corriente | La libreta de fiados de clientes | Lo que te deben los clientes |

**Reglas de la configuración** (el sistema las valida solo):
- Caja POS y Caja Central deben ser de tipo Efectivo.
- Caja POS ≠ Caja Central ≠ Diferencias (no pueden ser la misma cuenta).
- Podés crear todas las cuentas extra que quieras (RESERVA, Banco, etc.);
  las cinco de arriba son el esqueleto mínimo.

---

## 5. Cómo VER las cuentas

### 5.1 El vistazo rápido: saldos de todas las cuentas

**Admin → Tesorería → Medios de pago.** La columna **"Saldo actual"** muestra
el saldo vivo de cada cuenta: verde si es positivo, rojo si es negativo.

Lectura sana de esa pantalla (sin turnos abiertos):
- `Efectivo` (drawer) → **$0.00** ✅
- `Caja Central` → el efectivo real de tu caja fuerte
- `Diferencias de Caja` → idealmente $0; si crece, hay faltantes sin explicar
- `Fiado` → cuánto te deben los clientes
- `Mercado Pago` / `Tarjeta` → lo cobrado por esos canales

### 5.2 El detalle de una cuenta

Hacé clic en cualquier cuenta: además de sus datos, vas a ver el bloque
**"últimos 30 movimientos"** (solo lectura) — la punta del cuaderno para esa
cuenta.

### 5.3 El cuaderno completo, con filtros

**Admin → Tesorería → Movimientos de cuenta.** Todos los movimientos de todas
las cuentas. Filtros útiles (columna derecha):

- **por medio de pago** → el historial de un cajón
- **por tipo** → ej: `Diferencia de arqueo de cierre` te lista todos los
  faltantes/sobrantes históricos; `Ajuste` te lista todas las correcciones manuales
- **por turno** → todo lo que pasó en un turno puntual
- **por usuario** → todo lo que operó un cajero

Esta pantalla es **solo lectura**: nadie (ni vos) puede escribir el cuaderno a mano.

### 5.4 Reporte imprimible por período

**Admin → Tesorería → Movimientos de cuenta → botón "Reporte"** (también desde
el Panel de control → 📊 Reporte de cuentas): elegís cuenta y rango de fechas
y exportás **PDF o Excel** con saldo inicial del período, ingresos, egresos,
saldo final y el detalle línea por línea con saldo acumulado. Es el documento
para revisar con tu contador.

### 5.5 El cierre de cada turno

Cada turno cerrado tiene su **PDF de cierre** (Admin → Ventas → Turnos de
caja → botón Download): resumen del turno, arqueo de efectivo (esperado,
declarado, diferencia y motivo), sección informativa de Mercado Pago y
conciliación por medios de pago.

> **Importante:** los "saldos por medio" que ve el cajero en el POS son una
> vista operativa de *su* día (para que se controle a sí mismo). El saldo
> contable real de cada cuenta es el del Admin.

---

## 6. Cómo MODIFICAR las cuentas

Solo existen **dos herramientas** para tocar saldos a mano, y ambas dejan
rastro completo (usuario, fecha, motivo). Todo lo demás está bloqueado.

### 6.1 Ajuste de cuenta — cuando la plata entra o sale "de verdad"

**Admin → Tesorería → Ajustes de cuenta → Añadir.**

- **Cuenta:** a cuál aplicar.
- **Monto:** positivo = suma saldo (entró plata al sistema), negativo = resta
  (salió plata del sistema).
- **Descripción:** el motivo. **Obligatorio moralmente** — un ajuste sin motivo
  claro es un agujero en tu auditoría. Escribí como si se lo explicaras a tu
  contador: *"Carga inicial caja fuerte"*, *"Retiro del dueño para gastos
  personales"*, *"Se asume pérdida faltante turno #12"*.

Usalo cuando el dinero **aparece o desaparece del negocio**: carga inicial,
retiro del dueño, pérdida asumida, comisión bancaria, plata encontrada.

### 6.2 Transferencia entre cuentas — cuando la plata cambia de lugar

**Admin → Tesorería → Transferencias entre cuentas → Añadir.**

Elegís cuenta origen, cuenta destino y monto → el sistema genera los dos
movimientos (egreso + ingreso). La suma total del sistema no cambia.

Usalo cuando el dinero **se mueve pero sigue siendo tuyo**: llevás efectivo
de la Caja Central al banco, pasás plata de una caja fuerte a otra.

### 6.3 Lo que NO se puede hacer (y por qué)

| Acción | Qué pasa | Por qué |
|---|---|---|
| Crear/editar un Movimiento de cuenta a mano | El admin no lo permite | El cuaderno solo lo escribe el sistema |
| Editar o borrar una venta/gasto/cobro de un **turno cerrado** | El sistema lo rechaza (queda solo-lectura) | Un turno cerrado es historia congelada; se corrige con Ajustes |
| Editar o borrar un turno cerrado | Rechazado | Ídem |
| Abrir caja con plata "de la nada" | Rechazado: exige cuenta de origen con saldo suficiente | Evita saldos ficticios |
| Borrar un medio de pago con movimientos | Rechazado (protegido) | Perderías historia contable. Renombralo si querés |

---

## 7. Recetario: qué hacer en cada situación

### 📕 Falta dinero al cierre de caja (faltante)

**Qué hizo el sistema solo:** al cerrar, entró a Caja Central *lo declarado*
(lo contado real) y el faltante quedó asentado en **Diferencias de Caja** con
turno, cajero y el motivo que escribió el cajero. No tenés que tocar nada para
que las cuentas cierren.

**Qué hacés vos como administrador:**
1. Mirá el asiento: Admin → Tesorería → Movimientos de cuenta, filtro
   tipo = "Diferencia de arqueo de cierre". Ahí ves monto, turno, cajero y motivo.
2. Investigá con el PDF del cierre y hablá con el cajero.
3. Cerrá el caso según lo que encuentres:
   - **La plata no aparece (pérdida real):** Ajuste de cuenta sobre
     `Diferencias de Caja`, monto **negativo** (ej: −300), descripción
     *"Se asume pérdida faltante turno #12 — error de vuelto"*. Diferencias
     vuelve a $0 y la pérdida queda documentada.
   - **La plata aparece después** (estaba caída atrás del cajón): Transferencia
     `Diferencias de Caja` → `Caja Central` por el monto, descripción
     *"Faltante turno #12 recuperado"*. Diferencias vuelve a $0 y la plata
     entra a la caja fuerte.
   - **Era un gasto que el cajero no registró:** mismo Ajuste negativo en
     Diferencias, con descripción que explique el gasto (*"Faltante turno #12:
     compra de lamparita no registrada"*). El turno cerrado no se puede editar
     — el rastro queda en el ajuste.

### 📗 Sobra dinero al cierre de caja (sobrante)

**Qué hizo el sistema solo:** lo declarado (incluido el sobrante) entró a Caja
Central, y `Diferencias de Caja` quedó en **negativo** por el sobrante.

**Qué hacés vos:**
- **No se explica y te lo quedás:** Ajuste **positivo** en `Diferencias de
  Caja` (ej: +200), descripción *"Sobrante turno #15 reconocido como ingreso"*.
- **Era de un cliente (le cobraron de más) y se lo devolvés:** Transferencia
  `Caja Central` → `Diferencias de Caja` por el monto, descripción
  *"Devolución sobrante turno #15 a cliente"* (la plata sale de la caja fuerte
  y salda la diferencia).

> **Meta:** `Diferencias de Caja` en $0. Su saldo es tu lista de "casos
> abiertos". Si crece mes a mes, tenés un problema operativo (o algo peor) —
> y ahora tenés el registro por turno y cajero para encontrarlo.

### 💰 Poner la plata inicial del negocio en el sistema (primera vez)

Ajuste de cuenta sobre `Caja Central`, monto positivo = el efectivo real que
tenés, descripción *"Carga inicial de tesorería"*. **Es el único momento en
que la plata "aparece"**, y queda documentado. A partir de ahí, todo se mueve
por operaciones.

### 🏦 Depositar efectivo en el banco

1. Creá la cuenta si no existe: Medios de pago → Añadir → `Banco XXX`,
   categoría Transferencia Bancaria.
2. Transferencia `Caja Central` → `Banco XXX` por lo depositado.

### 👤 El dueño retira plata para uso personal

Ajuste **negativo** sobre `Caja Central`, descripción *"Retiro del dueño"*.
(Salió del negocio de verdad → es Ajuste, no Transferencia.)

> Si el cajero te da plata del cajón durante el turno, eso es un **Retiro**
> desde el POS: va solo del drawer a la Caja Central. Después hacés el ajuste
> desde Caja Central. Así el arqueo del cajero no se ve afectado.

### 💳 La tarjeta/MP depositó menos por comisiones

Cuando el banco te deposita, ej: cobraste $10.000 con tarjeta y entran $9.600:
1. Transferencia `Tarjeta` → `Banco XXX` por $9.600.
2. Ajuste **negativo** de $400 sobre `Tarjeta`, descripción *"Comisión posnet
   liquidación 07/07"*.

### 🧾 Descubro un error en una operación de un turno ya cerrado

No se puede editar (y está bien que así sea). Corregí el **efecto** según el
tipo de error, siempre citando la operación y el turno en la descripción:

- **Medio de pago equivocado** (ej: la venta #45 del turno #12 se cargó como
  Efectivo pero fue por Mercado Pago): una **Transferencia**
  `Efectivo/Caja Central` → `Mercado Pago` por el monto, descripción
  *"Corrección venta #45 turno #12: era MP, no efectivo"*.
- **Monto equivocado** (se cobró/registró de más o de menos): un **Ajuste**
  en la cuenta afectada por la diferencia, con la misma lógica de descripción.

Queda registrado el error Y su corrección — exactamente lo que un auditor
quiere ver.

### 📒 Un cliente quiere pagar su fiado

Eso NO se hace tocando cuentas: se hace desde el **POS → Cobrar deuda** (el
cajero necesita turno abierto). El sistema asienta solo: entra plata al medio
real y baja la libreta `Fiado`. Las cuentas CC no se ajustan a mano salvo
casos extremos — el detalle por cliente vive en Ventas → Clientes.

### 🕵️ "Este saldo no me cierra"

1. Medios de pago → clic en la cuenta → mirá los últimos 30 movimientos.
2. ¿Necesitás más? Movimientos de cuenta → filtrá por esa cuenta y por fechas.
3. ¿Querés papel? Reporte PDF/Excel del período.
4. Cada movimiento dice tipo, turno, usuario y descripción: siempre vas a
   llegar al documento que lo originó.

---

## 8. Control de cajeros: asignaciones de medios de pago

**Admin → Tesorería → Asignaciones de medios de pago a cajeros.**

Acá definís **qué medios puede operar cada cajero** en el POS (con qué medios
puede cobrar ventas, registrar gastos, etc.).

⚠️ **Regla clave que tenés que conocer:** un cajero **sin ninguna asignación
ve TODOS los medios de pago** — incluidas `Caja Central` y `Diferencias de
Caja`. Para un control serio:

1. Asignale a cada cajero **solo** los medios de cobro reales:
   `Efectivo`, `Mercado Pago`, `Tarjeta`, `Fiado`.
2. **Nunca** asignes `Caja Central` ni `Diferencias de Caja` a un cajero
   (no son canales de cobro; nadie paga "con la caja fuerte").
3. Para sacarle un medio a un cajero sin borrar el historial, destildá
   **Activo** en la asignación.

(`init_system` ya deja a los cajeros de fábrica con los 3 medios correctos.)

Los superusuarios ven todos los medios siempre — si el dueño usa el POS,
cuidado con no elegir `Caja Central` como medio de cobro por error.

---

## 9. Rutina de control del administrador

### Todos los días (2 minutos, después del último cierre)

- [ ] **Medios de pago:** `Efectivo` (drawer) en **$0** ✅
- [ ] `Diferencias de Caja` en $0 — si no, leé el motivo del asiento y resolvé con el recetario
- [ ] El PDF de cierre de cada turno: diferencia y motivo razonables
- [ ] `Caja Central` del sistema = billetes reales de la caja fuerte (contalos cada tanto)

### Todas las semanas

- [ ] Movimientos tipo **Ajuste**: cada uno con motivo claro. Un ajuste que no entendés = pregunta pendiente.
- [ ] `Mercado Pago` / `Tarjeta` contra las apps/liquidaciones reales
- [ ] `Fiado`: ¿crece sin parar? Revisá clientes deudores (Ventas → Clientes)

### Todos los meses

- [ ] Reporte PDF/Excel de `Caja Central` y de `Diferencias de Caja` del mes (archivalos)
- [ ] Diferencias por cajero: filtrá Movimientos por tipo "Diferencia de arqueo" y mirá patrones

### Señales de alerta

| Señal | Qué puede significar |
|---|---|
| `Efectivo` (drawer) ≠ $0 sin turnos abiertos | Turno legacy viejo, o alguien operando fuera del flujo |
| `Diferencias de Caja` crece todos los días | Faltantes recurrentes: error operativo o robo hormiga |
| Ajustes frecuentes sin descripción útil | Están "dibujando" saldos — exigí motivos |
| `Fiado` enorme y creciendo | Estás financiando a tus clientes sin control |
| Saldo negativo en una cuenta Efectivo | Imposible físicamente → buscá el movimiento que lo causó |

---

## 10. Preguntas frecuentes

**¿Puedo cambiar el saldo de una cuenta directamente?**
No, y es la mejor protección que tenés. El saldo es la suma de los
movimientos. Para modificarlo: Ajuste de cuenta (con motivo) o Transferencia.

**¿Puedo borrar o renombrar un medio de pago?**
Renombrar sí, es seguro (las cuentas del sistema están vinculadas por
configuración, no por nombre). Borrar solo si nunca tuvo movimientos; si los
tiene, el sistema lo protege. Si ya no usás un medio, quitáselo a los cajeros
en Asignaciones.

**¿Por qué la Caja Central tiene que ser de tipo Efectivo?**
Porque participa del circuito de billetes físicos (entrega el fondo de
apertura y recibe el cierre) y el sistema solo permite cuentas Efectivo en ese
circuito. Lo valida automáticamente.

**¿Por qué "Diferencias de Caja" es de tipo Otro y no Efectivo?**
Porque no es plata que exista en un cajón: es un registro de plata
faltante/sobrante pendiente de explicación. Si fuera Efectivo, aparecería como
origen posible al abrir caja — y no tiene sentido "abrir caja con el faltante".

**¿Qué diferencia hay entre un Ajuste y una Transferencia?**
Transferencia = la plata cambió de cajón pero sigue en el negocio (total del
sistema igual). Ajuste = la plata entró o salió del negocio de verdad (total
del sistema cambia). Si dudás: ¿después de esto tengo la misma plata total?
Sí → Transferencia. No → Ajuste.

**¿El saldo de `Fiado` es plata que tengo?**
No: es plata que te **deben**. No la podés gastar ni transferir. Se convierte
en plata real cuando el cliente paga (POS → Cobrar deuda).

**¿Por qué no puedo editar una venta de ayer?**
Porque su turno está cerrado y el cierre ya movió la plata según lo declarado.
Si se pudiera editar, el arqueo de ayer dejaría de cuadrar hoy y nadie podría
auditar nada. La corrección se documenta con un Ajuste (queda el error Y la
corrección, como en cualquier contabilidad seria).

**¿Quién puede ver/hacer todo esto?**
Todo lo de este manual vive en el Admin (staff/superusuario). Los cajeros solo
operan el POS; ni ven el ledger ni pueden ajustar cuentas.

**¿Y si tengo dos cajas registradoras?**
Cada cajero abre su propio turno, pero hoy todos comparten el mismo drawer
(`cuenta_caja_pos`). Los saldos del header del POS se calculan por cajero, y
el arqueo de cierre es por turno, así que el control individual se mantiene.
