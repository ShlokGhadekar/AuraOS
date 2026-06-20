const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('aura', {
  onShown: (callback) => ipcRenderer.on('overlay-shown', callback),
  onHidden: (callback) => ipcRenderer.on('overlay-hidden', callback),
  onHotkeyAgain: (callback) => ipcRenderer.on('hotkey-pressed-again', callback),
  escapePressed: () => ipcRenderer.send('escape-pressed'),
  dismiss: () => ipcRenderer.send('dismiss-overlay'),
  resize: (height) => ipcRenderer.send('resize-overlay', height),

  runCommand: async (text, onToken, onDone, onError) => {
    try {
      const response = await fetch('http://localhost:8100/api/v1/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: text }),
      });

      if (!response.ok || !response.body) {
        onError(`Server error: ${response.status}`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        onToken(decoder.decode(value, { stream: true }));
      }
      onDone();
    } catch (err) {
      onError(err.message || 'Connection failed. Is AuraOS running?');
    }
  },
});