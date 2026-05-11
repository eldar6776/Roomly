const { app, BrowserWindow } = require('electron')
const path = require('path')

function createWindow () {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    autoHideMenuBar: true,
    backgroundColor: '#1e1e1e', // Tamna pozadina da se izbjegne bijeli bljesak
    icon: path.join(__dirname, 'assets/icon.png') // Ako postoji
  })

  win.loadFile('index.html')
  // win.webContents.openDevTools() // Otkomentarisati za debug
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
