const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');
const path = require('path');

let overlayWindow = null;

function createWindow() {
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize;
  const windowWidth = 640;
  const windowHeight = 480;

  overlayWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x: Math.round((screenWidth - windowWidth) / 2),
    y: Math.round(screenHeight * 0.16),
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    show: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  overlayWindow.loadFile(path.join(__dirname, 'index.html'));
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  overlayWindow.setAlwaysOnTop(true, 'floating');

  // NOTE: deliberately no 'blur' auto-hide.
  // The overlay should stay visible while a task runs in another app
  // (e.g. VS Code stealing focus). Only Escape or explicit dismiss closes it.
}

function showOverlay() {
  if (!overlayWindow) createWindow();
  overlayWindow.show();
  overlayWindow.focus();
  overlayWindow.webContents.send('overlay-shown');
}

function hideOverlay() {
  if (overlayWindow) {
    overlayWindow.webContents.send('overlay-hidden');
    overlayWindow.hide();
  }
}

function toggleOverlay() {
  if (overlayWindow && overlayWindow.isVisible()) {
    // If a task is mid-run, re-pressing the hotkey should refocus, not hide
    overlayWindow.webContents.send('hotkey-pressed-again');
  } else {
    showOverlay();
  }
}

app.whenReady().then(() => {
  createWindow();
  globalShortcut.register('Cmd+Shift+Space', toggleOverlay);
  app.dock.hide();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

ipcMain.on('escape-pressed', hideOverlay);
ipcMain.on('dismiss-overlay', hideOverlay);
ipcMain.on('refocus-overlay', () => {
  if (overlayWindow) overlayWindow.focus();
});

// Agent calls run here in the main process rather than the renderer, so the
// core API doesn't need permissive CORS (which would let any website the
// user visits drive the agent via localhost).
ipcMain.on('run-command', async (event, id, text) => {
  const send = (channel, ...args) => {
    if (!event.sender.isDestroyed()) event.sender.send(channel, id, ...args);
  };
  try {
    const response = await fetch('http://127.0.0.1:8100/api/v1/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: text }),
    });

    if (!response.ok || !response.body) {
      send('run-error', `Server error: ${response.status}`);
      return;
    }

    const decoder = new TextDecoder();
    for await (const chunk of response.body) {
      send('run-token', decoder.decode(chunk, { stream: true }));
    }
    send('run-done');
  } catch (err) {
    send('run-error', err.message || 'Connection failed. Is AuraOS running?');
  }
});

ipcMain.on('resize-overlay', (event, height) => {
  if (overlayWindow) {
    const [width] = overlayWindow.getSize();
    overlayWindow.setSize(width, Math.min(Math.max(height, 96), 640));
  }
});