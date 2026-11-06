# Auditoría: Medios de pago, apertura y cierre de caja

**Fecha:** 2026-07-07 · **Estado:** ✅ IMPLEMENTADO (2026-07-07). La Parte 1 describe el comportamiento ANTERIOR (histórico); la Parte 2 es el diseño implementado. Manual operativo: `CAJA_MANUAL.md`. Decisiones del dueño: (a) apertura BLOQUEA si la cuenta de origen no tiene saldo suficiente; (b) turno cerrado 100% inmutable — correcciones solo vía Ajustes de cuenta con motivo.

**Notas de implementación:** el candado vive en `tesoreria/locks.py` (backstop de modelo + mixin de admin); el flujo de cierre en `_regenerate_turno_movimientos` (`tesoreria/signals.py`); las cuentas del sistema se configuran en Admin → Configuración → "Tesorería — Cuentas del sistema". Los turnos históricos sin cuenta de origen conservan sus asientos legacy (rama legacy del signal). Suite de invariantes: `tesoreria.tests.TurnoCierreCarrefourTests`.

---

## Parte 1 — Cómo funciona HOY

### 1.1 El libro mayor: `MovimientoCuenta`

Todo el dinero del sistema vive en `tesoreria.MovimientoCuenta` (el ledger). El
"Saldo actual" que se ve en el admin de Medios de pago es simplemente
`Σ ingresos − Σ egresos` de esa tabla (`tesoreria/admin.py:83`).

Los movimientos **nunca se crean a mano**: los generan signals
(`tesoreria/signals.py`) con un patrón *wipe & regenerate* — al guardar o
borrar una Venta/Gasto/Turno/etc., se borran sus movimientos y se recrean
desde cero.

### 1.2 Apertura y cierre de turno: DOS modos (`_regenerate_turno_movimientos`, `tesoreria/signals.py:509`)

#### Modo A — CON `cuenta_origen` (doble partida)

| Momento | Asiento |
|---|---|
| Apertura | EGRESO `cuenta_origen` por `saldo_inicial` + INGRESO `Efectivo` por `saldo_inicial` |
| Cierre | EGRESO `Efectivo` por el **balance real** (inicial + operaciones netas) + INGRESO `cuenta_origen` por el **saldo declarado** |

- La diferencia de arqueo **no genera ningún asiento propio**: queda implícita
  como distorsión del saldo de `cuenta_origen` (si declarás de menos, a la
  cuenta origen "le falta" plata y nadie lo registra).
- `diferencia_cierre` se fuerza a `0` en el API (`pos/views.py:2512`), aunque
  el PDF sí calcula y muestra la diferencia real al vuelo (`pos/views.py:1640`).

#### Modo B — SIN `cuenta_origen` (partida simple → dinero ficticio)

| Momento | Asiento |
|---|---|
| Apertura | INGRESO `Efectivo` por `saldo_inicial` **sin contrapartida** (dinero creado de la nada) |
| Cierre | Asiento `cierre_diferencia` en `Efectivo` por `declarado − esperado` |

- El float inicial nunca "sale" de Efectivo. El dinero declarado al cierre no
  va a ningún lado.

#### Caso borde — `cuenta_origen` == la propia cuenta Efectivo

Si la cuenta de origen elegida ES la cuenta Efectivo por defecto (hoy es la
única de categoría Efectivo, así que es fácil que pase), el signal omite la
pata de INGRESO para evitar una auto-transferencia circular
(`tesoreria/signals.py:534`), **pero el EGRESO de apertura sí se crea**. Al
cerrar declarando 0, tampoco hay devolución. Resultado: agujero de
`−saldo_inicial` en Efectivo.

### 1.3 Explicación de los tres casos que probaste

