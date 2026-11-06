# Prompt maestro para Codex local: Agente ADEMA

## Rol

Actua como un ingeniero senior de Django responsable de disenar, implementar, integrar y verificar un agente conversacional completo dentro de este proyecto real. Estas trabajando directamente sobre el repositorio del sistema, por lo que primero debes aprender su arquitectura, convenciones, modelos, servicios, permisos, transacciones, frontend, pruebas y proceso de empaquetado. No asumas nombres, rutas ni contratos que no hayas verificado en el codigo.

Tu trabajo no termina en una propuesta ni en un prototipo: debes entregar una implementacion funcional, integrada, probada y documentada, respetando el estilo existente y sin romper los circuitos contables actuales.

## Contexto del producto

Este proyecto es una aplicacion Django de escritorio para Windows orientada a POS, caja y gestion financiera. Incluye ventas, multipago, clientes y proveedores con cuenta corriente, compras, gastos, retiros, tesoreria, turnos, cierres, dashboard, reportes PDF/Excel, permisos, idempotencia e instalador. La base contable y financiera ya existe y debe seguir siendo la unica fuente de verdad.

Actualmente no hay un catalogo real de productos ni stock. El modulo llamado inventario clasifica ventas por categorias, pero no representa existencias. Por lo tanto, en esta entrega el agente debe registrar ventas por importe, categoria, cliente y medios de pago usando las capacidades reales del sistema. No inventes un inventario ni bloquees la arquitectura futura: deja puntos de extension limpios para incorporar catalogo, SEPA y stock mas adelante.

El producto deseado es un unico **Agente ADEMA multicanal** que pueda utilizarse desde:

- Un asistente pequeno integrado en la interfaz web/escritorio, similar conceptualmente a Clippy, pero visualmente coherente con el sistema.
- Un bot de Telegram opcional.
- Una API interna que permita sumar otros canales en el futuro.

Los canales no deben implementar logica de negocio ni tener agentes separados. Todos deben consumir el mismo orquestador, catalogo de herramientas, reglas, permisos, historial, confirmaciones y auditoria.

## Objetivo funcional

El agente debe comprender lenguaje natural en espanol, incluidas expresiones habituales y errores menores de escritura, para resolver de forma confiable un conjunto acotado de tareas:

1. Consultar ventas, cobros, saldos, caja y reportes por periodos naturales.
2. Resolver clientes y categorias existentes sin adivinar ante ambiguedades.
3. Preparar y confirmar ventas.
4. Preparar y confirmar cobros de clientes.
5. Preparar y confirmar gastos, solo si el circuito actual permite integrarlo con las mismas garantias.
6. Explicar claramente que entendio, que datos uso y que resultado obtuvo.
7. Recibir feedback positivo o negativo y comentarios correctivos con friccion minima.

Ejemplos que deben funcionar:

- "Cuanto vendimos hoy?"
- "Como venimos este mes comparado con el mismo periodo del mes pasado?"
- "Mostrame las ventas de la semana pasada por categoria."
- "Cuanto debe Juan Carlos?"
- "Registrame una venta de $100 de electricidad a Juan Carlos en efectivo."
- "Carga una venta de 150000 de electricidad a Juan Carlos; pago 100000 en efectivo y quedan 50000 en cuenta corriente."
- "Registra un cobro de 30000 de Marta por Mercado Pago."
- "Carga un gasto de luz de 45000 pagado en efectivo."

Si una orden es ambigua, incompleta o insegura, el agente debe hacer una pregunta concreta o presentar opciones. Nunca debe completar silenciosamente datos monetarios, clientes, cuentas, categorias, fechas o medios de pago inciertos.

## Principio de seguridad central

La IA interpreta; Django valida, calcula, autoriza y registra.

El modelo nunca puede:

- Ejecutar SQL libre.
- Escribir directamente en modelos contables.
- Decidir saldos, totales, asignaciones o cierres mediante texto generado.
- Saltarse permisos, turnos, transacciones, idempotencia o validaciones existentes.
- Confirmar por si mismo una operacion monetaria.
- Exponer secretos, prompts internos, trazas sensibles ni datos de otro negocio o usuario.

Las consultas de solo lectura pueden ejecutarse automaticamente si el usuario tiene permiso. Toda operacion que modifique dinero debe seguir el patron **preparar -> mostrar vista previa -> confirmar explicitamente -> ejecutar una sola vez**.

