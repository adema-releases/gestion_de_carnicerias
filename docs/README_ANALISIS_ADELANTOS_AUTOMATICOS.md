# Analisis de adelantos automaticos y estado de cuenta

## Objetivo

Documentar que hace hoy la app cuando estan activadas estas opciones:

- `Cobro automatico de deudas`
- `Pago automatico de deudas a proveedores`

Y contrastarlo contra la regla de negocio que se necesita:

> Un adelanto solo debe cancelar automaticamente una deuda cuando alcanza para cubrirla completa. Si no alcanza para cubrir el ticket o la deuda completa, no debe aplicarse parcialmente y la deuda debe seguir mostrandose completa.

## Resumen ejecutivo

El problema reportado es real y hoy esta implementado en backend.

Lo que encontre es esto:

1. El sistema hoy SI aplica adelantos parciales en automatico.
2. Ese comportamiento existe tanto para clientes como para proveedores.
3. La conciliacion manual del POS repite exactamente la misma logica parcial.
4. El ticket de estado de cuenta imprime el `saldo` actual, no la deuda original.
5. Por eso, cuando hubo una aplicacion parcial automatica, el ticket muestra la deuda ya neteada.
6. Los tests actuales validan ese comportamiento, asi que no parece un error accidental sino una regla de negocio implementada de otra manera.

## Ejemplo del problema

Caso esperado segun la regla pedida:

- Ticket 82 debe `$20.650`
- cliente deja un adelanto de `$100`

Resultado que se necesita:

- Ticket 82 debe seguir mostrando `$20.650`
- el adelanto de `$100` debe quedar disponible
- no debe generarse una cancelacion parcial automatica

Resultado que hace hoy el sistema:

- aplica los `$100` sobre esa deuda
- reduce el saldo pendiente del ticket
- el estado de cuenta muestra el ticket con la deuda ya reducida

## Hallazgos tecnicos

### 1. Configuracion involucrada

En `core/models.py` existen estos flags:

- `cobro_automatico_deudas`
- `pago_automatico_deudas_proveedores`

Los textos de ayuda dicen que el sistema aplica adelantos automaticamente a las deudas mas antiguas, pero no imponen ninguna condicion de cobertura total por deuda.

### 2. Donde se habilita la aplicacion parcial automatica

#### Clientes

En `pos/views.py`, la funcion `_intentar_cobro_automatico_por_adelanto(...)`:

- construye las deudas pendientes del cliente
- las ordena por fecha e id
- toma `remanente_adelanto = adelanto.saldo_disponible`
- recorre las deudas aplicando:

```python
monto_a_aplicar = min(d['saldo'], remanente_adelanto)
```

Ese `min(...)` confirma que el algoritmo acepta aplicaciones parciales.

Si la deuda es `20650` y el adelanto es `100`, hoy aplica `100`.

Luego crea un `CobroDeuda` automatico con:

- `monto_recibido = 0`
- `monto_adelanto_aplicado = total_a_cobrar`

Y registra detalles sobre las ventas o saldos iniciales afectados.

#### Proveedores

En `pos/views.py`, la funcion `_intentar_pago_automatico_por_adelanto_proveedor(...)` repite la misma logica:

```python
monto_a_aplicar = min(d['saldo'], remanente_adelanto)
```

O sea, el mismo problema existe del lado proveedor.

### 3. La conciliacion manual del POS repite el mismo criterio

Tambien en `pos/views.py`, los endpoints de conciliacion manual usan la misma mecanica:

- `api_cliente_cc_conciliar_manual(...)`
- `api_proveedor_cc_conciliar_manual(...)`

Ambos vuelven a usar:

```python
monto_a_aplicar = min(d['saldo'], remanente_adelanto)
```

Entonces el desvio no esta solo al registrar adelantos. Tambien esta en la conciliacion manual.

### 4. El estado de cuenta imprime saldo neto, no deuda original

En `pos/views.py`, la funcion `_cliente_cc_data(...)` arma cada deuda con estos campos:

