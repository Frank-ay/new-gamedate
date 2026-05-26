// electron/preload.cjs
// 预留:暴露 Electron 主进程能力给渲染层(目前 Streamlit 自己渲染,这里只挂安全桥接,
// 留给未来"主进程菜单 → 触发采集"等扩展使用)。

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('appApi', {
  collectStart: () => ipcRenderer.invoke('collect:start'),
  collectStatus: () => ipcRenderer.invoke('collect:status'),
  collectStop: () => ipcRenderer.invoke('collect:stop'),
});
