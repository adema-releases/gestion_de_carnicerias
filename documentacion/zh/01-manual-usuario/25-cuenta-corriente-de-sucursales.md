---
titulo: 分店往来账：汇款和调整
seo_title: 分店往来账：汇款和调整
seo_description: 登记每家分店汇来的钱（汇款）和更正（调整）。发货单会自动增加欠款。
palabras_clave: [分店往来账, 汇款, 欠款调整, 分店余额]
slug: cuenta-corriente-de-sucursales
grupo: G · 加工厂总部
rol: 加工厂
modulo: 总部 · 分店往来账
permiso: 总部的工作人员账号
estado: verificado
verificado: 2026-11-03 对照 central/models.py (MovimientoCuentaSucursal) 和 central/admin.py
version_sistema: 0.0.1
---

# 分店往来账：汇款和调整

> **适合谁：** 加工厂。  **时间：** 1 分钟。

每家分店**欠**发给它的货款，用**汇款**来**还**。收到汇款时，在**分店往来账 → 添加**里登记，类型选**汇款**，金额填**正数**：系统会从欠款里扣掉。

## 三种账目
| 类型 | 是什么 | 怎么录入 |
|---|---|---|
| **发货（借方）** | 发出的货 | 保存发货单时**自动**生成 |
| **收到汇款（贷方）** | 分店汇来的钱 | 手动，填正数：保存时自动变成减项 |
| **调整** | 更正（例如折让） | 手动：正数增加欠款，负数减少。一定要写说明 |

## 操作步骤

### 1. 查看账目
![各分店的账目和添加按钮](imagenes/25-cuenta-corriente-de-sucursales/01-movimientos.png)

1. 所有分店的**发货、汇款和调整**。可以按分店筛选。
2. **添加**一条账目。

### 2. 登记汇款
![表单：分店、汇款类型、正数金额和说明](imagenes/25-cuenta-corriente-de-sucursales/02-registrar-remesa.png)

1. **分店。**
2. **类型：** 收到汇款。
3. **金额：** 正数。
4. **说明：** 例如“现金汇款”。点**保存**。

### 3. 汇款减少欠款
![已登记的汇款显示为负数](imagenes/25-cuenta-corriente-de-sucursales/03-remesa-registrada.png)

1. 保存为**负数**：余额减少。各分店的余额在[面板](23-panel-central.md)的**账户余额**一栏。

## 常见疑问

### 发货单要在这里录吗？
不用：保存发货单时会自动生成。

## 下一步
- [商品目录：商品、价格、照片和模板](26-catalogo-precios-y-plantillas.md)。