La confirmacion no debe ser otra decision del modelo. Debe ser una accion determinista de la interfaz o de Telegram sobre un borrador persistido, firmado o identificado por un token opaco, con vencimiento, propietario, permisos y proteccion contra doble ejecucion.

## Arquitectura requerida

Implementa una app Django autocontenida y reusable llamada `agente` salvo que el repositorio tenga una convencion de nombres que justifique otra denominacion. Debe poder trasladarse en el futuro a otro proyecto Django con cambios pequenos.

La division conceptual obligatoria es:

```text
Canales: panel integrado / Telegram / API
                    |
          Orquestador conversacional
                    |
     Politicas + contexto + catalogo de tools
                    |
       Adaptadores del proyecto actual
                    |
     Servicios reales de dominio Django
```

El nucleo reusable puede conocer conceptos genericos como conversacion, mensaje, proveedor, ejecucion, herramienta, permiso, riesgo, borrador, confirmacion, feedback y canal. No debe importar directamente modelos de ventas, caja, clientes, dashboard o tesoreria.

La integracion especifica con este sistema debe vivir en adaptadores o tools registrados por el proyecto. Esos adaptadores pueden importar y reutilizar los servicios reales de cada dominio. Si una regla de negocio vive hoy solamente en una view o formulario, extrae la porcion minima a un servicio reutilizable sin duplicar comportamiento y agrega pruebas de regresion.

Evita dos extremos:

- No acoples todo `agente` a este POS.
- No construyas un framework abstracto desproporcionado. La generalidad debe estar respaldada por las necesidades reales de panel, Telegram y futura reutilizacion.

## Catalogo de herramientas

Crea un registro declarativo de tools. Cada herramienta debe definir, como minimo:

- Nombre estable y versionable.
- Descripcion orientada al modelo.
- Esquema estructurado y validado de entrada.
- Esquema estructurado de salida.
- Tipo: consulta, preparacion o confirmacion.
- Nivel de riesgo.
- Permiso o politica requerida.
- Si requiere confirmacion.
- Funcion ejecutora.
- Serializador seguro para el resultado visible.
- Manejo de errores esperables y ambiguedades.

Usa esquemas JSON y validacion tipada con las dependencias ya presentes; si no existe una opcion local adecuada, elige una dependencia pequena y justificada. Los contratos deben ser compatibles conceptualmente con function calling y faciles de exponer por MCP en el futuro, pero **no implementes MCP como dependencia del funcionamiento interno** en esta entrega.

Una forma orientativa, que debes adaptar a las convenciones reales, seria:

```python
@agent_tool(
    name="ventas.preparar",
    description="Prepara una venta y devuelve una vista previa sin registrarla.",
    input_schema=PrepararVentaInput,
    risk="financial_write",
    permission="ventas.add_venta",
    confirmation_required=True,
)
def preparar_venta(context, payload):
    ...
```

No uses una tool generica como `ejecutar_sql`, `llamar_endpoint`, `editar_modelo` ni `registrar_movimiento`. Las herramientas deben representar intenciones de negocio limitadas y auditables.

El conjunto inicial debe cubrir, segun las capacidades verificadas del proyecto:

- `reportes.consultar`
- `clientes.buscar`
- `clientes.consultar_saldo`
- `ventas.preparar`
- `ventas.confirmar`
- `cobros.preparar`
- `cobros.confirmar`
- `gastos.preparar` y `gastos.confirmar`, solo si pueden quedar correctamente integradas

Las confirmaciones pueden ser endpoints internos deterministas en lugar de tools visibles para el modelo. Elige la opcion mas segura y simple, pero conserva la separacion preparar/confirmar.

## Orquestador y modelos de IA

Implementa un orquestador pequeno, legible y predecible. No incorpores LangChain o LangGraph salvo que, despues de inspeccionar el repositorio, exista una necesidad concreta que no pueda resolverse limpiamente con una capa pequena. Si agregas una de esas dependencias, documenta el motivo y mantenla fuera de los servicios de dominio.

El orquestador debe:

