# Auditoría de saldos de cuentas (medios de pago)

**Fecha:** 07/07/2026
**Test:** `tesoreria/test_auditoria_cuentas.py`
**Ejecución:** `python manage.py test tesoreria.test_auditoria_cuentas -v 2`
**Resultado:** ✅ 9/9 tests OK — auditoría sin errores de saldos. Suite completa del proyecto: 144/144 OK.

---

## 1. Qué se probó

Simulación de **7 días de trabajo reales contra la API del POS** (los mismos
endpoints que usa la terminal), partiendo con **todas las cuentas en $0**:

| Cuenta | Rol |
|---|---|
| CAJA POS | Drawer físico de la terminal (Efectivo) |
| CAJA CENTRAL | Tesorería / caja fuerte (Efectivo) — origen del fondo de apertura |
| MERCADO PAGO | Billetera virtual |
| TARJETA DEBITO / TARJETA CREDITO | Cuentas de tarjetas |
| CUENTA CORRIENTE | Cuenta contable de fiados (clientes) y deudas (proveedores) |
| DIFERENCIAS DE CAJA | Cuenta virtual de faltantes/sobrantes de arqueo |

Cada día simulado incluyó:

- **Apertura de caja** con $10.000 de fondo saliendo de CAJA CENTRAL (doble asiento).
- **12 a 14 ventas** con todos los medios: efectivo solo, MP solo, débito, crédito,
  mixtas (efectivo+MP, efectivo+débito, MP+crédito, efectivo+CC) y **fiados totales** (CC).
- **Gastos** en efectivo, MP, débito y crédito (rotando por día).
- **Compras / pagos a proveedores**: al contado (efectivo, MP, débito) y **fiadas (CC)**.
- **Cancelaciones de deuda a proveedor** (efectivo y MP), **cobros de deuda de clientes**
  (efectivo y MP, con aplicación automática de adelantos), **adelantos** de cliente y de
  proveedor, y **retiros de efectivo** (sangrías a caja central).
- **Cierre de caja** declarando: arqueo exacto (días 1 y 4), **faltantes**
  ($500 día 2, $1.000 día 5, $50 día 7) y **sobrantes** ($250 día 3, $100 día 6).

El test lleva en paralelo un **ledger espejo** (la trazabilidad manual de lo que
DEBERÍA valer cada cuenta) y al final lo compara contra `MovimientoCuenta`.

## 2. Validaciones de negocio verificadas (casos negativos)

Todas estas operaciones inválidas fueron **correctamente rechazadas** por la API:

| # | Caso | Resultado |
|---|---|---|
| 1 | Apertura con efectivo **sin cuenta de origen** configurada | ✅ Rechazada — exige elegir cuenta ("Debés indicar de qué cuenta sale el efectivo inicial") |
| 2 | Apertura con efectivo y cuenta de origen **sin fondos** ($0) | ✅ Rechazada — "Saldo insuficiente" (no se crea dinero de la nada) |
| 3 | Apertura con cuenta de origen = **la propia caja POS** | ✅ Rechazada |
| 4 | Apertura con cuenta de origen **no Efectivo** (Mercado Pago) | ✅ Rechazada |
| 5 | Cierre con **diferencia de arqueo sin motivo** | ✅ Rechazado — exige el motivo del faltante/sobrante |
| 6 | **Gasto pagado con Cuenta Corriente** | ✅ Rechazado |
| 7 | **Venta fiada (CC) sin cliente** | ✅ Rechazada |
| 8 | Apertura **sin efectivo** (solo saldo MP declarado) sin cuenta origen | ✅ Permitida (correcto: no se mueve plata, MP es informativo) |

## 3. Resultado de la trazabilidad (7 días)

### Cierres por día

| Día | Esperado POS | Esperado auditoría | Declarado | Diferencia |
|---|---|---|---|---|
| 1 | 15.150,00 | 15.150,00 | 15.150,00 | 0,00 |
| 2 | 14.150,00 | 14.150,00 | 13.650,00 | −500,00 (faltante) |
| 3 | 33.150,00 | 33.150,00 | 33.400,00 | +250,00 (sobrante) |
| 4 | 4.150,00 | 4.150,00 | 4.150,00 | 0,00 |
| 5 | 14.150,00 | 14.150,00 | 13.150,00 | −1.000,00 (faltante) |
| 6 | 12.150,00 | 12.150,00 | 12.250,00 | +100,00 (sobrante) |
| 7 | 27.650,00 | 27.650,00 | 27.600,00 | −50,00 (faltante) |