- `importe`: monto original
- `pagado`: monto ya cobrado
- `saldo`: saldo pendiente actual

Para ventas a cuenta corriente, el campo mostrado como pendiente se construye con:

- `saldo = venta.saldo_pendiente`

Luego, al imprimir el estado de cuenta del cliente, `api_cliente_estado_cuenta_print(...)`:

- filtra deudas con `saldo > 0`
- calcula el total pendiente con la suma de `saldo`
- manda esos datos a `build_estado_cuenta_ticket(...)`

Finalmente, en `pos/printing.py`, `build_estado_cuenta_ticket(...)` imprime cada deuda usando:

```python
monto_str = _fmt_two_places(d.get('saldo', 0))
```

O sea, el ticket muestra el saldo neto despues de cobros o adelantos aplicados.

### 5. La semantica del modelo confirma esa lectura

En `ventas/models.py`:

- `SaldoInicialCliente.saldo_pendiente = monto - monto_cobrado`
- `Venta.saldo_pendiente = monto_fiado - monto_cobrado`

En `compras/models.py`:

- `SaldoInicialProveedor.saldo_pendiente = monto - monto_cancelado`
- `PagoProveedor.saldo_pendiente = importe - monto_cancelado`

Es decir, `saldo_pendiente` siempre es deuda neta actual, no deuda original.

Eso por si mismo no esta mal. El problema aparece porque el backend esta generando cancelaciones parciales automaticas que el negocio no quiere.

### 6. Los tests actuales validan el comportamiento parcial

En `pos/tests.py` hay pruebas que hoy esperan el comportamiento parcial.

Las principales son:

- `test_cobro_automatico_deudas_por_adelanto`
- `test_pago_automatico_deudas_proveedor_por_adelanto`

Esos tests verifican que:

- se cancela completa la deuda mas vieja
- el remanente se aplica parcialmente sobre la siguiente deuda

Ejemplo actual en tests:

- deuda vieja: `1000`
- venta posterior: `1500`
- adelanto: `2000`
- resultado esperado hoy: cancela `1000` de la primera y `1000` de la segunda, dejando `500` pendientes

Eso confirma que el comportamiento actual fue implementado a proposito, aunque hoy no coincida con la regla deseada.

## Causa raiz

La causa raiz principal esta en la logica de negocio del backend.

Secuencia real actual:

1. El algoritmo toma el adelanto disponible.
2. Lo distribuye en cascada con aplicaciones parciales.
3. Eso reduce `saldo_pendiente` de la deuda afectada.
4. El estado de cuenta imprime ese `saldo_pendiente` ya reducido.

En resumen: el ticket no inventa el problema. El ticket solo refleja una aplicacion parcial que ya ocurrio antes en backend.

## Impacto funcional

### Clientes

Con `cobro_automatico_deudas` activo:

- un adelanto chico puede reducir parcialmente una venta fiada
- el estado de cuenta deja de mostrar la deuda completa del ticket
- el usuario ve una deuda neteada aunque no hubo cobertura total de ese ticket

### Proveedores

Con `pago_automatico_deudas_proveedores` activo:

- un adelanto puede cancelar parcialmente compras a credito o saldos iniciales
- la deuda visible del proveedor queda reducida automaticamente
- aparece la misma inconsistencia de criterio que del lado cliente

## Desvio exacto contra la regla pedida

### Lo que hace hoy

Si una deuda es de `$20.650` y el adelanto es de `$100`:

- crea un cobro o cancelacion automatica parcial
- reduce el saldo pendiente de esa deuda
- el ticket muestra la deuda reducida

### Lo que deberia hacer

Si una deuda es de `$20.650` y el adelanto es de `$100`:

- no debe generar cobro automatico
- no debe crear detalle de aplicacion sobre esa deuda
- la deuda debe seguir en `$20.650`
- el adelanto de `$100` debe quedar como saldo a favor disponible
- el ticket debe mostrar la deuda completa

