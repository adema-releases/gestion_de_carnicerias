---
titulo: Gestión de Carnicerías 文档
seo_title: 肉店管理系统手册：分步教程
seo_description: 按岗位学习肉店系统：柜台、收银台、收货、每周结算、分店经理和总部，配截图，语言通俗。
palabras_clave: [肉店系统手册, 教程, 柜台, 收银台, 每周结算]
rol: 所有人
modulo: 总体
permiso: 无
estado: verificado
verificado: 2026-11-03（结构）；每个教程有自己的核对日期
version_sistema: 0.0.1
---

# Gestión de Carnicerías 文档

> **适合谁：** 加工厂、分店经理、收银员和屠宰工。  **内容：** 带截图的分步教程，**按岗位**编排，以及解释业务的核心概念。

Gestión de Carnicerías（肉店管理系统）是**一家加工厂和它自己的连锁肉店**使用的系统。每家肉店在**柜台**称重并录入订单，在**收银台**收款，在**收货**处接收和分割肉，每周二做公斤数的**每周结算**。加工厂在**总部**管理所有分店。每家店**断网也能营业**。

教程用**通俗的语言**写成，截图上有**箭头和编号**，正文按同样的编号解释，所有内容都**对照过系统代码**。截图里的系统界面是**中文**的。

> Versión en español: [../es/README.md](../es/README.md)

## 从哪里开始

| 我是…… | 先看…… |
|---|---|
| **新人**，不了解系统 | [从这里开始：系统是什么，谁负责什么](00-inicio/README.md) |
| **屠宰工**（助理或正式） | 01 登录 → 03 录入订单 → 04 作废 → 15 每周结算时盘点 |
| **收银员** | 01 登录 → 05 开班 → 06 收取订单款项 → 10 交班 |
| 负责收货的**正式屠宰工** | 11 接收发货单 → 13 分割 → 15–16 每周结算 |
| **分店经理** | 18 新增员工 → 19 工位和冷库 → 20 支付方式 → 22 每周检查 |
| **加工厂** | 23 总部面板 → 24 发货 → 25 往来账 → 26 商品目录 |

## 目录结构

| 文件夹 | 内容 | 适合谁 |
|---|---|---|
| [`00-inicio/`](00-inicio/README.md) | 业务模式、工位、谁做什么、分店的一天、词汇表 | 所有人 |
| [`01-manual-usuario/`](01-manual-usuario/) | **带截图的分步教程**，按岗位 | 所有人 |
| [`02-referencia/`](02-referencia/README.md) | 各角色权限、各种状态和规则 | 经理、技术支持 |
| [`03-conceptos/`](03-conceptos/README.md) | 订单和销售、分割和损耗、公斤数平衡、同步 | 所有人 |
| [`04-operacion/`](04-operacion/README.md) | 安装、同步、打印机、数据库 | 技术支持 |
| [`05-faq/`](05-faq/README.md) | 按主题整理的常见问题 | 所有人 |

## 教程

状态：🔲 待写 · 🟡 草稿 · ✅ 已对照代码并配好截图。

<!-- TUTORIALES:INICIO -->
### A · 入门
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 01 | [登录系统并选择设备工位](01-manual-usuario/01-ingresar-y-elegir-puesto.md) | 所有人 | ✅ |
| 02 | [切换语言：西班牙语或中文](01-manual-usuario/02-cambiar-idioma.md) | 所有人 | ✅ |

### B · 柜台
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 03 | [录入订单并发送到收银台](01-manual-usuario/03-armar-una-comanda.md) | 屠宰工 | ✅ |
| 04 | [我今天的订单以及如何作废](01-manual-usuario/04-mis-comandas-y-anular.md) | 屠宰工 | ✅ |

