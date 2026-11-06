# Método: documentación con tutoriales y capturas automáticas

Receta para replicar en cualquier proyecto web (Django u otro) una biblioteca de tutoriales **con capturas anotadas generadas por script**, sobre una **base de demo anonimizada**. Salió de ADEstock, se adaptó a Gestión de Créditos y después a Gestión de Carnicerías (esta, **bilingüe español/chino** y con base de demo generada desde cero en vez de anonimizada); los tres proyectos son la referencia viva (`documentacion/` en cada uno).

> **Idea central:** las capturas no se sacan a mano. Un script por tutorial maneja el sistema real (Playwright), dibuja flechas y números, y guarda las imágenes con nombres fijos. Si la pantalla cambia, se vuelve a correr el script y todo el tutorial se actualiza. El texto cita las mismas marcas numeradas.

---

## 1. Las cuatro piezas

| Pieza | Qué es | Dónde queda |
|---|---|---|
| **Biblioteca de textos** | Tutoriales `.md` con plantilla fija + conceptos, referencia, operación y FAQ | `documentacion/00-inicio … 05-faq` |
| **Base de demo anonimizada** | Copia de datos reales con todo lo personal reemplazado, para que los gráficos y listados tengan volumen verdadero | `_herramientas/demo/` |
| **Motor de capturas** | `capturas.js` (Playwright) + `anotar.js` (flechas/cajas/números sin pisarse) | `_herramientas/` |
| **Un script por tutorial** | `tNN_slug.js`: navega, prepara el estado y llama a `foto(nombre, marcas)` | `_herramientas/capturar/` |

## 2. Estructura de carpetas

```
documentacion/
├── README.md                  índice general + tabla de tutoriales con estado
├── _plantilla-tutorial.md     plantilla obligatoria
├── 00-inicio/                 qué es el sistema, roles, glosario, usuarios de la demo
├── 01-manual-usuario/         NN-slug.md  +  imagenes/NN-slug/01-nombre.png
├── 02-referencia/             cómo funciona cada módulo (reglas, modelos, permisos)
├── 03-conceptos/              conceptos transversales (mora, stock, planes…)
├── 04-operacion/              instalación, respaldos, tareas programadas
├── 05-faq/
├── llm/                       (opcional) paquete compacto por tutorial para asistentes de IA
├── _requerimientos/           (opcional) cambios pedidos que surgieron al documentar
├── _historico/                (opcional) documentación vieja archivada, no vigente
├── _capturas_tmp/             salida de pruebas (en .gitignore)
└── _herramientas/
    ├── README.md  METODO-DOCUMENTACION.md
    ├── capturas.js  anotar.js
    ├── capturar/   _comun.js  t00_humo.js  tNN_*.js
    └── demo/       entorno.sh  reset_demo.sh  levantar.sh  crear_base_demo.py  preparar_*.py  excel_ejemplo/
```

Convenciones: imágenes en `imagenes/<NN-slug>/<orden>-<nombre>.png` (el orden coincide con los pasos); nada generado a mano dentro de `imagenes/`.

## 3. Cómo es un tutorial

Encabezado YAML + secciones fijas (ver `_plantilla-tutorial.md`):

```
titulo · rol · modulo · permiso · verificado (AAAA-MM-DD contra el código) · version_sistema
> Para quién es · Tiempo · Necesitás
Para qué sirve            ← en lenguaje del dueño del negocio, no del sistema
Qué vas a lograr
Antes de empezar          ← permisos y configuración previa
Paso a paso               ← ### 1. … con captura + lista numerada que explica cada marca
Qué pasa por detrás       ← qué se mueve en el sistema (sin código)
Problemas frecuentes      ← tabla: Si te pasa… | Es porque… | Qué hacer
Siguiente paso
```

Reglas que lo hacen bueno:
- **Verificar contra el código antes de escribir.** Cada afirmación (qué botón hace qué, qué permiso pide, qué se recalcula) se confirma leyendo vistas/modelos. La fecha `verificado` lo certifica. Lo que no se pudo confirmar se anota como "a verificar", no se inventa.
- **Un flujo de trabajo por tutorial**, con nombre de tarea ("Anular un cobro"), no de pantalla.
- **Las marcas de la imagen se explican en el mismo orden** en la lista numerada de abajo.
- Empezar por el **para qué** (problema del negocio), no por los botones.
- Los tutoriales se **encadenan**: cada uno asume el estado que dejó el anterior, y el índice indica el orden.

