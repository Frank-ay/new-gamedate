# GameDataMonitor

Google Play 美国市场游戏增长监控 桌面版 — 通过 Electron 外壳一键运行,无需安装 Node 或 Python。

| 平台 | 产物 | 架构 |
|---|---|---|
| macOS | `GameDataMonitor-1.0.0-arm64.dmg` | Apple Silicon (arm64) |
| Windows | `GameDataMonitor Setup 1.0.0.exe` | x64(NSIS) |

## 架构

| 层 | 技术栈 | 入口 |
|---|---|---|
| 外壳 | Electron 31 | [electron/main.cjs](electron/main.cjs) |
| 数据采集 | Node.js + better-sqlite3 + google-play-scraper | [collector/collect.mjs](collector/collect.mjs) |
| 数据分析 | Python + pandas + sqlite3 | [analysis/growth_scorer.py](analysis/growth_scorer.py) |
| 数据展示 | Streamlit + plotly | [dashboard/app.py](dashboard/app.py) |

- Streamlit 作为 127.0.0.1 上的本地 web 服务,Electron 主进程 spawn 它,然后在 `BrowserWindow` 内 `loadURL`
- Node collector 用 `process.execPath + ELECTRON_RUN_AS_NODE=1` 启动,免单独打包 Node binary
- Python runtime 用 [python-build-standalone](https://github.com/indygreg/python-build-standalone) 嵌入到 `resources/python/`
- 所有用户数据(`games.db`、icons、logs、用户改过的 config.yaml)落在 `app.getPath('userData')`,与应用包解耦

## 路径约定

所有业务代码通过 `APP_*` 环境变量读路径,由 Electron 主进程 [electron/paths.cjs](electron/paths.cjs) 注入。

| 环境变量 | dev | prod |
|---|---|---|
| `APP_PYTHON` | `.venv/bin/python3` | `Contents/Resources/python/bin/python3` (mac) / `resources/python/python.exe` (win) |
| `APP_NODE_BIN` | 系统 `node` | `process.execPath`(Electron exe) |
| `APP_ROOT` | 仓库根 | `Contents/Resources/app.asar.unpacked` |
| `APP_DATA_DIR` | `仓库/data` | `userData/data` |
| `APP_LOG_DIR` | `仓库/logs` | `userData/logs` |
| `APP_DB_PATH` | `仓库/data/games.db` | `userData/data/games.db` |
| `APP_ASSETS_DIR` | `仓库/data/assets/icons` | `userData/data/assets/icons` |
| `APP_CONFIG_PATH` | `仓库/config.yaml` | `userData/config.yaml` |

`userData` 目录:
- macOS: `~/Library/Application Support/gamedata-monitor/`
- Windows: `%APPDATA%\gamedata-monitor\`

## 开发(dev)

```bash
# 1. 安装 Node 依赖(自动 electron-rebuild 编译 better-sqlite3 到 Electron ABI)
npm install

# 2. 准备 Python venv(dev 用 .venv,prod 用嵌入式 Python)
python3.13 -m venv .venv
.venv/bin/pip install streamlit==1.36.0 pandas==2.2.3 plotly==5.24.1 requests==2.32.3

# 3. 启动
npm start
```

dev 模式下 [electron/paths.cjs](electron/paths.cjs) 走 `isDev` 分支,所有路径用仓库内的 `.venv`、`data/`、`logs/`,不会污染 userData。

> 注意:dev 模式下 `npm run collect`(直接 `node`)因 ABI 不匹配会失败 — better-sqlite3 已被编译到 Electron 31 ABI(NODE_MODULE_VERSION 125),而系统 Node 22 是 127。要单独跑 collector,用 `ELECTRON_RUN_AS_NODE=1 ./node_modules/.bin/electron collector/collect.mjs`,或者直接从 dashboard 侧边栏点「立即采集」。

## 打包(本机)

### 准备 Python runtime(一次性,首次或升级时跑)

```bash
npm run fetch:python          # 下载 python-build-standalone 到 resources/python/
npm run install:py-deps       # 装 requirements.txt 到嵌入 Python(dev/调试用)
npm run install:py-deps:strip # 装 + 裁剪 tests/__pycache__(打包前用)
```

### 出当前平台的安装包

```bash
# macOS arm64
CSC_IDENTITY_AUTO_DISCOVERY=false npm run dist:mac

# Windows x64(在 Windows 机器上跑)
npm run dist:win
```

产物在 `dist/` 目录,如:
- `dist/GameDataMonitor-1.0.0-arm64.dmg`
- `dist/GameDataMonitor Setup 1.0.0.exe`

> 不带签名的 `.dmg`:用户首次打开时 macOS Gatekeeper 会拦截,需要**右键 → 打开 → 仍要打开**;之后双击即可。Windows 不签名会触发 SmartScreen 警告,选「仍要运行」可继续。

## CI/CD(GitHub Actions)

[`.github/workflows/build.yml`](.github/workflows/build.yml) 在 tag 推送(`v*`)或手动触发时,矩阵构建 macOS + Windows 安装包并自动发布 Release。

```bash
# 触发发布
git tag v1.0.0
git push origin v1.0.0
```

## 代码签名 + 公证(可选,但强烈建议)

### macOS — Apple Developer Program($99/年)

1. 申请 Apple Developer Program 账号
2. 在 Apple Developer 后台创建 **Developer ID Application** 证书,导出为 `.p12`
3. 用 `base64 -i cert.p12` 编码,放到 GitHub Secrets:
   - `MAC_CERT_BASE64`:.p12 文件的 base64
   - `MAC_CERT_PASSWORD`:.p12 的密码
   - `APPLE_ID`:Apple Developer 账号邮箱
   - `APPLE_APP_SPECIFIC_PASSWORD`:在 appleid.apple.com 生成的 app-specific password
   - `APPLE_TEAM_ID`:Developer 后台的 Team ID

CI workflow 会自动用这些 secrets 给 .dmg 签名 + notarytool 公证。

### Windows — OV/EV 代码签名证书($80-300/年)

1. 从 DigiCert / Sectigo / SSL.com 购买 OV(便宜)或 EV(贵但用户不需要重复点确认)证书
2. 拿到 `.pfx` 后,放到 GitHub Secrets:
   - `WIN_CSC_LINK`:.pfx 文件 base64
   - `WIN_CSC_KEY_PASSWORD`:.pfx 密码

> OV 证书签名后 Windows SmartScreen 仍会拦截首次安装(需积累信誉);EV 证书装机即过。

## 数据迁移(从旧版本)

如果之前在 dev 模式下采集过数据,想把数据带到打包版:

```bash
cp data/games.db ~/Library/Application\ Support/gamedata-monitor/data/games.db   # mac
cp data/games.db %APPDATA%\gamedata-monitor\data\games.db                          # win
```

## 配置

[config.yaml](config.yaml) — Google Play 采集参数(国家、品类、抓取数量、重试次数、采集间隔等)。

首次启动时,Electron 把仓库内的 `config.yaml` 复制到 userData,用户可在 userData 内修改,不影响应用包。

## 维护

- 升级 PBS Python:改 [scripts/python-runtime.json](scripts/python-runtime.json) 的 `release` / `pythonVersion`,清空 `sha256` 字段,重跑 `npm run fetch:python` 让脚本回写新 SHA256
- 升级 npm/python 依赖:改 `package.json` / `requirements.txt`,跑 `npm install` / `npm run install:py-deps` 重装
- 重建 better-sqlite3:`./node_modules/.bin/electron-builder install-app-deps`
