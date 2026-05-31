const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    moveWindow: (pos) => ipcRenderer.send('move-window', pos),
    closeWindow: () => ipcRenderer.send('close-app'),
    startListening: () => ipcRenderer.send('start-listening'), 
    onBrainData: (callback) => ipcRenderer.on('asuna-brain-data', (event, value) => callback(value))
});