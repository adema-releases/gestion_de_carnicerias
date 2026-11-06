# Hallazgos del código al documentar

Cosas raras o mejorables que aparecieron al leer el sistema y recorrer cada pantalla para escribir los tutoriales. **Ninguna se corrigió**: los tutoriales describen el comportamiento actual. Si se corrige alguna, hay que actualizar el tutorial indicado (en `es/` y en `zh/`).

Verificado el 2026-11-03.

| # | Dónde | Qué pasa | Por qué importa | Tutorial |
|---|---|---|---|---|
| 1 | `core/admin.py` (`ConfiguracionAdmin.fieldsets`) | El **día de liquidación** (`dia_liquidacion`), la **sucursal** de la instalación y el **estado de la sincronización** (`sync_ultima`, `sync_ultimo_error`) no están en ninguna pestaña de *Configuración* | `docs/MANUAL_GERENTE.md` dice que se cambian y se consultan ahí. Hoy el gerente no puede cambiar el día ni ver si la PC sincroniza | 19 |
| 2 | `pos/templates/pos/terminal.html` (`modal-cierre`) | El cierre de caja solo pide el **efectivo**. No hay casilla para **declarar Mercado Pago**, aunque el modelo tiene `saldo_final_mercado_pago` | `docs/MANUAL_CAJA_CARNICERIA.md` dice «Declará el saldo de Mercado Pago» | 10 |
| 3 | `pos/templates/pos/terminal.html` | En el flujo de venta **clásico** no hay botón para abrir *Cobro de deuda* (`modal-cobro`): solo se llega desde el flujo guiado (`abrirCobroDesdeVenta`). En la práctica se cobra con **Adelanto cliente** + cobro automático o **Conciliar** | El manual de caja nombra «Cobro de deuda» como acción del día | 08 |
| 4 | `core/roles.py` / `core/management/commands/seed_carniceria.py` | El rol **Gerente** carga todos los permisos del POS pero **no** tilda `is_staff` ni `is_superuser`: el gerente no entra al admin ni al dashboard hasta que alguien lo tilda a mano | El manual del gerente asume que entra al admin. En la demo se tildó a mano | 18 |
| 5 | `core/admin.py` (`SucursalAdmin`) | El **token de sincronización** se ve como texto de solo lectura; no hay botón para copiarlo ni para regenerarlo si se filtra | Al abrir una sucursal hay que copiarlo a mano; si se compromete, no hay forma de rotarlo desde el admin | 27 |
| 6 | `pos/views.py` (`_seleccionar_deudas_cubiertas_por_adelanto`) | El cobro automático cancela solo **ventas fiadas enteras**; el resto que no alcanza para la siguiente venta queda como adelanto disponible aunque el cliente siga debiendo | Comportamiento razonable, pero sorprende al ver «disponible» con deuda pendiente | 08 |
| 7 | `pos/comandas.py` (`api_comanda_anular`) | El **motivo** de anulación es opcional en el servidor (se acepta vacío) | El control semanal de comandas anuladas pierde valor si no hay motivo | 04, 22 |
| 8 | Traducciones (`ventas` · `CobroDeuda`) | El nombre plural del modelo sale en inglés en el admin: **«Debt collections»**; y el selector de puestos (*filter_horizontal*) muestra textos de ayuda en inglés («Choose … by selecting them…») | Se ve en el menú del gerente y en la ficha del usuario | 18, 22 |
| 9 | `central/templates/central/panel.html` | El panel central es más ancho que una pantalla de 1760 px: la última columna queda cortada y hay que desplazar la tabla | En una notebook no se ve **Saldo cuenta** sin desplazar | 23 |
| 10 | `manage.py` (`normalize_runserver_argv`) | `runserver` **ignora** el puerto que se le pasa y usa `RUNSERVER_PORT` (por defecto 8250) | Al levantar una segunda instancia (demo, central de prueba) se monta sobre el puerto de la app real si no se exporta `RUNSERVER_PORT` | — (herramientas) |
| 11 | Tema del admin (Jazzmin oscuro) · selector `filter_horizontal` de *Puestos habilitados* | Las opciones de las dos listas se ven **blanco sobre blanco**; las flechas para pasar de una lista a otra salen como imagen rota. Solo funciona el doble clic | El gerente cree que no hay puestos para elegir | 18 |
| 12 | Traducciones en chino del admin | En *Turnos de caja* la columna de diferencia sigue diciendo «(faltante)» / «(exacto)» en español | Detalle visible en la pantalla de control semanal en chino | 22 |
