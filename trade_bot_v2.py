# === ПОЛНЫЙ РАБОЧИЙ МУЛЬТИЯЗЫЧНЫЙ БОТ ===

import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_NAME = "users.db"

# ================= DB =================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        language TEXT DEFAULT 'ru'
    )
    """)

    conn.commit()
    conn.close()

# ================= LANG =================

LANG = {
    "ru": {
        "start": "Привет 👋 Выбери язык:",
        "menu": ["📋 Список", "📊 Анализ", "🌐 Язык"],
    },
    "en": {
        "start": "Hello 👋 Choose language:",
        "menu": ["📋 List", "📊 Analyze", "🌐 Language"],
    },
    "kk": {
        "start": "Сәлем 👋 Тілді таңда:",
        "menu": ["📋 Тізім", "📊 Талдау", "🌐 Тіл"],
    },
    "cs": {
        "start": "Ahoj 👋 Vyber jazyk:",
        "menu": ["📋 Seznam", "📊 Analýza", "🌐 Jazyk"],
    }
}

def get_lang(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "ru"

def set_lang(user_id, lang):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO users (user_id, language)
    VALUES (?, ?)
    ON CONFLICT(user_id) DO UPDATE SET language=excluded.language
    """, (user_id, lang))
    conn.commit()
    conn.close()

# ================= KEYBOARDS =================

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang_kk")],
        [InlineKeyboardButton(text="🇨🇿 Čeština", callback_data="lang_cs")],
    ])

def main_menu(user_id):
    lang = get_lang(user_id)
    menu = LANG[lang]["menu"]

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=menu[0])],
            [KeyboardButton(text=menu[1])],
            [KeyboardButton(text=menu[2])]
        ],
        resize_keyboard=True
    )

# ================= HANDLERS =================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Choose language / Выберите язык",
        reply_markup=lang_keyboard()
    )

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    set_lang(callback.from_user.id, lang)

    await callback.message.answer(
        "✅ OK",
        reply_markup=main_menu(callback.from_user.id)
    )

@dp.message(F.text.in_(["🌐 Язык", "🌐 Language", "🌐 Тіл", "🌐 Jazyk"]))
async def change_lang(message: types.Message):
    await message.answer("🌐", reply_markup=lang_keyboard())

@dp.message()
async def echo(message: types.Message):
    lang = get_lang(message.from_user.id)

    if lang == "ru":
        await message.answer("Ты написал: " + message.text)
    elif lang == "en":
        await message.answer("You wrote: " + message.text)
    elif lang == "kk":
        await message.answer("Сен жаздың: " + message.text)
    elif lang == "cs":
        await message.answer("Napsal jsi: " + message.text)

# ================= MAIN =================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())