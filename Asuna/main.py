import os
import sys
import asyncio
import datetime
import subprocess
from pathlib import Path
from dotenv import load_dotenv

import pygame
import edge_tts
import aiohttp
import speech_recognition as sr
from faster_whisper import WhisperModel
from google import genai
from google.genai import types

# Завантажуємо конфігурацію з середовища (.env)
load_dotenv()

# --- КОНФІГУРАЦІЙНИЙ СТИЛЬ ТА ПРOMПТИ (Для легкого редагування іншими користувачами) ---
SYSTEM_CORE_PROMPT = """
Ти — Асуна, живий, розумний та емпатичний ШІ-компаньйон. Твоя мета — підтримувати діалог природно, уникаючи канцелярщини.
Не використовуй у тексті емодзі чи текстові смайлики (це критично!). 
Будуй мовлення розмовно, коротко (1-3 речення).
Відповідай мовою користувача.

Нижче наведено довгострокові спогади про користувача, з яким ти спілкуєшся, його діяльність та інтереси:
{user_profile}

Контекст ваших останніх зустрічей (історія еволюції вашого спілкування):
{evolution_log}

Увага! Ти розмовляєш з {user_name}. Обов'язково використовуй ці знання у розмові, не став дурних запитань про те, що ти вже знаєш. 
Ти маєш доступ до інструментів для збереження та редагування файлів у робочій папці користувача, оновлення його профілю та твоїх правил поведінки. Якщо {user_name} просить щось запам'ятати чи створити нотатку — сміливо викликай потрібний інструмент.
"""

SUMMARY_ANALYSIS_PROMPT = """
Ти — аналітичний модуль пам'яті Асуни. Проаналізуй повсякденний діалог між користувачем {user_name} та Асуною.
Твоя задача — витягти важливі факти про його життя, плани, поточні справи та настрій для довгострокової пам'яті.

Напиши підсумок строго у такому форматі (використовуй Markdown):
### [{current_time}]
- **Про що говорили:** (Суть розмови, 1-2 речення)
- **Контекст, плани та настрій:** (Які справи планує зробити, який настрій)
- **Нові деталі для профілю:** (Факти про роботу, хобі, уподобання. Якщо нічого нового — пиши "без змін")

Ось текст діалогу для аналізу:
{chat_history}
"""