1. Recibir mensaje, usuario, negocio/sucursal si aplica, canal y contexto seguro.
2. Cargar solo el historial reciente necesario, con limites configurables.
3. Entregar al proveedor las tools permitidas para ese usuario y canal.
4. Exigir llamadas y argumentos estructurados, nunca parsear supuestos JSON con expresiones fragiles.
5. Validar todos los argumentos del modelo del lado del servidor.
6. Ejecutar consultas o crear borradores mediante el catalogo.
7. Resolver ciclos de tool calling con un limite estricto.
8. Producir una respuesta visible, breve y verificable.
9. Persistir la trazabilidad completa sin guardar secretos.
10. Fallar de manera util si el proveedor no responde, devuelve datos invalidos o excede limites.

Implementa una abstraccion de proveedores que permita cambiar modelo sin modificar el agente. Como minimo debe existir un proveedor OpenAI-compatible configurable por `base_url`, modelo y API key, de modo que pueda usarse una API comercial o un servidor local compatible. Si el proyecto ya tiene una abstraccion equivalente, reutilizala.

La configuracion debe permitir:

- Proveedor y modelo.
- URL base cuando corresponda.
- API key almacenada de forma segura y nunca enviada al navegador.
- Temperatura baja para interpretacion operativa.
- Timeout, reintentos acotados y limites de tokens/tool calls.
- Presupuesto o limite de uso, al menos como campos y metricas si el proveedor no permite aplicarlo directamente.
- Activar o desactivar el agente, panel y Telegram.
- Elegir acciones habilitadas por canal.

No guardes claves en texto plano si el proyecto dispone de un mecanismo de cifrado. Si no existe, implementa una solucion razonable basada en un secreto externo y documenta rotacion y recuperacion. Nunca escribas claves reales en migraciones, fixtures, logs o pruebas.

## Comprension de fechas y numeros

El agente debe comprender expresiones como `hoy`, `ayer`, `esta semana`, `semana pasada`, `este mes`, `mes pasado`, `ultimos 7 dias`, rangos explicitos y comparaciones con el periodo anterior.

No delegues la aritmetica temporal final al modelo. Normaliza las fechas en el backend usando la zona horaria configurada y devuelve rangos inclusivos/exclusivos bien definidos. Inyecta al modelo la fecha, hora y zona actuales para interpretar correctamente referencias relativas. Agrega pruebas en limites de dia, semana, mes y ano.

Los importes deben normalizar formatos argentinos habituales como `$150.000`, `150000`, `150 mil`, `100,50` cuando el dominio admita centavos. La validacion y las cuentas finales deben usar `Decimal`, nunca `float` ni calculos del modelo.

## Resolucion de entidades y dialogo

La busqueda de clientes, categorias, cuentas y medios de pago debe usar datos reales y respetar activos, permisos y alcance del usuario.

- Coincidencia unica y suficientemente fuerte: continuar.
- Varias coincidencias plausibles: presentar opciones claras.
- Ninguna coincidencia: informar y permitir reformular; no crear entidades automaticamente.
- Informacion obligatoria faltante: hacer una sola pregunta enfocada cuando sea posible.

Conserva el estado estructurado de la tarea pendiente para que una respuesta como `el segundo` o `en Mercado Pago` complete la operacion correcta sin depender solo del texto del historial.

## Borradores, confirmaciones e idempotencia

Una preparacion monetaria debe persistir un borrador inmutable o versionado con:

- Usuario y canal que lo solicito.
- Tool y version de contrato.
- Argumentos originales y datos ya resueltos.
- Resumen visible.
- Efectos previstos.
- Permisos comprobados.
- Fecha de creacion y vencimiento.
- Estado: pendiente, confirmado, cancelado, vencido o fallido.
- Identificador de idempotencia.
- Referencia al objeto creado al confirmar.

Al confirmar, vuelve a comprobar permisos y precondiciones que puedan haber cambiado: turno abierto, estado del cliente, cuentas, medios de pago, totales y cualquier regla propia del servicio. Ejecuta todo dentro de `transaction.atomic()` o de la transaccion de dominio ya existente. Una segunda confirmacion del mismo borrador debe devolver el resultado anterior, no duplicar la operacion.

La vista previa de una venta debe mostrar al menos cliente, categoria, total, pagos, saldo pendiente, turno/caja y advertencias. La de un cobro debe mostrar cliente, deudas o saldo afectado, importe, medio, cuenta destino y criterio de imputacion.

Existe un riesgo conocido en la validacion backend de multipago: verifica en el codigo real que la suma de los medios coincida exactamente con el total o con la combinacion valida de pago y cuenta corriente. Corrige esa validacion en la capa de dominio antes de permitir que el agente prepare o confirme ventas. Agrega pruebas tanto para la interfaz actual como para llamadas directas al servicio/API.

