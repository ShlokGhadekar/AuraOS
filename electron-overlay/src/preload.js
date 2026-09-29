const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('aura', {
  onShown: (callback) => ipcRenderer.on('overlay-shown', callback),
  onHidden: (callback) => ipcRenderer.on('overlay-hidden', callback),
  onHotkeyAgain: (callback) => ipcRenderer.on('hotkey-pressed-again', callback),
  escapePressed: () => ipcRenderer.send('escape-pressed'),
  dismiss: () => ipcRenderer.send('dismiss-overlay'),
  resize: (height) => ipcRenderer.send('resize-overlay', height),

  runCommand: (text, onToken, onDone, onError) => {
    // Main process does the HTTP call and streams chunks back over IPC
    const id = `${Date.now()}-${Math.random()}`;
    const handlers = {
      'run-token': (_e, runId, chunk) => runId === id && onToken(chunk),
      'run-done':  (_e, runId) => runId === id && finish(onDone),
      'run-error': (_e, runId, message) => runId === id && finish(onError, message),
    };
    function finish(callback, ...args) {
      for (const [channel, handler] of Object.entries(handlers)) {
        ipcRenderer.removeListener(channel, handler);
      }
      callback(...args);
    }
    for (const [channel, handler] of Object.entries(handlers)) {
      ipcRenderer.on(channel, handler);
    }
    ipcRenderer.send('run-command', id, text);
  },
});