### Lista única, SEO y lenguaje simple
- **`_herramientas/tutoriales.py`** es la fuente única de la lista de tutoriales (número, slug, título, `seo_title`, `seo_description`, palabras clave, rol, permiso y **archivos de código a verificar**). De ahí genera los esqueletos `.md`, los scripts de captura y la tabla del índice, y **valida** longitudes SEO y que las fuentes existan (`--check`). No pisa lo que ya existe.
- **`_guia-de-estilo.md`**: reglas de lenguaje simple (frases cortas, «vos», nombres de botón exactos, términos explicados) y SEO (`seo_title` ≤ 60, `seo_description` 120–155, un solo H1, respuesta directa arriba, preguntas reales como `###`, texto alternativo descriptivo en cada imagen) más un checklist de publicación.
- La plantilla suma al encabezado `seo_title`, `seo_description`, `palabras_clave`, `slug`, `grupo` y `estado`, y al cuerpo una sección *Preguntas frecuentes*.

## 4. Motor de capturas

### `capturas.js`
`abrir({ancho, alto, movil})` abre Chromium (Playwright) y devuelve un objeto con:
- `destino('01-manual-usuario/imagenes/NN-slug')` — carpeta de salida.
- `ir(ruta)`, `login(usuario, clave, ruta)` — navegación y sesión (la ruta de login se adapta por proyecto).
- `foto(nombre, marcas, {completa, clip})` — dibuja las marcas, saca el PNG y las borra del DOM.
- `cerrar()`.
Acepta `confirm()/alert()` nativos automáticamente. Usa `DEMO_URL` (por defecto `http://127.0.0.1:8765`).

### Marcas (`anotar.js`)
Cada marca: `{ sel | rect:[x,y,w,h], tipo:'caja'|'flecha', texto, n, lado:'arriba|abajo|izq|der', largo }`.
- `sel` es un selector CSS o `text=Algo`; `rect` son coordenadas fijas.
- `n` dibuja un círculo numerado (para citarlo en el texto); `texto` agrega una etiqueta.
- **Posicionamiento automático:** para cada etiqueta busca el mejor lugar libre **en cualquier ángulo**, evitando (a) otras etiquetas, (b) otros elementos marcados, (c) salirse de la pantalla. `lado` y `largo` son solo la preferencia inicial.
- Si no logra ubicarla sin conflicto, avisa `~ revisar a ojo (N): texto` → abrir la imagen y confirmar.
- Los elementos que dibuja llevan la clase `__doc_marca` y `position:fixed; z-index:2147483647`, por eso nunca alteran el layout.

### Un script de captura (esqueleto)
```js
const { abrir } = require('../capturas');
const { entrarAdmin, irALista } = require('./_comun');
(async () => {
  const c = await abrir({ ancho: 1440, alto: 860 });
  c.destino('01-manual-usuario/imagenes/NN-slug');
  await entrarAdmin(c);
  await irALista(c, 'app', 'modelo');
  await c.foto('01-lista', [
    { sel: '#searchbar', tipo: 'caja', lado: 'arriba', n: 1 },
    { sel: '#result_list', tipo: 'caja', texto: 'Listado', lado: 'izq', n: 2 },
  ]);
  await c.cerrar();
})().catch(e => { console.error(e); process.exit(1); });
```
`_comun.js` concentra lo repetitivo del proyecto (entrar, abrir menús, cerrar modales, cambiar de usuario). **Es lo único que cambia de verdad entre proyectos**, junto con los selectores.

Buenas prácticas de selectores: preferir ids estables (`#id_campo`, `data-*`) antes que textos o clases; dejar `waitForTimeout` generosos tras abrir modales y cargas AJAX; en pantallas largas hacer `scrollIntoViewIfNeeded` (lo hace `anotar.js` al medir).

## 5. La base de demo

Objetivo: que las capturas y los gráficos muestren **datos con volumen real** sin exponer a nadie.

### Receta
1. **Origen:** un backup real (`pg_dump -Fc` / `.dump`) restaurado en una **base nueva** llamada `<proyecto>_demo`. Nunca se opera sobre la base original.
2. **Seguro:** el script aborta si el nombre de la base no contiene `demo`; `entorno.sh` exporta las variables de base **antes** de arrancar Django (python-dotenv no pisa variables ya definidas) y aborta si `DB_NAME` no contiene `demo`.
3. **Anonimización determinística** (semilla fija → misma demo cada vez):