## Reportes y respuestas

Los numeros deben provenir de consultas y servicios del sistema, especialmente de los servicios del dashboard si representan la fuente de verdad. No permitas que el modelo calcule totales a partir de listados extensos.

Separa:

- Resultado estructurado: metricas, rangos, comparaciones, filas y metadatos.
- Presentacion: texto breve para chat, tarjetas o tablas para el panel y formato apropiado para Telegram.

La respuesta debe indicar el periodo consultado y evitar una precision falsa. Cuando compare periodos parciales, debe comparar periodos equivalentes. Si no hay datos, debe decirlo claramente.

## Panel integrado

Construye un asistente pequeno integrado al frontend actual, respetando su sistema visual y sus patrones. No lo conviertas en una landing ni en una aplicacion separada.

Debe incluir:

- Boton de apertura discreto y acceso por teclado si no colisiona con atajos existentes.
- Panel responsive que no tape controles esenciales ni se desborde en pantallas pequenas.
- Historial de conversacion.
- Campo de mensaje, envio, carga, error y reintento.
- Acciones rapidas: reporte, registrar venta, registrar cobro y consultar saldo; gasto solo si queda habilitado.
- Respuestas estructuradas con tablas o metricas cuando corresponda.
- Opciones para resolver ambiguedades.
- Tarjeta de vista previa con `Confirmar`, `Modificar` y `Cancelar`.
- Botones de feedback positivo y negativo en respuestas del agente.
- Al marcar negativo, comentario opcional de una linea o cuadro pequeno, sin modal obligatorio ni pasos innecesarios.

El frontend no debe contener la API key ni decidir permisos o confirmaciones. Protege endpoints con autenticacion, CSRF y las mismas reglas de sesion del sistema.

## Telegram

Implementa Telegram como adaptador opcional del mismo agente. Dado que el producto funciona como aplicacion de escritorio, inspecciona el ciclo de vida real antes de decidir entre long polling, webhook o proceso separado. Prioriza una solucion que funcione de manera confiable en Windows y que pueda apagarse sin corromper conversaciones.

Requisitos:

- Vinculacion explicita entre una cuenta de Telegram y un usuario autorizado del sistema mediante codigo temporal generado dentro de la aplicacion.
- El ID de Telegram no concede acceso por si solo.
- Permisos y tools por usuario y canal.
- Botones inline para opciones, confirmar, cancelar y feedback.
- PIN adicional configurable para acciones sensibles si existe un mecanismo seguro para validarlo.
- No mostrar informacion sensible en grupos; inicialmente limita operaciones a chats privados.
- Proteccion contra updates repetidos e idempotencia por `update_id`/callback.
- Token del bot almacenado de forma segura.
- Errores de red y reinicios recuperables.

No dupliques prompts, tool handling ni reglas entre Telegram y el panel.

## Feedback, aprendizaje y evaluacion

El feedback no debe modificar automaticamente el comportamiento financiero ni entrenar un modelo en produccion. Debe construir un corpus auditable para mejorar prompts, descripciones de tools, resolucion de entidades y casos de prueba.

Registra:

- Mensaje del usuario.
- Respuesta evaluada.
- Tool elegida y argumentos validados, si existieron.
- Resultado o borrador relacionado.
- Like o dislike.
- Comentario opcional.
- Usuario, canal y fecha.
- Version del prompt, proveedor y modelo.

Evita duplicados si el usuario cambia su voto. Permite filtrar feedback negativo desde Django admin o una vista interna sencilla, segun los patrones del proyecto. No almacenes cadenas de razonamiento privadas del proveedor; guarda solo entradas, salidas, decisiones estructuradas, errores y metadatos necesarios.

Crea un conjunto de evaluaciones reproducibles basado en frases reales y variantes con errores ortograficos. Debe poder ejecutarse sin consumir una API paga usando un proveedor falso o respuestas grabadas. Separa evaluacion de interpretacion, validacion de dominio y presentacion.

## Datos y modelos del modulo

Disena los modelos exactos despues de inspeccionar el proyecto, pero cubre conceptualmente:

- Configuracion del agente/proveedor.
- Conversacion y canal.
- Mensajes.
- Ejecuciones del orquestador.
- Invocaciones de tools.
- Borradores y confirmaciones.
- Feedback.
- Vinculaciones de Telegram.
- Metricas de uso, latencia, tokens/coste cuando esten disponibles.