1. **Apertura 5000 + 1200 MP, sin cuenta de origen, cierre en 0** (Turno #1):
   Modo B. El ledger recibió +5000 ficticios en Efectivo (apertura) y al
   cerrar el asiento "Faltante de arqueo" de −5000 lo compensó → Efectivo
   quedó en 0. Los $1.200 de Mercado Pago **nunca tocaron el ledger**: solo se
   suman visualmente en el header del POS mientras el turno está abierto
   (`_saldos_medios_dia`, `pos/views.py:1154-1166`). Al cerrar, ese display
   desaparece. Por eso "sumó y descontó".

2. **Apertura 5000 sin indicar origen, cierre en 0**: idéntico al caso 1 —
   Modo B, ciclo +5000/−5000, neto 0.

3. **Apertura 1000 eligiendo la cuenta "Efectivo" como origen, cierre en 0**
   (Turno #2, saldo −1000 en el admin): caso borde de Modo A. EGRESO −1000 sin
   pata de ingreso, cierre sin devolución (declaraste 0) → Efectivo quedó en
   **−1000**.

### 1.4 Mercado Pago hoy

`saldo_inicial_mercado_pago` / `saldo_final_mercado_pago` ya son **puramente
informativos**: jamás generan `MovimientoCuenta`. Solo alimentan el header del
POS y la sección "Mercado Pago" del PDF de cierre (esperado vs declarado).
⚠️ La cuenta MP se detecta por nombre exacto `"mercado pago"`
(`pos/views.py:74`) — renombrarla rompe silenciosamente el informe.

### 1.5 Hallazgos de auditoría (resumen)

| # | Hallazgo | Riesgo |
|---|---|---|
| H1 | Modo B crea dinero ficticio (apertura sin contrapartida) | Saldos falsos, imposible conciliar |
| H2 | `cuenta_origen` es opcional (flag `apertura_requiere_cuenta_origen` default `False`, y solo aplica si el cajero puede ver el selector) | Cualquier cajero elige Modo B |
| H3 | En Modo A la diferencia de arqueo no genera asiento ni registro propio | Faltantes invisibles, escondidos en la cuenta origen |
| H4 | Caso borde `cuenta_origen == Efectivo` produce EGRESO sin contrapartida | Agujeros tipo el −1000 |
| H5 | Los asientos de apertura usan `timezone.now()` en cada regeneración — cada re-save del turno les cambia la fecha | Trazabilidad temporal débil |
| H6 | Un turno cerrado no está bloqueado: editar/borrar ventas, gastos o el propio turno regenera el ledger sin dejar rastro | Ledger mutable a posteriori |
| H7 | Mercado Pago identificado por nombre mágico | Frágil |
| H8 | `diferencia_cierre` (campo del modelo) se fuerza a 0 en Modo A pero el PDF muestra otra cosa | Datos inconsistentes |
| H9 | La "caja del POS" es implícitamente "la primera cuenta de categoría Efectivo por id" (`get_efectivo_default`) — retiros y aperturas dependen de eso | Agregar otra cuenta Efectivo (ej. Caja Central) puede desviar asientos |
| H10 | El cierre acepta declarar $0 por defecto sin confirmación | Cierres accidentales sin arqueo real |

---

## Parte 2 — Propuesta: modelo "terminal de supermercado" (Carrefour)

### 2.1 Principios

1. **Doble partida siempre.** Ningún peso entra o sale del sistema sin
   contrapartida. Las únicas excepciones documentadas: `AjusteCuenta` (es el
   documento explícito de ajuste, con usuario, fecha y motivo) y los asientos
   de Cuenta Corriente (son cuentas de crédito, no dinero físico).
2. **El drawer (caja física del POS) empieza y termina cada turno en $0** en
   el ledger. Todo lo que tiene durante el turno vino de algún lado y se va a
   algún lado.
3. **Al cierre entra a Caja Central exactamente lo declarado** (lo contado).
   La diferencia contra lo esperado genera su propio asiento — el "ticket de
   diferencia" — nunca desaparece ni se esconde.
4. **Mercado Pago sigue siendo informativo** (saldo inicial → movimientos →
   declarado → diferencia en el reporte), sin tocar el ledger desde el turno.

### 2.2 Cuentas explícitas (nuevo en `core.Configuracion`)

| Campo | Rol |
|---|---|
| `cuenta_caja_pos` | El drawer de la terminal (reemplaza al implícito `get_efectivo_default`) |
| `cuenta_caja_central` | Donde vive el efectivo fuera de los turnos; origen por defecto de la apertura y destino del cierre |
| `cuenta_diferencias_caja` | Cuenta virtual (categoría "Otro") que acumula faltantes/sobrantes de arqueo |
| `cuenta_mercado_pago` | FK explícita, elimina el match por nombre (H7) |

`init_system` crea "Caja Central" y "Diferencias de caja" si no existen.

### 2.3 Flujo propuesto

**Apertura** (declaro fondo `F`, origen obligatorio, default Caja Central):

```
EGRESO  Caja Central  F   (apertura_caja)
INGRESO Caja POS      F   (apertura_caja)
```

**Durante el turno:** igual que hoy (ventas/cobros/adelantos → INGRESO drawer
o cuenta del medio; gastos/pagos → EGRESO). Retiros: EGRESO drawer + INGRESO
Caja Central (hoy el retiro es plata que "desaparece").

**Cierre** (esperado `E = F + neto efectivo del turno`, declarado `D`):

```
EGRESO  Caja POS      D          (cierre_devolucion → "efectivo enviado a Caja Central")
INGRESO Caja Central  D
-- si D < E (faltante):
EGRESO  Caja POS          (E−D)  (cierre_diferencia → "Faltante de arqueo turno #N")
INGRESO Diferencias caja  (E−D)
-- si D > E (sobrante):
INGRESO Caja POS          (D−E)  (cierre_diferencia → "Sobrante de arqueo turno #N")
EGRESO  Diferencias caja  (D−E)
```

Resultado garantizado: **drawer en $0 tras cada cierre**, Caja Central recibe
lo contado, y la cuenta "Diferencias de caja" acumula el historial de
faltantes/sobrantes por turno y cajero (el equivalente al ticket de
diferencia de Carrefour). El gerente la revisa y la regulariza con
`AjusteCuenta` cuando corresponde.

### 2.4 Reglas duras (validaciones)

1. **Apertura sin cuenta de origen: prohibida.** Se elimina el Modo B. El API
   rechaza; la UI preselecciona Caja Central y no permite vacío.
2. **`cuenta_origen ≠ cuenta_caja_pos`** — validado en API y modelo (mata H4).
3. **Saldo insuficiente en origen:** si `saldo(origen) < F`, bloquear (o
   advertir, según config) — no se puede retirar de Caja Central plata que no
   existe.
4. **Cierre exige declaración explícita:** confirmación si se declara $0.
   Si hay diferencia ≠ 0, pedir motivo (texto libre) que queda en la
   descripción del asiento de diferencia.
5. **`diferencia_cierre` siempre se calcula y persiste** (mata H8).

### 2.5 Trazabilidad e inmutabilidad

- **Fechas estables:** apertura usa la fecha de creación del turno; cierre usa
  `cerrado_en`. Nunca `now()` en la regeneración (mata H5).
- **Candado de turno cerrado:** no se pueden crear/editar/borrar operaciones
  de un turno cerrado (validación en modelos + admin); para corregir hay que
  reabrir el turno (acción de admin registrada) o usar `AjusteCuenta`.
- (Fase posterior, opcional) historial inmutable con `django-simple-history`
  sobre `MovimientoCuenta` / `AjusteCuenta` / `TurnoCaja`.

### 2.6 Fases de implementación

| Fase | Contenido |
|---|---|
| 1 | Config de cuentas explícitas + migración + `init_system` (Caja Central, Diferencias de caja) |
| 2 | Endurecer apertura: API + UI (origen obligatorio, validaciones) |
| 3 | Refactor del signal de cierre (flujo 2.3), persistir diferencia + motivo |
| 4 | Candado de turno cerrado + fechas estables |
| 5 | Retiros con destino + MP por FK + PDF con sección de arqueo |
| 6 | Tests: drawer=0 tras cierre, conservación de saldo global, diferencia registrada, aperturas inválidas rechazadas |
