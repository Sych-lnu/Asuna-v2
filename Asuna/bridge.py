# Asuna/bridge.py
import sys
import io
import json
import asyncio
from main import AsunaCore


# Примусово налаштовуємо стандартний вивід та помилки на UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

async def main():
    try:
        asuna = AsunaCore()
        
        print(json.dumps({"type": "status", "text": "Brain Ready"}), flush=True)
    except Exception as e:
        print(json.dumps({"type": "error", "message": str(e)}), flush=True)
        return

    while True:
        line = sys.stdin.readline()
        if not line:
            break
            
        # ДЕБАГ: Підтверджуємо отримання команди
        print(json.dumps({"type": "debug", "text": f"Received command: {line.strip()}"}), flush=True)
        
        try:
            data = json.loads(line)
            if data.get("command") == "listen":
                # Це повідомлення має з'явитися в консолі Electron
                print(json.dumps({"type": "debug", "text": "Starting listen..."}), flush=True)
                
                text = asuna.listen()
                print(json.dumps({"type": "transcription", "text": text}), flush=True)
                
                if text:
                    response = await asuna.ask_asuna(text)
                    reply_text = response["text"] # Отримуємо текст
                    print(json.dumps({"type": "response", "text": reply_text}), flush=True)
                    await asuna.talk(reply_text) # Озвучуємо
                    if response.get("status") == "shutdown":
                        print(json.dumps({"type": "status", "text": "Shutdown Complete"}), flush=True)
                        break # Вилітаємо з циклу очікування
        except Exception as e:
            print(json.dumps({"type": "error", "message": str(e)}), flush=True)
    print(json.dumps({"type": "status", "text": "Closing Python process..."}), flush=True)
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())