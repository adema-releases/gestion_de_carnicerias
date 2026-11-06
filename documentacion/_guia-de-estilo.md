# Guía de estilo: lenguaje simple y SEO

Todo artículo y tutorial cumple esto antes de pasar a `estado: verificado`. Sirve para que lo entienda quien nunca usó el sistema **y** para que lo encuentre quien lo busca en Google o en un asistente de IA.

## 1. Lenguaje simple

| Hacer | Evitar |
|---|---|
| Frases de hasta 20 palabras. Una idea por frase | Párrafos largos con subordinadas |
| «Vos» y verbos en imperativo: *abrí, elegí, tocá, guardá* | Impersonal o infinitivo mezclado: *se procede a seleccionar* |
| Nombre del botón **exacto, en negrita**, como se ve en pantalla | «El botón de arriba», «la opción correspondiente» |
| Palabras del negocio: *comanda, media res, desposte, merma, liquidación* | Jerga técnica: *endpoint, queryset, sync, post_save* |
| Explicar el término la primera vez: «**Merma**: kilos que se pierden en hueso, grasa, lo que se tira y lo que falta» | Dar por sabido el glosario |
| Un paso = una acción | Pasos que mezclan «hacé A, luego B y revisá C» |
| Ejemplos con números concretos (`1,350 kg`, `$ 12.500/kg`) | Explicaciones solo abstractas |
| Decir qué pasa si algo sale mal, en la tabla de problemas | Dejar al lector sin salida |

Prueba final: leelo como si fueras el ayudante o la cajera de una sucursal que nunca vio el sistema. ¿Podría hacerlo sin preguntarte nada?

## 2. SEO: cómo lo encuentran

**Metadatos (encabezado del `.md`):**
- `seo_title`: **hasta 60 caracteres**. Empieza con la tarea y contiene la palabra clave. Ej.: *Cerrar la caja al final del día: arqueo y diferencias*.
- `seo_description`: **120–155 caracteres**. Dice qué vas a aprender y para qué sirve. Sin comillas ni relleno.
- `palabras_clave`: la frase principal + 2–3 variantes **tal como las escribiría una persona** («anular una comanda», no «gestión de anulación de comandas»).
- `slug`: la tarea en minúsculas con guiones, sin tildes ni números de versión.

**Contenido:**
- **Un solo `# H1`**, igual a la tarea. Debajo, `##` para secciones y `###` para pasos. No saltear niveles.
- **Respuesta directa arriba:** las primeras 2–3 líneas contestan la pregunta del título.
- **Palabra clave principal** en el título, en el primer párrafo y en al menos un `##`. Natural, sin repetirla en cada frase.
- **Preguntas reales como `###`** en la sección *Preguntas frecuentes*, con respuesta corta y completa (los buscadores las toman como respuesta destacada).
- **Texto alternativo en cada imagen:** describe lo que se ve y por qué importa. *«Ventana de pesaje con 1,350 kg, el subtotal y el botón Agregar»*, no *«captura1»*.
- **Nombres de archivo de imagen** con orden y tema: `03-pesar.png`.
- **Enlaces internos descriptivos** a otros tutoriales y conceptos: *«ver cómo se calcula la [merma](…)»*, nunca *«hacé clic acá»*.
- **Listas y tablas** para pasos, requisitos y problemas: se leen rápido y las toman los resultados enriquecidos.
- **Fecha de verificación** visible en el encabezado: da confianza y frescura.

## 3. Listo para publicar (checklist)

- [ ] Verificado contra el código (la fecha en `verificado:`; lo que no se pudo confirmar, anotado).
- [ ] `seo_title` ≤ 60 y `seo_description` 120–155 (`python documentacion/_herramientas/tutoriales.py --check`).
- [ ] Un solo H1; respuesta directa en las primeras líneas.
- [ ] Cada captura tiene texto alternativo descriptivo y sus marcas están explicadas **en el mismo orden**.
- [ ] Cada botón nombrado igual que en pantalla.
- [ ] Sin términos técnicos sin explicar.
- [ ] Tabla *Problemas frecuentes* completa y 2–4 *Preguntas frecuentes*.
- [ ] *Siguiente paso* con al menos 2 enlaces.
- [ ] Capturas rehechas sobre la demo actual y revisadas a ojo.

## 4. Dos idiomas

- Cada tutorial existe en `es/` y en `zh/`, con el **mismo número, slug y nombres de imagen**.
- Las capturas de `zh/` se sacan con **el sistema en chino** (`DOC_LANG=zh`): los botones que se nombran en el texto chino son los que se ven en esa captura.
- Los **datos** (nombres de productos, clientes, rubros, medios de pago) no se traducen: en el texto chino se citan tal cual, con la traducción entre paréntesis la primera vez. Ejemplo: «Fiado»（赊账）.
- Los tickets, PDF y Excel salen siempre en español: decirlo cuando aparezcan.
- En chino: frases cortas, 你 (no 您), términos constantes según el glosario de `zh/00-inicio/README.md`.