| Dato | Tratamiento |
|---|---|
| Nombres, apellidos | Listas de nombres/apellidos comunes, sorteados con semilla |
| DNI / CUIT | Aleatorios únicos; CUIT con **dígito verificador válido** (módulo 11) y coherente con el DNI en todas las tablas que lo repitan |
| Direcciones, teléfonos, mails, nacimiento | Inventados con formato local (`calle + número`, `11-xxxx-xxxx`, `@ejemplo.com`) |
| Sucursales, usuarios | Renombrados a roles claros (`dueno`, `admin_norte`…), todos con la misma clave de demo; se **conservan los ids** para no romper relaciones, grupos ni permisos |
| Respuestas de APIs externas (JSON crudo) | Se reescribe `identificacion`/`denominacion`, se conserva el resto |
| Firmas, IPs, geolocalización | Firma dibujada con trazos al azar, IPs de documentación (`203.0.113.x`), coordenadas con ruido |
| Textos libres (detalles, comentarios, notas) | Reemplazo por valores genéricos del rubro |
| Logs con nombres, sesiones, bitácora del admin | Se regeneran con nombres nuevos o se vacían |
| Rutas, tokens, enlaces de respaldo/Drive | Se vacían; se borran los registros de ejecuciones |
| Marca/nombre real del negocio | Se renombra (planes, claves por defecto, etc.) |
| **Montos, fechas, cuotas, pagos, estados, mora** | **Se conservan** — es lo que da realismo a los gráficos |

4. **Verificación automática:** al final el script arma la lista de valores prohibidos (nombre completo en varias formas, direcciones, DNI originales, nombres de la marca/usuarios reales) y recorre **todas las columnas de texto/JSON de la base** buscándolos. Debe imprimir `Sin restos de datos reales`. Falsos positivos conocidos: un número nuevo (p. ej. CUIT) puede contener por azar un DNI de 7 dígitos viejo.
5. **MEDIA aparte:** la demo usa su propio `MEDIA_ROOT` (`demo/media/`, en `.gitignore`) para no mostrar archivos reales; se copia el logo genérico y se generan las firmas ficticias.

### Estado entre tutoriales
Los tutoriales que modifican datos (cobrar, anular, importar) ensucian la demo. Regla: **`reset_demo.sh` antes de empezar una tanda**, y los `preparar_*.py` dejan cada escenario listo (por ejemplo una cuota vencida para cobrar). En el índice se documenta el orden de la cadena.

### Excel de ejemplo
Para tutoriales de importación: un generador (`generar_excels_ejemplo.py`) arma los `.xlsx` **contra la demo** (ids reales de créditos/cuotas) e incluye **filas con error a propósito** para mostrar cómo se leen los avisos del modo simulación (*dry-run*). Probar siempre los archivos con la función real de importación dentro de una transacción con rollback.

## 6. Puesta en marcha en un proyecto nuevo (checklist)

1. **Copiar** `documentacion/_herramientas/{capturas.js, anotar.js}` y la `_plantilla-tutorial.md`; crear las carpetas `00-inicio … 05-faq` y `.gitignore` (`_capturas_tmp/`, `demo/media/`, `demo/logs/`, `demo/*.log`).
2. **Ajustar `capturas.js`:** ruta de login por defecto y usuario/clave de demo. Verificar que la ruta del módulo `playwright-core` exista (`%APPDATA%/npm/node_modules/@playwright/cli/…`) o instalar Playwright.
3. **Escribir `_comun.js`** con las acciones repetidas del sistema (login, abrir un menú, cambiar de usuario, cerrar modales).
4. **Preparar la demo:** adaptar `crear_base_demo.py` (qué tablas tienen datos personales → qué se reemplaza; copiar la lista de tablas del modelo de datos). Revisar **todas** las tablas con `information_schema` buscando texto libre, JSON y archivos. Correr y mirar el informe de verificación.
5. **`entorno.sh` / `levantar.sh` / `reset_demo.sh`:** variables de base y media de demo; puerto fijo (8765); guardas contra apuntar a producción.
6. **Prueba de humo** (`t00_humo.js`): entra, saca 2 fotos con marcas. Abrir las imágenes y comprobar flechas y logo.
7. **Definir la lista de tutoriales** en `tutoriales.py` (agrupada por flujo de trabajo, con fuentes a verificar) y correrlo: genera esqueletos, stubs de captura y el índice con estados (🔲 / 🟡 / ✅).
8. **Primer tutorial de punta a punta** para validar el método (texto + script + capturas) antes de escribir el resto.
9. **Por cada tutorial:** leer el código → escribir el script de captura → correrlo (con `reset_demo` si hace falta) → mirar cada imagen (`~ revisar a ojo`) → escribir el `.md` con la plantilla → marcar ✅ y fechar `verificado`.
10. (Opcional) generar el resumen compacto en `llm/NN-slug/` para asistentes de IA.

## 7. Lecciones aprendidas (trampas ya pisadas)