Usa relaciones genericas o referencias serializadas solo cuando esten justificadas. Evita depender de `GenericForeignKey` para integridad critica si una referencia de dominio o tabla de enlace clara es mas segura. Define indices, restricciones unicas, politicas de retencion y borrado coherentes.

No guardes en logs ni en campos de error datos completos que contengan secretos. Revisa tambien el comportamiento con bases SQLite, que es el entorno real del producto.

## Permisos y politicas

Cada tool debe pasar por una capa de politica central. No basta con ocultar botones.

Como base:

- Consultas: automaticas con permiso de lectura.
- Crear clientes/categorias: fuera del alcance inicial o con confirmacion separada.
- Ventas, cobros y gastos: vista previa y confirmacion obligatoria.
- Transferencias, ajustes y operaciones de alto impacto: deshabilitadas inicialmente.
- Cerrar caja, anular movimientos, eliminar datos, resetear o modificar cierres: no exponer.

Respeta usuario, rol, sucursal, negocio y turno si esos conceptos existen. El agente nunca debe ampliar los permisos del usuario de sesion.

## Observabilidad y administracion

Integra el modulo con Django admin o con las herramientas administrativas existentes para permitir:

- Ver conversaciones y ejecuciones sin exponer secretos.
- Inspeccionar tool calls, duracion, estado y errores saneados.
- Revisar borradores y confirmaciones.
- Filtrar feedback negativo.
- Activar/desactivar proveedores, canales y tools.
- Consultar consumo aproximado.

Usa logging estructurado si el proyecto ya lo permite. Incluye correlation IDs entre mensaje, ejecucion, tool, borrador y operacion de dominio. Define timeouts y evita que una llamada lenta bloquee indefinidamente el servidor local.

## Seguridad adicional

Antes de finalizar:

- Verifica que `DEBUG`, binding de red, hosts permitidos y configuracion de escritorio no expongan el agente o sus secretos accidentalmente.
- No introduzcas endpoints sin autenticacion.
- Sanea Markdown/HTML generado antes de renderizarlo.
- Limita tamanos de mensaje, historial, archivos y resultados.
- Protege contra prompt injection: el contenido de clientes, categorias y reportes es dato, no instruccion.
- No permitas que el modelo seleccione tools no autorizadas aunque las mencione por nombre.
- Evita SSRF mediante `base_url`: restringe o valida su configuracion segun el modelo de despliegue.
- Agrega rate limits razonables por usuario/canal o un mecanismo equivalente compatible con el proyecto.
- Documenta claramente cualquier riesgo que no pueda cerrarse en esta entrega.

No mezcles en esta tarea cambios masivos ajenos al agente. Si encuentras credenciales predeterminadas, migraciones historicas fragiles u otros riesgos previos, no destruyas compatibilidad: corrige solo lo necesario para habilitar el agente con seguridad y deja documentados los demas hallazgos.

## Protocolo de trabajo obligatorio

1. Lee primero `AGENTS.md`, README, settings, URLs, modelos, servicios, forms, views, templates, tests, migraciones, empaquetado y dependencias relevantes.
2. Inspecciona el estado de Git. El arbol puede tener cambios del usuario: no reviertas ni sobrescribas trabajo ajeno.
3. Traza los flujos reales de venta, multipago, cobro, gasto, permisos, turno, idempotencia y dashboard antes de disenar adaptadores.
4. Ejecuta la suite base o el subconjunto mas amplio viable y registra el estado previo.
5. Redacta un plan de implementacion breve y concreto dentro de tu sesion, y luego implementalo sin detenerte a pedir aprobacion salvo que exista una decision de producto realmente bloqueante o una accion destructiva.
6. Trabaja en incrementos verificables: nucleo, tools, seguridad, panel, Telegram y pruebas.
7. Usa migraciones Django normales y comprueba instalaciones nuevas y actualizaciones sobre una copia de la base, nunca sobre datos operativos unicos.
8. Ejecuta formatters, linters, checks, tests y pruebas manuales de los flujos afectados.
9. No des por finalizada la tarea con stubs, TODOs esenciales, botones decorativos o herramientas que simulan exito.
10. Al terminar, entrega un resumen de arquitectura, archivos cambiados, migraciones, configuracion necesaria, pruebas ejecutadas, riesgos residuales y pasos exactos para probar panel y Telegram.

