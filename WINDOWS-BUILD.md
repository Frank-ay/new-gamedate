# Windows 打包指南

把 `gamedata-monitor` 项目在一台 Windows 10/11 (x64) 机器上打成 `.exe` 安装包,然后把 `.exe` 发给最终使用的同事。最终同事不需要装任何东西。

---

## 一、Windows 打包机器需要装的东西(一次性)

只在**打包用的那台 Windows 机器**上装,**给同事用的最终机器不需要**这些。

### 1. Node.js 20 LTS(必装)

下载安装:<https://nodejs.org/zh-cn/download>

选 **20.x.x LTS / Windows Installer (.msi) / 64-bit**,一路下一步即可。

安装完后开个新的 `cmd` 或 `PowerShell` 窗口,输入:

```cmd
node --version
npm --version
```

能看到版本号(如 `v20.18.0`)就说明装好了。

### 2. Visual Studio Build Tools(可能要装)

`better-sqlite3` 这个原生模块在某些情况下需要 C++ 编译环境。**先不装,直接打包,失败了再装**。

如果打包步骤 `npm install` 报 `MSBUILD : error` 或 `node-gyp` 编译失败:

下载 **Visual Studio Build Tools**:<https://visualstudio.microsoft.com/visual-cpp-build-tools/>

安装时勾选 **「使用 C++ 的桌面开发」**(Desktop development with C++),其它全部不勾。装完重启再跑打包脚本。

> 如果是新版 npm + 新版 Node,大多数情况下会自动下载 prebuilt binary,**不需要**装 Build Tools。

### 3. 网络

打包脚本会从 GitHub 下载 ~40MB 的 Python runtime,再从 PyPI 装 ~150MB 的 Python 库。需要能访问 `github.com` 和 `pypi.org`。

如果国内网络不顺,建议:
- 开个代理跑打包
- 或者预先在能联网的环境下打包,把整个 `node_modules/` + `.cache/` + `resources/` 拷过来再跑

---

## 二、把代码搬到 Windows 机器

把整个 `gamedata-monitor` 文件夹拷到 Windows 机器上(U 盘 / 网盘 / GitHub clone 都行)。

**注意**:拷之前可以删掉这几个目录省空间,Windows 机器上跑脚本时会重新生成:

| 目录 | 是否要拷 | 说明 |
|---|---|---|
| `node_modules/` | ❌ 不要拷 | 平台相关,Windows 上要重新装 |
| `.venv/` | ❌ 不要拷 | mac Python 虚拟环境,Windows 不用 |
| `resources/python/` | ❌ 不要拷 | mac 的 Python runtime,Windows 要重下 |
| `.cache/` | 可选 | 缓存目录,有的话能省一次下载,但平台不匹配 |
| `dist/` | ❌ 不要拷 | mac 旧产物 |
| `data/` | ❌ **不要拷** | 你 mac 上采集的数据库,装到 Windows 上会污染同事的数据 |
| `logs/` | ❌ 不要拷 | mac 旧日志 |

**必须拷的目录与文件**:`electron/` `collector/` `analysis/` `dashboard/` `scripts/` `build/` `package.json` `package-lock.json` `requirements.txt` `config.yaml` `README.md` `WINDOWS-BUILD.md`

或者最省事:整个文件夹直接拷,反正多余的脚本会重新装。

---

## 三、打包(一行命令)

在 Windows 机器上开 `cmd`,进到 `gamedata-monitor` 目录,然后:

```cmd
scripts\build-windows.bat
```

脚本会自动:

1. 检查 Node.js 和 tar 是否就绪
2. `npm install` 装 Node 依赖,自动重编 `better-sqlite3` 到 Electron ABI
3. 下载 Python runtime(`resources/python/python.exe`)
4. 把 streamlit/pandas/plotly/requests 装到嵌入式 Python
5. 用 `electron-builder` 打包 `.exe`

第一次跑大概 **10-15 分钟**,主要时间花在下载上。后续跑会快很多(依赖都缓存)。

产物在 `dist\GameDataMonitor Setup 1.0.0.exe`,大概 **300-350 MB**。

---

## 四、在 Windows 机器上测一下 .exe

**重要**:不要只看到产物文件就以为成功了,必须装一遍试试。

1. 双击 `dist\GameDataMonitor Setup 1.0.0.exe`
2. NSIS 安装界面会弹出来,默认装到 `%LocalAppData%\Programs\GameDataMonitor\`,可改路径
3. 装完桌面有快捷方式,双击启动
4. **第一次启动会比较慢**(splash 屏会显示「首次启动 5-10 秒」),Electron 在后台拉起 Streamlit
5. 看到 dashboard 出来后,试一下:
   - 点侧边栏「立即采集」按钮 → 看是否能跑(可能因为 Google Play 需要外网访问而失败,正常)
   - 切换到「热榜追踪」「品类趋势」等子页面 → 看 plotly 图表能不能渲染
6. 退出应用,看 `%APPDATA%\gamedata-monitor\` 目录(注意是 Roaming 那个)有没有 `data/` 和 `logs/`

如果以上都正常,**.exe 就是可以发给同事的产物**。

> Windows SmartScreen 第一次会弹「Windows 已保护你的电脑」拦截窗,因为我们没买代码签名证书。点「**更多信息 → 仍要运行**」即可。

---

## 五、发给同事

只发 `dist\GameDataMonitor Setup 1.0.0.exe` 一个文件给同事就够了(~300 MB,微信/邮件可能传不过去,用网盘或公司内网 share)。

同事拿到后:
1. 双击 `.exe`
2. 第一次过 SmartScreen 拦截(更多信息 → 仍要运行)
3. NSIS 一路下一步装完
4. 桌面双击图标即可使用

**同事的机器不需要装 Node.js、Python 或任何东西**,所有运行时都已经打包进 `.exe` 里了。

---

## 六、常见报错

| 报错 | 解决 |
|---|---|
| `'node' 不是内部或外部命令` | Node.js 没装好,或没开新窗口。重新装一遍 Node.js,然后**关掉所有 cmd 重新打开** |
| `MSBUILD : error MSB...` 或 `node-gyp ERR! find Python` | 装 Visual Studio Build Tools(见上面第一节第 2 条) |
| `tar: 不是内部或外部命令` | Windows 版本太旧。升级到 Windows 10 1803 以上,或手动装 7-Zip / Git for Windows(自带 tar) |
| `fetch-python` HTTP 403 / 超时 | 网络问题,开代理或换网络 |
| `electron-builder` `cannot find module` | 之前 `npm install` 没跑完。删掉 `node_modules` 重新跑脚本 |
| `electron-builder` 报 `sign` 相关错误 | 不应该出现 — 配置里已禁用签名。如果出现请告诉我 |

---

## 七、升级 / 改 BUG 重新打包

改完代码后:

```cmd
REM 直接重跑同一个脚本即可,会复用 node_modules 和 resources/python/
scripts\build-windows.bat
```

如果想 **完全干净重打**:

```cmd
rmdir /s /q node_modules dist resources\python .cache
scripts\build-windows.bat
```

---

## 八、版本号

每次发布建议在 `package.json` 改一下 `version`,比如 `1.0.0` → `1.0.1`,产物文件名会跟着变,同事一眼就能看出来是新版。