El "saldo esperado" que muestra el POS al cierre coincidió **los 7 días** con la
trazabilidad manual independiente, y con el ledger (`MovimientoCuenta`).

### Saldos finales por cuenta

| Cuenta | Ledger real | Esperado | Dif. | Estado |
|---|---|---|---|---|
| CAJA POS | 0,00 | 0,00 | 0,00 | ✅ OK (queda en $0 tras cada cierre) |
| CAJA CENTRAL | 558.350,00 | 558.350,00 | 0,00 | ✅ OK |
| MERCADO PAGO | 66.200,00 | 66.200,00 | 0,00 | ✅ OK |
| TARJETA DEBITO | 33.100,00 | 33.100,00 | 0,00 | ✅ OK |
| TARJETA CREDITO | 54.500,00 | 54.500,00 | 0,00 | ✅ OK |
| CUENTA CORRIENTE | 4.400,00 | 4.400,00 | 0,00 | ✅ OK |
| DIFERENCIAS DE CAJA | 1.200,00 | 1.200,00 | 0,00 | ✅ OK |

Chequeos estructurales adicionales, todos OK:

- **CAJA POS = $0** después de cada uno de los 7 cierres (el drawer nunca retiene plata).
- **CUENTA CORRIENTE** = por cobrar a clientes ($8.400) − por pagar a proveedores
  ($4.000) = $4.400. El saldo contable de CC coincide exactamente con las deudas
  reales pendientes calculadas desde las ventas fiadas y compras fiadas.
- **DIFERENCIAS DE CAJA** = Σ faltantes − Σ sobrantes = 500 + 1.000 + 50 − 250 − 100
  = **$1.200** (saldo positivo = plata que faltó y hay que regularizar).
- **Conservación global**: ningún movimiento interno (aperturas, cierres, retiros,
  diferencias) crea ni destruye dinero; el total del sistema se explica por el
  capital inicial + resultado operativo.

## 4. Errores encontrados

**Ninguno.** La trazabilidad cerró exacta en las 7 cuentas tras ~250 movimientos
generados por 96 ventas, 19 gastos, 12 compras (4 fiadas), 3 cancelaciones de deuda,
4 cobros de deuda, 3 adelantos, 3 retiros y 7 ciclos de apertura/cierre.

El motor de movimientos (`tesoreria/signals.py`) regenera correctamente el ledger
para cada operación, incluyendo los casos finos:

- Ventas multi-medio generan un movimiento por línea de pago (incluida la línea CC).
- El cobro de deuda genera ingreso real + egreso CC por el total cancelado,
  descontando adelantos aplicados (partida doble consistente).
- La cancelación a proveedor genera egreso real + ingreso CC.
- Retiros y cierres mueven la plata entre drawer y caja central sin pérdidas.

## 5. Observaciones (no son errores, pero conviene saberlas)

1. **Saldos iniciales de cliente/proveedor no pasan por el ledger.**
   `SaldoInicialCliente` / `SaldoInicialProveedor` no generan movimiento de alta en
   la cuenta CC (son deuda "histórica" previa al sistema), pero **cobrarlos sí**
   genera el egreso/ingreso en CC. Si se usan saldos iniciales, el saldo de la
   cuenta CC dejará de coincidir con "por cobrar − por pagar" en el monto de esos
   saldos históricos ya cobrados. *Solución si se quiere CC 100 % auditable:*
   registrar un `AjusteCuenta` sobre la cuenta CC por el total de saldos iniciales
   cargados, o generar el movimiento de alta por señal (como ya se hace con las
   ventas fiadas). Quedó fuera del alcance de esta simulación.

2. **Los adelantos vigentes no viven en la cuenta CC.** Un adelanto de cliente sin
   aplicar ($1.500 de Cliente B en la simulación) entra por su medio real (MP) y no
   toca CC hasta que se aplica a una deuda. Es consistente en partida doble, pero al
   leer el saldo CC hay que recordar que los adelantos pendientes son un pasivo
   aparte (visible en la ficha del cliente).

3. **Mercado Pago en apertura/cierre es informativo.** Los saldos MP declarados al
   abrir/cerrar no generan movimientos (correcto por diseño); el saldo real de la
   cuenta MP se construye solo con las operaciones.

4. El test deja fijado el comportamiento: si mañana un cambio en señales o en
   `_totales_turno` rompe la partida doble, este test falla mostrando cuenta por
   cuenta la diferencia y el detalle de movimientos por tipo.
