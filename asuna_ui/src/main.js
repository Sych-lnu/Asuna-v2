import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';

let app;
let model;

// Точні індекси рухів та емоцій з конфігу твоєї моделі Асуни SAO v2
const ASUNA_MOTIONS = {
    START_LISTEN: 7,  // I_SNEESE
    SPEAK_START: 11,  // REPEAT_01
    SPEAK_LOOP: 12,   // REPEAT_02
    SPEAK_END: 13,    // REPEAT_03
    FUN_READY: 1      // I_FUN
};

const ASUNA_EXPRESSIONS = {
    NORMAL: 'F_NOMAL',
    FUN: 'F_FUN_SMILE',
    SURPRISE: 'F_SURPRISE',
    SLEEP: 'F_SLEEP'
};

// 1. Функція завантаження та первинного налаштування моделі
// asuna_ui/src/main.js

// asuna_ui/src/main.js

// asuna_ui/src/main.js

// asuna_ui/src/main.js

async function loadAsunaModel() {
    try {
        console.log("Завантаження моделі Асуни з фіксом сумісності Pixi v7...");

        // ================= ТУТ НАЙВАЖЛИВІШИЙ ХАК ДЛЯ PIXI V7 =================
        // Плагін шукає PIXI.Ticker.shared або PIXI.Ticker.system і намагається викликати .remove().
        // Оскільки в Pixi v7 структура змінилася, ми вручну створюємо об'єкт-заглушку,
        // щоб плагін міг успішно викликати метод remove() і НЕ КРАШИВ ПРОГРАМУ!
        if (!PIXI.Ticker) PIXI.Ticker = {};
        if (!PIXI.Ticker.shared) {
            PIXI.Ticker.shared = {
                add: () => {},
                remove: () => {} // Ось цей рядок захищає від помилки (reading 'remove')!
            };
        }
        // ====================================================================

        // Тепер стандартний метод завантаження пройде БЕЗ ЖОДНИХ ПОМИЛОК
        model = await Live2DModel.from("/model/asuna_04.model.json");
        
        // Повністю вимикаємо внутрішній автоапдейт плагіна, ми керуємо ним самі
        model.autoUpdate = false; 

        // ХАКИ СУМІСНОСТІ ДЛЯ КЛІКІВ У PIXI V7+
        model.registerInteraction = () => {};
        model.isInteractive = () => true;
        model.eventMode = 'static';
        model.interactive = true;
        model.buttonMode = true; 

        // Налаштування масштабування та позиціонування
        model.anchor.set(0.5, 0);
        model.scale.set(0.25); // За потреби підкрути цей коефіцієнт
        model.x = app.screen.width / 2;
        model.y = 0;
        
        // СИНХРОНІЗАЦІЯ КАДРІВ ДЛЯ V2 + PIXI V7
        // Оновлюємо Live2D строго перед розрахунком матриці трансформації Pixi
        const originalUpdateTransform = model.updateTransform;
                model.updateTransform = function() {
                    if (typeof this.update === 'function') {
                        // Отримуємо поточний дельта-час від головного тикера PixiJS v7
                        const deltaTime = PIXI.Ticker.shared.elapsedMS || 0.8; 
                        const speedModifier = 0.4; 
                        const finalDelta = deltaTime * speedModifier;
                        // Передаємо цей час в модель, щоб запустити внутрішній годинник Live2D v2
                        this.update(deltaTime); 
                    }
                    originalUpdateTransform.call(this);
                };

        // Додаємо Асуну на сцену Pixi
        app.stage.addChild(model);
        
        // Обробка кліку
        /*model.on('pointerdown', (e) => {
            e.stopPropagation(); 
            console.log("Клік по Асуні! Починаємо слухати...");
            const statusDiv = document.getElementById('status-indicator');
            if (statusDiv) {
                statusDiv.innerText = "🎤 Слухаю тебе...";
                statusDiv.style.color = "#ffaa00";
            }
            window.electronAPI.startListening();
        });*/

        console.log("🎉 Перемога! Обхідний щит спрацював, Асуна завантажена на сцену.");
        return true; 
    } catch (error) {
        console.error("Критична помилка завантаження самої моделі:", error);
        return false;
    }
}

// 2. Функція LipSync (Анімація ротика для версії v2)
function startLipSync() {
    const duration = 4000; 
    const start = Date.now();
    
    const interval = setInterval(() => {
        const elapsed = Date.now() - start;
        if (elapsed > duration) {
            // Закриваємо рот в кінці обома методами для надійності
            if (model?.internalModel?.coreModel?.setParameterValueById) {
                model.internalModel.coreModel.setParameterValueById('PARAM_MOUTH_OPEN_Y', 0);
            }
            if (model?.setParamFloat) {
                model.setParamFloat('PARAM_MOUTH_OPEN_Y', 0);
            }
            clearInterval(interval);
            return;
        }
        
        const mouthValue = Math.abs(Math.sin(Date.now() / 80)) * 0.8;
        
        // Рухаємо параметром PARAM_MOUTH_OPEN_Y (великі літери для v2)
        if (model?.internalModel?.coreModel?.setParameterValueById) {
            model.internalModel.coreModel.setParameterValueById('PARAM_MOUTH_OPEN_Y', mouthValue);
        }
        if (model?.setParamFloat) {
            model.setParamFloat('PARAM_MOUTH_OPEN_Y', mouthValue);
        }
    }, 40);
}

