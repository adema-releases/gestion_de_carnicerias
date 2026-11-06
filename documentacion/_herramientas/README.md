# Herramientas de documentación

Generan las capturas de pantalla (con flechas, recuadros y números) de los tutoriales, **en español y en chino**, sobre una **base de demostración con datos inventados** que nunca toca la base real.

## Requisitos
- Windows con el `venv` del proyecto (`venv/Scripts/python.exe`) y PostgreSQL local (la clave se toma de `DB_PASSWORD` del `.env`).
- Node.js y Playwright (`npm i -g @playwright/cli`; trae Chromium).

## La base de demo
`demo/reset_demo.sh` crea dos bases desde cero (se niega a trabajar si el nombre no contiene `demo`):

| Base | Qué es | Cómo se arma |
|---|---|---|
| `gestion_de_carnicerias_demo` | La PC de la sucursal **S001 · Centro** | `init_system` → `preparar_demo.py antes-del-seed` → `seed_carniceria` (14 días de ventas, comandas, remitos, despostes y una liquidación) → `preparar_demo.py despues-del-seed` (fotos, gerente con admin, un despacho por recibir, una media vieja en cámara, cobro automático) |
| `gestion_de_carnicerias_demo_central` | El frigorífico | Copia de la anterior + `preparar_demo.py central` (sucursales Norte y Sur con sus números, despachos, remesas y el usuario `frigorifico`) |

Usuarios: ver [`../es/00-inicio/README.md`](../es/00-inicio/README.md#usuarios-de-la-demostración). Clave de todos: `Carne1234`.

## Uso
```bash
bash documentacion/_herramientas/demo/reset_demo.sh           # (re)crea las dos bases de demo
bash documentacion/_herramientas/demo/levantar.sh              # sucursal → http://127.0.0.1:8765   (dejar corriendo)
bash documentacion/_herramientas/demo/levantar.sh central      # central  → http://127.0.0.1:8766   (dejar corriendo)
bash documentacion/_herramientas/capturar/correr_todo.sh       # rehace TODAS las capturas, es y zh, en orden
bash documentacion/_herramientas/capturar/correr_todo.sh zh    # solo chino
DOC_LANG=zh bash documentacion/_herramientas/capturar/_correr.sh t03_armar_una_comanda   # un script suelto
python documentacion/_herramientas/tutoriales.py               # actualiza los índices y valida imágenes y enlaces
```

> `manage.py` fija el puerto con `RUNSERVER_PORT`; `levantar.sh` ya lo exporta. No levantes la demo con `runserver 127.0.0.1:8765` a mano: terminaría en el puerto 8250 de la app real.

## Orden de la cadena
Los tutoriales que modifican datos dejan el estado que necesita el siguiente (ver el encabezado de `capturar/correr_todo.sh`): mostrador → caja → cierre → apertura → liquidación → recepción → desposte → control → gerente → central. Para correr un script suelto conviene partir de `reset_demo.sh`.

## Archivos
| Archivo | Qué hace |
|---|---|
| `capturas.js` | Abre Chromium, entra, elige el puesto, cambia el idioma, saca la foto con marcas (`foto(nombre, marcas)`) |
| `anotar.js` | Dibuja recuadros, flechas y números sin pisar otras etiquetas ni salirse de la pantalla |
| `capturar/_comun.js` | `entrar(c, usuario, puesto)`, `irALista`, `irAAlta`, `elegir` (selects del admin), `abrirFila`, `fotoVisor` (imagen de un visor de balanza) |
| `capturar/_caja.js`, `_recepcion.js` | Ayudas de la terminal de caja y de recepción/conteo |
| `capturar/tNN_*.js` | Un script por tutorial |
| `capturar/_probe.js` | Sonda: lista ids, pestañas y botones de una pantalla (`node _probe.js pos/mostrador/ oficial1 "Mostrador 1"`) |
| `capturar/_recorrido.js` | Foto sin marcas de varias pantallas, para explorar |
| `demo/preparar_demo.py` | Pasos de la demo y escenarios (`sin-turno-abierto`, `idioma-es`, `idioma-zh`) |
| `tutoriales.py` | Lista única de tutoriales (es/zh): índices de los README y validación |

## Escribir un script de captura
Copiar uno parecido. Cada marca es `{ sel | rect, tipo: 'caja'|'flecha', texto: { es, zh }, n, lado, largo }`. Reglas:
- **Selectores estructurales** (`#id`, clases, `[onclick*=…]`), nunca textos visibles: el mismo script corre en los dos idiomas.
- Si `anotar.js` avisa `~ revisar a ojo`, abrir la imagen y confirmar.
- Para pantallas largas, agrandar el alto de la ventana solo para esa foto.
