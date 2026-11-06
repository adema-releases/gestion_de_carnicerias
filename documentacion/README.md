# Gestión de Carnicerías · Documentación / 文档

| | |
|---|---|
| 🇦🇷 **Español** | [Manual de usuario, conceptos y preguntas frecuentes](es/README.md) |
| 🇨🇳 **中文** | [用户手册、核心概念和常见问题](zh/README.md) |

Tutoriales paso a paso **por puesto** (mostrador, caja, recepción, liquidación, gerente y central del frigorífico), con capturas con flechas y números, en lenguaje simple.
按岗位编写的分步教程（柜台、收银台、收货、周结算、经理和冷冻厂总部），配有带箭头和编号的截图，语言通俗易懂。

## Estructura

```
documentacion/
├── README.md                 esta portada
├── es/                       documentación en español
│   ├── README.md             índice y tabla de tutoriales
│   ├── 00-inicio/            la idea del negocio, puestos, quién hace qué, glosario
│   ├── 01-manual-usuario/    27 tutoriales  +  imagenes/NN-slug/*.png (capturas en español)
│   ├── 02-referencia/        permisos por rol, estados y reglas
│   ├── 03-conceptos/         comanda, desposte, merma, balance de kilos, sincronización
│   ├── 04-operacion/         instalación, sincronización, impresora, base
│   └── 05-faq/               problemas frecuentes
├── zh/                       la misma estructura, en chino (capturas con el sistema en chino)
├── _guia-de-estilo.md        reglas de redacción
├── _plantilla-tutorial.md    plantilla de cada tutorial
├── _hallazgos.md             cosas del código que aparecieron al documentar
└── _herramientas/            capturas automáticas (Playwright) y base de demostración
```

## Para quien mantiene esta documentación
- Las capturas **no se sacan a mano**: un script por tutorial maneja el sistema, dibuja flechas y números y guarda las imágenes, en español y en chino. Ver [`_herramientas/README.md`](_herramientas/README.md).
- Todo se saca sobre una **base de demostración con datos inventados**, nunca sobre la base real.
- La lista de tutoriales vive en [`_herramientas/tutoriales.py`](_herramientas/tutoriales.py): genera los índices y valida imágenes y enlaces.
- El método completo (para replicarlo en otro proyecto): [`_herramientas/METODO-DOCUMENTACION.md`](_herramientas/METODO-DOCUMENTACION.md).
