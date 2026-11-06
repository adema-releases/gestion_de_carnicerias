---
titulo: 运行与维护
seo_title: 运行：安装、同步、打印机和数据库
seo_description: 给负责安装和维护系统的人：分店电脑、平板、与总部同步、打印机和钱箱、数据库。
palabras_clave: [安装肉店系统, 同步, 小票打印机, config.env]
rol: 技术支持
modulo: 安装、同步、打印
permiso: 超级用户
estado: verificado
verificado: 2026-11-03 对照 run_server.py、postgres_local.py、installer.nsi、core/agente_sync.py、pos/printing.py 和 README.md
version_sistema: 0.0.1
---

# 运行与维护

> **适合谁：** 负责安装和维护系统的人。**日常使用不需要看。** 完整技术说明见[项目 README](../../../README.md)（西班牙语）。

## 分店电脑

- Windows 安装程序自带 **PostgreSQL** 数据库：不用另外安装。
- 第一次运行时在 `C:\GestionDeCarnicerias\pgdata` 创建数据库（本地端口 5433）。
- 登录 Windows 后应用自动启动，通过**任务栏托盘图标**控制。退出时会关闭数据库。
- 配置文件是 `C:\GestionDeCarnicerias\config.env`：

  ```env
  SYNC_MODO=sucursal
  SYNC_URL=https://<总部地址>
  SYNC_TOKEN=<分店令牌>
  ```

## 平板和手机

- 连上**肉店的 Wi-Fi**，打开 `http://<电脑 IP>:8250/pos/`。
- 安装程序会在 Windows 防火墙开放 8250 端口。
- 应用启动时会在日志里记下电脑的 IP。建议在路由器上固定这个 IP。

## 同步

- 只要配置了 `SYNC_URL` 和 `SYNC_TOKEN`，电脑每 60 秒上传自己的变动，并下载总部的变动。
- 断网时分店照常营业；变动排队等待上传。
- 手动执行：`python manage.py sincronizar` · `--inicial`（已有数据的分店）· `--catalogo`（把商品目录上传到空的总部）· `--loop 60`。
- 加工厂在[总部面板](../01-manual-usuario/23-panel-central.md)上看到每家分店的最近同步时间。

## 小票打印机和钱箱

- 在收银台（**设置打印机**）或*设置 → POS — General*里填入打印机的准确名称。
- 销售含**现金**时钱箱自动打开。需要 `pywin32`。
- 没有打印机时，销售照常登记。

## 数据库和备份

- 分店和总部都用 PostgreSQL。
- 备份分店电脑：用 `pg_dump` 导出（端口 5433，用户 `carnicerias`，密码在 `C:\GestionDeCarnicerias\db\clave_postgres.txt`）。
- 如果新版本带来更高的 PostgreSQL 大版本，需要先运行 `pg_upgrade`，否则应用不会用旧数据启动。

## 语言

- 西班牙语和中文。更新翻译见[项目 README](../../../README.md)的 *Internacionalización* 一节。
