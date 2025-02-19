import json
import logging
import asyncio
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv
import os
import re

# Загрузка переменных из .env
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_PHONE = os.getenv("USER_PHONE")

# Файл для хранения данных
DATA_FILE = "bot_data.json"
monitoring_task = None  # Переменная для управления мониторингом

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Клиенты: бот и пользователь
bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
user = TelegramClient("user", API_ID, API_HASH)

# Функция загрузки данных
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"keywords": [], "groups": [], "processed_messages": {}, "recipients": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Функция сохранения данных
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Главное меню
def main_menu():
    return [
        [Button.inline("➕ Добавить ключевое слово", b"add_keyword")],
        [Button.inline("➕ Добавить группу", b"add_group")],
        [Button.inline("➕ Добавить получателя", b"add_recipient")],
        [Button.inline("📜 Показать ключевые слова", b"show_keywords")],
        [Button.inline("📜 Показать группы", b"show_groups")],
        [Button.inline("📜 Показать получателей", b"show_recipients")],
        [Button.inline("▶️ Начать мониторинг", b"start_monitoring")],
        [Button.inline("🛑 Остановить мониторинг", b"stop_monitoring")]
    ]

# Обработчик /start
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.respond("👋 Привет! Управляй ботом через кнопки ниже:", buttons=main_menu())

# Добавление ключевого слова
@bot.on(events.CallbackQuery(data=b"add_keyword"))
async def add_keyword(event):
    async with bot.conversation(event.sender_id) as conv:
        await conv.send_message("✍️ Введи ключевое слово:")
        response = await conv.get_response()

        data = load_data()
        data["keywords"].append(response.text.lower())
        save_data(data)

        await conv.send_message(f"✅ Добавлено ключевое слово: {response.text}", buttons=main_menu())

# Добавление группы
@bot.on(events.CallbackQuery(data=b"add_group"))
async def add_group(event):
    async with bot.conversation(event.sender_id) as conv:
        await conv.send_message("✍️ Введи ссылку на группу (пример: https://t.me/example_group):")
        response = await conv.get_response()

        match = re.search(r"https?://t\.me/(\w+)", response.text)
        if not match:
            await conv.send_message("🚫 Ошибка! Введи корректную ссылку.", buttons=main_menu())
            return

        group_link = response.text.strip()
        data = load_data()
        data["groups"].append({"link": group_link})
        save_data(data)
        await conv.send_message(f"✅ Группа добавлена: {group_link}", buttons=main_menu())

# Добавление получателя сообщений
@bot.on(events.CallbackQuery(data=b"add_recipient"))
async def add_recipient(event):
    user_id = event.sender_id  # Получаем ID пользователя
    data = load_data()
    
    # ✅ Если ключа "recipients" нет — создаем его
    if "recipients" not in data:
        data["recipients"] = []
    
    if user_id not in data["recipients"]:
        data["recipients"].append(user_id)
        save_data(data)
        await event.respond("✅ Ты добавлен в список получателей!", buttons=main_menu())
    else:
        await event.respond("⚠️ Ты уже в списке получателей!", buttons=main_menu())


# Показ ключевых слов
@bot.on(events.CallbackQuery(data=b"show_keywords"))
async def show_keywords(event):
    data = load_data()
    keywords = "\n".join(data["keywords"]) if data["keywords"] else "❌ Ключевые слова не заданы."
    await event.respond(f"📜 Ключевые слова:\n{keywords}", buttons=main_menu())

# Показ групп
@bot.on(events.CallbackQuery(data=b"show_groups"))
async def show_groups(event):
    data = load_data()
    groups = "\n".join([g["link"] for g in data["groups"]]) if data["groups"] else "❌ Группы не заданы."
    await event.respond(f"📜 Мониторинг групп:\n{groups}", buttons=main_menu())

# Показ получателей
@bot.on(events.CallbackQuery(data=b"show_recipients"))
async def show_recipients(event):
    data = load_data()
    recipients = "\n".join(map(str, data["recipients"])) if data["recipients"] else "❌ Получатели не заданы."
    await event.respond(f"📜 Получатели сообщений:\n{recipients}", buttons=main_menu())

# Запуск мониторинга
@bot.on(events.CallbackQuery(data=b"start_monitoring"))
async def start_monitoring(event):
    global monitoring_task
    if monitoring_task and not monitoring_task.done():
        await event.respond("🚀 Мониторинг уже запущен!", buttons=main_menu())
        return

    await event.respond("🚀 Мониторинг запущен! Бот будет отслеживать ключевые слова.")
    monitoring_task = asyncio.create_task(monitor_chats())

# Остановка мониторинга
@bot.on(events.CallbackQuery(data=b"stop_monitoring"))
async def stop_monitoring(event):
    global monitoring_task
    if monitoring_task:
        monitoring_task.cancel()
        monitoring_task = None
        await event.respond("⏹ Мониторинг остановлен.", buttons=main_menu())
    else:
        await event.respond("🚫 Мониторинг не запущен.", buttons=main_menu())

# Мониторинг сообщений
async def monitor_chats():
    data = load_data()
    group_links = [g["link"] for g in data["groups"]]
    keywords = data["keywords"]
    recipients = data.get("recipients", [])  # Получаем список получателей

    logging.info(f"🔍 Ключевые слова: {keywords}")

    async with user:
        while True:
            for group_link in group_links:
                try:
                    chat = await user.get_entity(group_link)
                    messages = await user.get_messages(chat, limit=10)

                    logging.info(f"🔍 Проверяю группу: {group_link}")

                    for message in messages:
                        if not message.text:
                            continue

                        message_text = message.text.lower()
                        sender_id = message.sender_id  # 🆔 ID автора сообщения

                        # Генерация ссылки на автора (если ID публичный)
                        sender_link = f"https://t.me/{sender_id}" if sender_id else "Неизвестный пользователь"

                        for keyword in keywords:
                            if keyword in message_text:
                                logging.info(f"🎯 Найдено ключевое слово '{keyword}' в {group_link}!")

                                msg = (
                                    f"🔍 **Найдено ключевое слово!**\n"
                                    f"📢 **Группа:** {group_link}\n"
                                    f"💬 **Сообщение:**\n{message.text}\n"
                                    f"👤 **Автор:** [{sender_id}]({sender_link})"
                                )

                                # Отправка сообщения всем получателям
                                for recipient in recipients:
                                    try:
                                        await bot.send_message(recipient, msg, link_preview=False)
                                        logging.info(f"✅ Сообщение отправлено {recipient}!")
                                    except Exception as e:
                                        logging.error(f"⚠️ Ошибка отправки {recipient}: {e}")

                    await asyncio.sleep(10)  # Пауза между группами

                except Exception as e:
                    logging.warning(f"⚠️ Ошибка при мониторинге {group_link}: {e}")

            await asyncio.sleep(10)  # Проверка каждые 10 секунд


# Запуск бота
async def main():
    await bot.start()
    await user.start(phone=USER_PHONE)
    print("✅ Бот запущен!")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())