### C · 收银台
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 05 | [开班（打开收银台）](01-manual-usuario/05-abrir-la-caja.md) | 收银员 | ✅ |
| 06 | [收取订单的款项](01-manual-usuario/06-cobrar-una-comanda.md) | 收银员 | ✅ |
| 07 | [按件销售并用两种支付方式收款](01-manual-usuario/07-venta-por-unidad-y-pago-dividido.md) | 收银员 | ✅ |
| 08 | [赊账：记账销售并收回欠款](01-manual-usuario/08-fiado-y-cobro-de-deuda.md) | 收银员 | ✅ |
| 09 | [支出和取现](01-manual-usuario/09-gastos-y-retiros.md) | 收银员 | ✅ |
| 10 | [交班（关闭收银台）](01-manual-usuario/10-cerrar-la-caja.md) | 收银员 | ✅ |

### D · 收货与冷库
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 11 | [接收加工厂的发货单](01-manual-usuario/11-recibir-despacho-del-frigorifico.md) | 正式屠宰工和助理屠宰工 | ✅ |
| 12 | [接收其他供应商的货](01-manual-usuario/12-recibir-de-otro-proveedor.md) | 正式屠宰工和助理屠宰工 | ✅ |
| 13 | [冷库：移动和分割半边胴体](01-manual-usuario/13-camara-y-desposte.md) | 正式屠宰工 | ✅ |
| 14 | [查看各部位库存](01-manual-usuario/14-ver-el-stock.md) | 正式屠宰工、助理屠宰工和经理 | ✅ |

### E · 盘点与每周结算
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 15 | [每周结算：盘点剩余和丢弃的货](01-manual-usuario/15-liquidacion-semanal-contar.md) | 助理屠宰工和正式屠宰工 | ✅ |
| 16 | [查看差异并关闭每周结算](01-manual-usuario/16-liquidacion-cerrar.md) | 正式屠宰工和经理 | ✅ |
| 17 | [抽查盘点和历史记录](01-manual-usuario/17-conteo-de-control.md) | 正式屠宰工和经理 | ✅ |

### F · 分店经理
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 18 | [新增员工：用户、角色和工位](01-manual-usuario/18-alta-de-personal.md) | 分店经理 | ✅ |
| 19 | [工位、冷库和分店资料](01-manual-usuario/19-puestos-camaras-y-configuracion.md) | 分店经理 | ✅ |
| 20 | [每位收银员能用哪些支付方式](01-manual-usuario/20-medios-de-pago-de-la-cajera.md) | 分店经理 | ✅ |
| 21 | [财务看板和报表](01-manual-usuario/21-dashboard-y-reportes.md) | 分店经理 | ✅ |
| 22 | [每周检查：收银差额、作废订单和损耗](01-manual-usuario/22-controles-de-la-semana.md) | 分店经理 | ✅ |

### G · 加工厂总部
| # | 教程 | 工位 | 状态 |
|---|---|---|---|
| 23 | [总部面板：各分店的情况](01-manual-usuario/23-panel-central.md) | 加工厂 | ✅ |
| 24 | [给分店发货](01-manual-usuario/24-despachar-a-una-sucursal.md) | 加工厂 | ✅ |
| 25 | [分店往来账：汇款和调整](01-manual-usuario/25-cuenta-corriente-de-sucursales.md) | 加工厂 | ✅ |
| 26 | [商品目录：商品、价格、照片和分割模板](01-manual-usuario/26-catalogo-precios-y-plantillas.md) | 加工厂 | ✅ |
| 27 | [开设新分店](01-manual-usuario/27-abrir-una-sucursal-nueva.md) | 加工厂 | ✅ |
<!-- TUTORIALES:FIN -->

## 文档维护
- 截图由脚本在**虚构数据的演示库**上自动生成。界面改了，重新运行脚本，中西两种语言的截图会自动更新。见 [`../_herramientas/README.md`](../_herramientas/README.md)（西班牙语）。
- 小票、PDF 和 Excel 永远是西班牙语：顾客拿的是小票，小票打印机没有中文字体。