class AsunaCore:
    
    def __init__(self):
        pygame.mixer.init()
        
        # 1. ДИНАМІЧНІ ДАНІ КОРИСТУВАЧА З .env
        self.user_name = os.getenv("USER_NAME", "Користувач")
        self.voice = os.getenv("VOICE_NAME", "uk-UA-PolinaNeural")
        
        # 2. КРИШТАЛЕВО ЧИСТІ ВІДНОСНІ ШЛЯХИ (Працює на будь-якому ПК)
        # Визначаємо корінь проекту на основі розташування файлу main.py
        self.base_dir = Path(__file__).resolve().parent.parent
        
        self.memory_dir = self.base_dir / "asuna_memory"
        self.workspace_dir = self.memory_dir / "asuna_workspace"
        
        # Створюємо структури, якщо їх немає
        self.memory_dir.mkdir(exist_ok=True)
        self.workspace_dir.mkdir(exist_ok=True)
        
        # 3. ІНІЦІАЛІЗАЦІЯ ШІ МОДЕЛЕЙ
        print(f"⚙️ [Core]: Ініціалізація Асуни для користувача: {self.user_name}", file=sys.stderr, flush=True)
        self.whisper = WhisperModel("small", device="cpu", compute_type="int8")
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("❌ [Core Error]: GEMINI_API_KEY не знайдено у файлі .env!", file=sys.stderr, flush=True)
            
        self.client = genai.Client(api_key=gemini_key)
        self.model_id = "gemini-2.5-flash-lite"
        
        self.session_history = []
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300  
        self.recognizer.dynamic_energy_threshold = True

    def load_obsidian_context(self):
        """Зчитує динамічний контекст пам'яті відносних Markdown-файлів"""
        persona = ""
        profile = ""
        evolution = ""
        
        persona_path = self.memory_dir / "asuna_persona.md"
        if persona_path.exists():
            persona = persona_path.read_text(encoding="utf-8")
            
        # НЕЙТРАЛЬНА НАЗВА ПРОФІЛЮ ЗАМІСТЬ ХАРДКОДУ СAШІ
        profile_path = self.memory_dir / "user_profile.md"
        if profile_path.exists():
            profile = profile_path.read_text(encoding="utf-8")
            
        evolution_path = self.memory_dir / "evolution_log.md"
        if evolution_path.exists():
            full_evolution = evolution_path.read_text(encoding="utf-8")
            evolution = full_evolution[-2500:]

        # Форматуємо винесений наверх базовий промпт даних
        return f"{persona}\n" + SYSTEM_CORE_PROMPT.format(
            user_profile=profile,
            evolution_log=evolution,
            user_name=self.user_name
        )

    def listen(self):
        with sr.Microphone() as source:
            print("Асуна слухає...", file=sys.stderr, flush=True)
            try:
                audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=8)
                # Зберігаємо аудіо в корінь бекенду відносно main.py
                wav_path = Path(__file__).resolve().parent / "voice.wav"
                
                with open(wav_path, "wb") as f:
                    f.write(audio.get_wav_data())
                
                segments, _ = self.whisper.transcribe(str(wav_path), language="uk")
                text = "".join([s.text for s in segments]).strip()
                return text
            except sr.WaitTimeoutError:
                return ""
            except Exception as e:
                print(f"DEBUG Помилка розпізнавання: {e}", file=sys.stderr, flush=True) 
                return ""

    # --- ІНСТРУМЕНТИ КЕРУВАННЯ ФАЙЛАМИ ТА ДИНАМІЧНОЮ ПАМ'ЯТТЮ ---
    
    def create_workspace_file(self, filename: str, content: str) -> str:
        """Створює новий Markdown (.md) файл у робочій папці asuna_workspace."""
        try:
            pure_name = Path(filename).stem
            file_path = self.workspace_dir / f"{pure_name}.md"
            file_path.write_text(content, encoding="utf-8")
            print(f"📁 [Workspace]: Створено файл {pure_name}.md", file=sys.stderr, flush=True)
            return f"Успішно створено Markdown-файл {pure_name}.md у робочій папці."
        except Exception as e:
            return f"Помилка створення файлу: {str(e)}"

    def edit_workspace_file(self, filename: str, content: str, mode: str = "append") -> str:
        """Модифікує або дописує інформацію у існуючий Markdown-файл в asuna_workspace."""
        try:
            pure_name = Path(filename).stem
            file_path = self.workspace_dir / f"{pure_name}.md"
            
            if not file_path.exists():
                return f"Помилка: Файл {pure_name}.md не існує."
                
            if mode == "overwrite":
                file_path.write_text(content, encoding="utf-8")
            else:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{content}")
            print(f"📝 [Workspace]: Оновлено файл {pure_name}.md", file=sys.stderr, flush=True)
            return f"Файл {pure_name}.md успішно оновлено."
        except Exception as e:
            return f"Помилка редагування: {str(e)}"

    def update_user_profile(self, fact: str) -> str:
        """Додає новий довгостроковий факт про користувача у файл user_profile.md."""
        try:
            profile_path = self.memory_dir / "user_profile.md"
            if not profile_path.exists():
                profile_path.write_text(f"# Профіль користувача {self.user_name}\n## Уподобання:\n", encoding="utf-8")
            
            with open(profile_path, "a", encoding="utf-8") as f:
                f.write(f"\n- {fact} (автоматично: {datetime.datetime.now().strftime('%Y-%m-%d')})")
            print(f"🧠 [Memory]: Оновлено файл user_profile.md", file=sys.stderr, flush=True)
            return f"Я успішно внесла цей факт про тебе у свою довгострокову пам'ять."
        except Exception as e:
            return f"Не вдалося оновити профіль: {str(e)}"

    def update_asuna_behavior(self, rule: str) -> str:
        """Додає нове правило поведінки, характеру чи стилю Асуни у файл asuna_persona.md."""
        try:
            persona_path = self.memory_dir / "asuna_persona.md"
            if not persona_path.exists():
                persona_path.write_text("# Характер та стиль Асуни\n## Правила поведінки:\n", encoding="utf-8")
                
            with open(persona_path, "a", encoding="utf-8") as f:
                f.write(f"\n- {rule} (побажання від {datetime.datetime.now().strftime('%Y-%m-%d')})")
            print(f"⚙️ [Persona]: Оновлено правила asuna_persona.md", file=sys.stderr, flush=True)
            return "Я зафіксувала це правило у своїх внутрішніх установках і буду його дотримуватися."
        except Exception as e:
            return f"Не вдалося оновити характер: {str(e)}"

    # --- ЗАПИТ ТА ЛОКАЛЬНІ КОМАНДИ ---

    async def ask_asuna(self, prompt):
        if not prompt:
            return {"status": "ok", "text": f"Я не почула тебе, {self.user_name}."}
            
        cmd_result = self.run_command(prompt.lower())
        if cmd_result:
            if isinstance(cmd_result, dict) and cmd_result.get("action") == "goodbye":
                asuna_reply = cmd_result["text"]
                self.session_history.append(f"Асуна: {asuna_reply}")
                await self.save_session_summary()
                return {"status": "shutdown", "text": asuna_reply}
            elif isinstance(cmd_result, str):
                self.session_history.append(f"Асуна: {cmd_result}")
                return {"status": "ok", "text": cmd_result}

        try:
            system_prompt = self.load_obsidian_context()
            self.session_history.append(f"{self.user_name}: {prompt}")
            history_context = "\n".join(self.session_history[-6:])
            
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[
                    self.create_workspace_file,
                    self.edit_workspace_file,
                    self.update_user_profile,    
                    self.update_asuna_behavior   
                ],
                temperature=0.7
            )
            
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=f"Історія поточної розмови:\n{history_context}\n\nОстання репліка: {prompt}",
                config=config
            )
            
            # Function Calling
            if response.function_calls:
                for call in response.function_calls:
                    func_name = call.name
                    func_args = call.args
                    
                    if func_name == "create_workspace_file":
                        result_msg = self.create_workspace_file(**func_args)
                    elif func_name == "edit_workspace_file":
                        result_msg = self.edit_workspace_file(**func_args)
                    elif func_name == "update_user_profile":
                        result_msg = self.update_user_profile(**func_args)
                    elif func_name == "update_asuna_behavior":
                        result_msg = self.update_asuna_behavior(**func_args)
                    else:
                        result_msg = "Невідома функція"
                        
                    follow_up = self.client.models.generate_content(
                        model=self.model_id,
                        contents=[
                            types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                            response.candidates[0].content,
                            types.Content(role="tool", parts=[types.Part.from_function_response(
                                name=func_name,
                                response={"result": result_msg}
                            )])
                        ],
                        config=config
                    )
                    asuna_reply = follow_up.text
                    self.session_history.append(f"Асуна: {asuna_reply}")
                    return {"status": "ok", "text": asuna_reply}
            
            asuna_reply = response.text
            self.session_history.append(f"Асуна: {asuna_reply}")
            return {"status": "ok", "text": asuna_reply}
            
        except Exception as e:
            print(f"!!! КРИТИЧНА ПОМИЛКА GEMINI: {e}", file=sys.stderr, flush=True)
            return {"status": "ok", "text": "Вибачте, виникла помилка доступу до хмари штучного інтелекту."}
        
    async def save_session_summary(self):
        if len(self.session_history) < 2:
            return
        try:
            await asyncio.sleep(0.5)
            chat_str = "\n".join(self.session_history)
            
            # Форматуємо винесений наверх аналітичний промпт
            analysis_prompt = SUMMARY_ANALYSIS_PROMPT.format(
                user_name=self.user_name,
                current_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                chat_history=chat_str
            )
            
            loop = asyncio.get_running_loop()
            summary_response = await loop.run_in_executor(
                None, 
                lambda: self.client.models.generate_content(model=self.model_id, contents=analysis_prompt)
            )
            
            summary_text = summary_response.text.strip()
            evolution_path = self.memory_dir / "evolution_log.md"
            with open(evolution_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n{summary_text}")
            print("🧠 [LOG]: Повсякденні спогади Асуни успішно збережено в Obsidian.", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"DEBUG Помилка фонового збереження спогадів: {e}", file=sys.stderr, flush=True)

    def run_command(self, command):
        if any(word in command for word in ["завершити роботу", "вимкнись", "бувай", "папа"]):
            return {
                "action": "goodbye",
                "text": f"Бувай! Я зберігаю наші спогади в Обсідіан та відпочиватиму. До зустрічі, {self.user_name}!"
            }
        elif "котра година" in command or "який зараз час" in command:
            now = datetime.datetime.now()
            return f"Зараз {now.hour}:{now.minute:02d}."
        elif "яке сьогодні число" in command or "яка дата" in command:
            now = datetime.datetime.now()
            months = ["січня", "лютого", "березня", "квітня", "травня", "червня", 
                      "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
            return f"Сьогодні {now.day} {months[now.month - 1]} {now.year} року."
        elif "щоденник" in command or "спогади" in command:
            log_path = self.memory_dir / "evolution_log.md"
            if log_path.exists():
                os.system(f'start "" "{log_path}"')
                return "Відкриваю твій щоденник еволюції."
            return "Я ще не встигла створити файл щоденника."
        elif command == "повтори" or "що ти сказала" in command:
            for msg in reversed(self.session_history):
                if msg.startswith("Асуна: "):
                    return msg.replace("Асуна: ", "Повторюю: ")
            return "Я ще нічого не казала."
        elif "браузер" in command or "хром" in command:
            subprocess.Popen(['start', 'chrome'], shell=True)
            return "Відкриваю веб-браузер."
        elif "телеграм" in command:
            subprocess.Popen(['start', 'telegram'], shell=True)
            return "Месенджер запущено."
        elif "блокнот" in command:
            subprocess.Popen(['notepad.exe'])
            return "Блокнот готовий."
        return None
    
    async def talk(self, text):
        output_file = Path(__file__).resolve().parent / "response.mp3"
        clean_text = text.replace("**", "").replace("*", "").replace("###", "").strip()
        
        # Автоматична очистка текстових озвучень емодзі
        emoji_phrases = [
            "усміхнене лице", "усміхнене обличчя", "лице з посмішкою", 
            "підмигуюче лице", "підмигування", "робот", "смайлик",
            "обличчя, що посміхається", "лице, що посміхається"
        ]
        for phrase in emoji_phrases:
            clean_text = clean_text.replace(phrase, "").replace(phrase.capitalize(), "")
            
        clean_text = " ".join(clean_text.split()).strip()
        
        if not clean_text:
            return
        try:
            communicate = edge_tts.Communicate(
                text=clean_text, 
                voice=self.voice,
                rate="+15%",
                pitch="+4Hz"
            )
            await communicate.save(str(output_file))

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            try:
                pygame.mixer.music.unload()
            except:
                pass

            pygame.mixer.music.load(str(output_file))
            pygame.mixer.music.play()
            
            await asyncio.sleep(0.2)
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
            
            pygame.mixer.music.unload()
            if output_file.exists():
                os.remove(output_file)
        except Exception as e:
            print(f"!!! Помилка озвучки Edge-TTS: {e}", file=sys.stderr, flush=True)