- **Variables de entorno vs `.env`:** `python-dotenv` no sobrescribe lo ya exportado; por eso `entorno.sh` gana sobre `.env`. Sin eso, la demo apuntaría a la base real.
- **No leer producción para armar la demo:** restaurar el `.dump` en una base nueva y trabajar ahí. Evita permisos de producción y riesgo de modificarla.
- **Anonimizar relaciones, no solo columnas:** un DNI aparece en cliente, consulta a un organismo (BCRA), firma, logs y textos. Se calcula una vez por cliente y se propaga por JOIN.
- **Redondeos en los Excel de ejemplo:** un pago "igual a la cuota" redondeado hacia abajo (`8133.33 < 8133.333…`) es rechazado como "importe menor". Redondear **hacia arriba** al armar los datos.
- **Un filtro que borra o falla en silencio es peor que un error:** el verificador debe leer *todas* las columnas de texto, no una lista fija de tablas, para no olvidarse de ninguna.
- **Los logs son una fuga clásica** (listas de nombres en `detalles_*`, `resultado`, bitácora del admin, sesiones). Regenerarlos con nombres nuevos conserva la apariencia de uso real.
- **Estilo de heredocs en la terminal:** para crear archivos con comillas y backticks usar la herramienta de escritura de archivos, no `cat <<EOF` en una línea larga.
- **Imágenes sin sorpresas:** que el logo de la empresa (suele vivir en MEDIA) exista en la media de la demo, o sale como imagen rota en todas las capturas.
- **Un servidor de demo vivo y en segundo plano:** el servidor tiene que quedar corriendo mientras se capturan (en Claude Code, como tarea en segundo plano). Lanzarlo con `( ... &)` dentro de un comando que termina lo mata.
- **Antes de escribir un script, mirar la pantalla con una sonda** (`capturar/_probe.js <ruta>`): lista pestañas, ids de campos y botones. Evita adivinar selectores.
- **Pestañas y secciones plegadas:** con `changeform_format: horizontal_tabs` los campos están en pestañas; en fichas con secciones plegables hay que abrirlas (`.collapse` → `show`) antes de medir las marcas.
- **Medir con la ventana tan alta como la página** (`alto: 1700–3000`): si la página scrollea mientras se miden las marcas, las cajas quedan desfasadas.
- **Marcar siempre el encabezado de la tabla** (`#result_list thead`), no la tabla entera: una caja gigante deja flechas larguísimas.
- **Cadena completa reproducible:** `capturar/correr_todo.sh` resetea la demo y corre todos los scripts en el orden en que cada tutorial deja el estado que necesita el siguiente.
- **Hallazgos del código:** documentar un sistema obliga a leerlo; anotar lo raro que aparezca (valores fijos, avisos que no avisan) y reportarlo aparte.
- **Un script que se niega a ejecutarse en una base no-demo** vale más que cualquier advertencia en el README.

## 8. Qué se reutiliza tal cual y qué se reescribe

| Se copia sin cambios | Se adapta | Se escribe de cero |
|---|---|---|
| `anotar.js`, `capturas.js` (solo login/URL), plantilla, estructura de carpetas, este método | `entorno.sh`, `levantar.sh`, `reset_demo.sh`, `_comun.js` | `crear_base_demo.py` (tablas y campos propios), `preparar_*.py`, los `tNN_*.js` y los textos |

---

## 9. Variante bilingüe y demo desde cero (Gestión de Carnicerías)

- **Dos idiomas con los mismos scripts.** `capturas.js` lee `DOC_LANG` (`es` | `zh`): cambia el idioma del usuario en el sistema (igual que tocar ES / 中文), guarda en `<idioma>/01-manual-usuario/imagenes/` y acepta `texto: { es, zh }` en cada marca. Los selectores tienen que ser **estructurales** (ids, clases, `onclick`), nunca textos visibles, para que el mismo script sirva en los dos idiomas.
- **Demo sin anonimizar.** Si el sistema tiene un comando de datos de ejemplo (`seed_carniceria`), la demo se arma desde cero: `init_system` + `preparar_demo.py antes-del-seed` + seed + `preparar_demo.py despues-del-seed`. No hay datos reales que esconder.
- **Dos instancias.** Sucursal (`:8765`) y central (`:8766`), cada una con su base `*_demo`. La central es una copia de la sucursal (`CREATE DATABASE … TEMPLATE`) más dos sucursales clonadas con `bulk_create` (sin señales).
- **Ojo con `manage.py` que fija el puerto.** Acá `runserver` ignora el puerto que se le pasa y usa `RUNSERVER_PORT`: sin eso, la demo se levanta sobre el puerto de la app real.
- **Ventanas largas.** Para pantallas largas (recepción, planilla de desposte) se agranda el alto de la ventana **solo para esa foto** (`page.setViewportSize`). `anotar.js` primero desplaza hasta cada elemento y recién después mide todas las cajas, para que un scroll posterior no las deje corridas.
- **`prompt()` nativos.** `c.responderDialogos('texto')` contesta los `prompt()` (por ejemplo, el motivo al anular una comanda).