## Propuesta tecnica de correccion

### Regla sugerida

Recorrer las deudas en orden cronologico estricto y aplicar esta condicion:

1. Si `remanente_adelanto >= saldo_deuda`, cancelar la deuda completa.
2. Si `remanente_adelanto < saldo_deuda`, detener el proceso.
3. No hacer aplicaciones parciales.
4. No saltar a deudas mas nuevas para usar el remanente en otra mas chica.

### Cambio de algoritmo esperado

Reemplazar el criterio actual:

```python
monto_a_aplicar = min(d['saldo'], remanente_adelanto)
```

Por una logica de este tipo:

```python
if remanente_adelanto < d['saldo']:
    break

monto_a_aplicar = d['saldo']
```

### Funciones que habria que tocar

En `pos/views.py`:

- `_intentar_cobro_automatico_por_adelanto(...)`
- `_intentar_pago_automatico_por_adelanto_proveedor(...)`
- `api_cliente_cc_conciliar_manual(...)`
- `api_proveedor_cc_conciliar_manual(...)`

## Recomendacion de refactor

Conviene extraer un helper comun para evitar que cliente y proveedor vuelvan a divergir.

Por ejemplo, una funcion que:

- reciba deudas ordenadas
- reciba remanente de adelanto
- devuelva solo deudas completamente cubribles

Eso permitiria reutilizar exactamente la misma regla en:

- autoaplicado de clientes
- autoaplicado de proveedores
- conciliacion manual de clientes
- conciliacion manual de proveedores

## Sobre el ticket de estado de cuenta

Hay dos niveles posibles de mejora.

### Ajuste minimo

Si se corrige la logica del backend para impedir aplicaciones parciales automaticas, el problema reportado baja de inmediato porque las deudas ya no van a quedar reducidas por adelantos insuficientes.

### Ajuste recomendable

Ademas, el ticket podria mostrar por cada deuda:

- deuda original
- total aplicado
- saldo pendiente

Eso da mucha mas trazabilidad y evita confusion incluso cuando si existan pagos parciales manuales legitimos.

## Tests que deberian cambiar o agregarse

### Clientes

1. Adelanto menor que la deuda mas antigua.
   - deuda: `20650`
   - adelanto: `100`
   - esperado: no se crea `CobroDeuda`, la deuda sigue igual, el adelanto queda disponible.

2. Adelanto igual a la deuda mas antigua.
   - deuda: `20650`
   - adelanto: `20650`
   - esperado: se cancela completa esa deuda.

3. Adelanto que cubre la primera deuda pero no la segunda.
   - deuda 1: `1000`
   - deuda 2: `1500`
   - adelanto: `2000`
   - esperado: se cancela solo deuda 1, quedan `1000` como adelanto disponible, deuda 2 no se toca.

4. Conciliacion manual con el mismo criterio estricto.

### Proveedores

Repetir exactamente los mismos escenarios para:

- `SaldoInicialProveedor`
- `PagoProveedor` en cuenta corriente
- conciliacion manual de proveedor

## Riesgos del cambio

1. Los tests actuales van a fallar porque hoy validan la aplicacion parcial.
2. Puede cambiar el comportamiento operativo que algunos usuarios ya daban por hecho.
3. Si se corrige una sola ruta y no las cuatro, el sistema quedara inconsistente.
4. Si se corrige solo el ticket y no el backend, el problema real seguira existiendo.

## Conclusion

Tu observacion coincide exactamente con la implementacion actual.

Hoy la app:

- si aplica adelantos parciales automaticamente
- lo hace tanto para clientes como para proveedores
- repite la misma regla en conciliacion manual
- y despues imprime el saldo neto resultante en el estado de cuenta

En resumen, el desvio principal esta en la logica de autoaplicacion y conciliacion, no solo en la impresion del ticket.

## Archivos clave revisados

- `core/models.py`
- `pos/views.py`
- `pos/printing.py`
- `ventas/models.py`
- `compras/models.py`
- `pos/tests.py`