## Estrategia de pruebas minima

Agrega pruebas unitarias, de integracion y las pruebas de interfaz que soporte el proyecto. Como minimo cubre:

- Registro, descubrimiento y filtrado de tools por permiso.
- Validacion de argumentos y rechazo de campos inesperados.
- Interpretacion determinista de fechas y periodos.
- Normalizacion de importes argentinos con `Decimal`.
- Cliente unico, cliente ambiguo y cliente inexistente.
- Preparacion de venta sin efectos contables.
- Confirmacion atomica e idempotente.
- Reconfirmacion sin duplicados.
- Borrador vencido, cancelado o perteneciente a otro usuario.
- Cambio de permisos o cierre de turno entre preparar y confirmar.
- Rechazo de multipago inconsistente desde backend.
- Preparacion y confirmacion de cobro usando el servicio real.
- Consultas de dashboard con periodos equivalentes.
- Feedback positivo, negativo, comentario opcional y cambio de voto.
- Proveedor IA simulado: tool call valida, argumentos invalidos, timeout, error y limite de iteraciones.
- Panel: autenticacion, CSRF, estados de carga/error y confirmacion.
- Telegram: vinculacion, chat no autorizado, update repetido, callback repetido y permisos.
- Aislamiento entre usuarios/negocios/sucursales si aplica.

No hagas que la suite dependa de internet ni de una API key real.

## Criterios de aceptacion

La entrega se considera completa solo si:

1. Un usuario autenticado puede abrir el asistente integrado y preguntar por ventas de un periodo; la respuesta usa datos reales y muestra el rango consultado.
2. Puede consultar el saldo de un cliente y resolver coincidencias ambiguas mediante opciones.
3. Puede escribir una venta en lenguaje natural, recibir una vista previa exacta y confirmarla explicitamente.
4. Antes de confirmar no existe ningun efecto contable; despues de confirmar existe exactamente una operacion valida y auditada.
5. Un doble clic, reintento HTTP, callback repetido o mensaje duplicado no crea ventas ni cobros duplicados.
6. Una suma de pagos invalida es rechazada por el backend aunque se evite el navegador.
7. El mismo orquestador funciona desde el panel y Telegram sin duplicar logica.
8. Un modelo pequeno/OpenAI-compatible puede seleccionar tools mediante salidas estructuradas; cambiar a un modelo mas potente solo requiere configuracion.
9. El usuario puede dar like/dislike y dejar una correccion opcional en pocos pasos.
10. Las claves permanecen fuera del frontend, los logs y el repositorio.
11. La app `agente` no importa directamente dominios concretos del POS; la integracion vive en adaptadores registrados.
12. Las pruebas existentes siguen pasando, salvo fallos previos documentados y no relacionados.
13. La aplicacion y el instalador de Windows siguen arrancando, o queda documentado y probado el ajuste necesario para iniciar el componente de Telegram.

## Decisiones de alcance

Incluido ahora:

- App reusable `agente`.
- Catalogo de tools.
- Orquestador y proveedor configurable.
- Panel integrado.
- Telegram opcional.
- Reportes, saldos, ventas y cobros.
- Gastos si el dominio permite una integracion segura dentro del mismo ciclo.
- Confirmaciones, auditoria, feedback, permisos, metricas y pruebas.

No incluido ahora:

- Inventario real, stock o movimientos de mercaderia.
- Catalogo SEPA, salvo interfaces vacias o puntos de extension sin comportamiento ficticio.
- Facturacion fiscal.
- Ejecucion de SQL libre.
- Cierres, anulaciones, transferencias o ajustes autonomos.
- Entrenamiento o fine-tuning automatico con feedback.
- MCP como requisito interno. Los contratos deben quedar preparados para exponer un adaptador MCP mas adelante.

## Criterio de calidad

Prefiere codigo explicito, pequeno y probado. Reutiliza los servicios de dominio existentes. No dupliques reglas contables en prompts, views, serializers, Telegram ni JavaScript. Toda afirmacion monetaria debe ser trazable a una consulta o resultado estructurado. Toda escritura debe ser autorizada, validada, transaccional, confirmada e idempotente.

Empieza inspeccionando el repositorio real. Luego implementa la solucion completa de extremo a extremo y verificala. No te detengas despues del analisis ni entregues solo un plan.
