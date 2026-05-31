const { app, BrowserWindow, ipcMain } = require('electron');

const { spawn } = require('child_process');

const path = require('path');

let pythonProcess = null;

function createWindow() {
    const win = new BrowserWindow({
        width: 450,
        height: 600,
        transparent: true,
        frame: false,
        alwaysOnTop: true,
        hasShadow: false,
        webPreferences: {
            // ПІДКЛЮЧАЄМО НАШ МІСТОК
            preload: path.join(__dirname, 'preload.cjs'),
            nodeIntegration: false,
            contextIsolation: true,
        },
    });

    win.loadURL('http://localhost:8080');

    const bridgePath = path.join(__dirname, '../Asuna/bridge.py');
    pythonProcess = spawn('python', [bridgePath]);
    pythonProcess = spawn('python', ['-u', bridgePath]);
    pythonProcess.on('exit', (code) => {
    console.log(`Python-процес завершився з кодом ${code}`);
    
    // Якщо Python закрився успішно (код 0) або взагалі завершив роботу,
    // ми примусово закриваємо додаток Electron!
    if (win) {
        win.destroy(); // або win.close();
    }
    app.quit(); // Повністю закриває Electron додаток
});
    pythonProcess.stdout.on('data', (data) => {
        const output = data.toString();
        try {
            const json = JSON.parse(output);
            // Відправляємо дані у візуальну частину (PixiJS)
            win.webContents.send('asuna-brain-data', json);
        } catch (e) {
            console.log("Python Log:", output);
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`PYTHON ERROR: ${data}`);
    });

    // Слухаємо запит на активацію мікрофона від інтерфейсу
    ipcMain.on('start-listening', () => {
        if (pythonProcess) {
        console.log("Відправляю команду в Python: listen");
        // Пишемо JSON у потік stdin Python-процесу
        pythonProcess.stdin.write(JSON.stringify({ command: "listen" }) + "\n");
    }
});

    // ОБРОБКА РУХУ ВІКНА
    ipcMain.on('move-window', (event, pos) => {
        win.setPosition(pos.x, pos.y);
    });
    ipcMain.on('close-app', () => {
        app.quit();
    });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (pythonProcess) pythonProcess.stdin.write(JSON.stringify({ command: "close_session" }) + "\n");
    if (pythonProcess) pythonProcess.kill();
    if (process.platform !== 'darwin') app.quit();
});