// 3. Головна функція запуску програми
async function startApp() {
    try {
        // Створюємо додаток PixiJS
        app = new PIXI.Application({
    width: window.innerWidth,
    height: window.innerHeight,
    backgroundAlpha: 0, // ЦЕЙ РЯДОК замінює transparent: true у Pixi v7!
    autoStart: true
});
        
        document.body.appendChild(app.view);
        
        // Чекаємо повного завантаження моделі
        const isLoaded = await loadAsunaModel();
        if (!isLoaded) {
            console.error("Запуск зупинено через помилку моделі.");
            return;
        }
        
        const statusDiv = document.getElementById('status-indicator');
        if (statusDiv) {
            statusDiv.innerText = "Очікування підключення мозку...";
        }

        // НАЛАШТУВАННЯ ПЕРЕТЯГУВАННЯ ВІКНА МИШКОЮ
        let isMouseDown = false;
        let isDragging = false; // Прапорець, який показує, що ми саме тягнемо вікно
        let startX, startY;
        let initialMouseX, initialMouseY;

        window.addEventListener('mousedown', (e) => {
            isMouseDown = true;
            isDragging = false; // На початку натискання це ще не перетягування
            
            // Координати для перетягування Electron-вікна
            startX = e.clientX;
            startY = e.clientY;
            
            // Координати для перевірки зміщення миші
            initialMouseX = e.screenX;
            initialMouseY = e.screenY;
        });

        window.addEventListener('mousemove', (e) => {
            if (isMouseDown) {
                // Рахуємо, на скільки пікселів змістилася мишка від точки натискання
                const moveX = Math.abs(e.screenX - initialMouseX);
                const moveY = Math.abs(e.screenY - initialMouseY);
                
                // Якщо мишка змістилася більше ніж на 4 пікселі — вмикаємо режим перетягування
                if (moveX > 4 || moveY > 4) {
                    isDragging = true;
                }

                // Якщо ми в режимі перетягування — рухаємо вікно Electron
                if (isDragging) {
                    const x = e.screenX - startX;
                    const y = e.screenY - startY;
                    window.electronAPI.moveWindow({ x, y });
                }
            }
        });

        window.addEventListener('mouseup', (e) => {
            isMouseDown = false;

            // НАЙВАЖЛИВІШЕ: Якщо мишка відпущена і прапорець isDragging залишився false — 
            // це означає, що користувач просто клікнув по віджету, не рухаючи його!
            if (!isDragging) {
                // Перевіряємо, чи клік відбувся саме по Асуні (або по нижній частині віджета, де вона стоїть)
                // Виключаємо кліки по кнопці закриття (якщо координати вище кнопки)
                if (e.clientY > 40) { 
                    console.log("Чистий клік без перетягування! Починаємо слухати...");
                    
                    const statusDiv = document.getElementById('status-indicator');
                    if (statusDiv) {
                        statusDiv.innerText = "🎤 Активація мікрофона...";
                        statusDiv.style.color = "#ffaa00";
                    }
                    window.electronAPI.startListening();
                }
            }
            
            isDragging = false; // Скидаємо прапорець
        });

        // КНОПКА ЗАКРИТТЯ ВІДЖЕТА
        const closeBtn = document.getElementById('close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation(); 
                window.electronAPI.closeWindow();
            });
        }

        // ОБРОБКА ДАНИХ ВІД PYTHON ЧЕРЕЗ МІСТОК
        window.electronAPI.onBrainData((data) => {
            if (!statusDiv) return;

            // Стан: Місток готовий (Brain Ready)
            if (data.type === 'status' && data.text === 'Brain Ready') {
                statusDiv.innerText = "Асуна готова до роботи";
                statusDiv.style.color = "#55ff55"; 
                if (model.expression) model.expression(ASUNA_EXPRESSIONS.NORMAL);
                if (model.motion) model.motion("idle", 0, 3); 
            }

            // Стан: Користувач клікнув, запис пішов
            if (data.type === 'debug' && data.text === 'Starting listen...') {
                statusDiv.innerText = "🎤 Слухаю тебе...";
                statusDiv.style.color = "#ffaa00"; 
                if (model.expression) model.expression(ASUNA_EXPRESSIONS.SURPRISE);
                if (model.motion) model.motion("", ASUNA_MOTIONS.START_LISTEN, 3); 
            }

            // Стан: Whisper розпізнав текст
            if (data.type === 'transcription') {
                statusDiv.innerText = `💬 Саша: "${data.text}"`;
                statusDiv.style.color = "#ffffff";
            }
            
            // Стан: Асуна відповідає голосом
            if (data.type === 'response') {
                statusDiv.innerText = "🗣️ Відповідаю...";
                statusDiv.style.color = "#55aaff"; 
                
                if (model.expression) model.expression(ASUNA_EXPRESSIONS.FUN);
                if (model.motion) model.motion("", ASUNA_MOTIONS.SPEAK_START, 3);
                
                // Перемикаємо на циклічний жест через секунду
                setTimeout(() => {
                    if (model.motion) model.motion("", ASUNA_MOTIONS.SPEAK_LOOP, 3);
                }, 1000);
                
                // Запуск ворушіння губами
                startLipSync();
                
                // Повернення в стан спокою
                setTimeout(() => {
                    statusDiv.innerText = "Асуна готова";
                    statusDiv.style.color = "#55ff55";
                    
                    if (model.motion) model.motion("", ASUNA_MOTIONS.SPEAK_END, 3);
                    if (model.expression) model.expression(ASUNA_EXPRESSIONS.NORMAL);
                    
                    setTimeout(() => {
                        if (model.motion) model.motion("idle", 0, 2);
                    }, 2000);
                    
                }, 4000);
            }
            
            // Стан: Помилка системи
            if (data.type === 'error') {
                statusDiv.innerText = "❌ Помилка містка";
                statusDiv.style.color = "#ff5555";
            }
        });

    } catch (e) {
        console.error("Помилка всередині startApp:", e);
    }
}

// Запускаємо додаток
startApp();