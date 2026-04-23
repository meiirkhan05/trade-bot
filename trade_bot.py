import asyncio
import html
import os
import random
import sqlite3
from typing import Optional

import aiohttp
import yfinance as yf
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if not TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_NAME = "portfolio.db"
GEMINI_MODEL = "gemini-2.5-flash-lite"

STOCKS = [
    {"id": "HSBK", "name": "Halyk Bank", "kase_ticker": "HSBK", "yahoo_tickers": ["HSBK.IL"]},
    {"id": "KZAP", "name": "Kazatomprom", "kase_ticker": "KZAP", "yahoo_tickers": ["KAP.IL"]},
    {"id": "KSPI", "name": "Kaspi.kz", "kase_ticker": "KSPI", "yahoo_tickers": ["KSPI"]},
    {"id": "KCEL", "name": "Kcell", "kase_ticker": "KCEL", "yahoo_tickers": ["KCEL.L"]},
    {"id": "KZTK", "name": "Kazakhtelecom", "kase_ticker": "KZTK", "yahoo_tickers": ["KZHXY", "KZTA.F"]},
    {"id": "KZTO", "name": "KazTransOil", "kase_ticker": "KZTO", "yahoo_tickers": []},
    {"id": "KEGC", "name": "KEGOC", "kase_ticker": "KEGC", "yahoo_tickers": []},
    {"id": "CCBN", "name": "Bank CenterCredit", "kase_ticker": "CCBN", "yahoo_tickers": []},
]
STOCKS_BY_ID = {item["id"]: item for item in STOCKS}

STATIC_COMPANY_INFO = {
    "HSBK": {
        "sector": "Financial Services",
        "industry": "Banking",
        "country": "Kazakhstan",
        "business_summary": "Halyk Bank is one of the largest banks in Kazakhstan. Its business includes retail banking, corporate banking, deposits, loans, payments, and related financial services.",
        "long_term_note": "For long-term investors, banks are usually judged by profit stability, credit quality, capital strength, and dividend policy.",
        "dividend_note": "Bank stocks can be attractive for dividend investors, but payouts depend on balance sheet quality and regulation.",
    },
    "KZAP": {
        "sector": "Energy",
        "industry": "Uranium",
        "country": "Kazakhstan",
        "business_summary": "Kazatomprom is a large uranium producer. Its results depend heavily on uranium prices, global supply-demand balance, and the outlook for nuclear energy.",
        "long_term_note": "For long-term investors, this stock is connected to the uranium cycle and the long-term role of nuclear power.",
        "dividend_note": "Commodity companies can pay strong dividends in good cycles, but payouts may vary with market prices.",
    },
    "KSPI": {
        "sector": "Technology / Financial Services",
        "industry": "Fintech, Payments, Marketplace",
        "country": "Kazakhstan",
        "business_summary": "Kaspi.kz combines payments, digital banking, and e-commerce services in one ecosystem. Its strength comes from customer activity, transaction growth, and ecosystem convenience.",
        "long_term_note": "For long-term investors, important factors include sustainable growth, profitability, competitive advantages, and ecosystem expansion.",
        "dividend_note": "Fast-growing fintech companies may also pay dividends, but growth quality is usually the main long-term driver.",
    },
    "KCEL": {
        "sector": "Communication Services",
        "industry": "Telecom",
        "country": "Kazakhstan",
        "business_summary": "Kcell is a telecommunications company. It earns mainly from mobile services, internet access, data traffic, and business telecom solutions.",
        "long_term_note": "For long-term investors, telecom companies are often judged by subscriber base, cash flow, investment discipline, and pricing power.",
        "dividend_note": "Telecom names can be interesting for income-focused investors because mature telecom businesses may generate recurring cash flow.",
    },
    "KZTK": {
        "sector": "Communication Services",
        "industry": "Telecom",
        "country": "Kazakhstan",
        "business_summary": "Kazakhtelecom is a major telecom operator in Kazakhstan. Its business includes communication infrastructure, broadband services, and telecom-related operations.",
        "long_term_note": "Long-term investors usually focus on stable cash flow, market position, infrastructure quality, and capital allocation.",
        "dividend_note": "Telecom businesses often attract investors looking for relatively stable business models and possible dividends.",
    },
    "KZTO": {
        "sector": "Energy",
        "industry": "Oil Transportation",
        "country": "Kazakhstan",
        "business_summary": "KazTransOil operates oil transportation infrastructure. Its results are linked to transport volumes, tariffs, regulation, and the condition of the energy sector.",
        "long_term_note": "For long-term investors, infrastructure-style companies are often judged by asset stability, regulation, and resilience of cash flow.",
        "dividend_note": "Infrastructure and transport names may interest dividend investors if operating cash flows remain stable.",
    },
    "KEGC": {
        "sector": "Utilities",
        "industry": "Electric Grid / Transmission",
        "country": "Kazakhstan",
        "business_summary": "KEGOC operates in electricity transmission and grid infrastructure. Its business depends on power demand, tariffs, regulation, and investment in energy networks.",
        "long_term_note": "Utility and grid companies are often considered for long-term investing because of their essential infrastructure role.",
        "dividend_note": "Utility-style companies can be attractive to investors who value more predictable business models and income potential.",
    },
    "CCBN": {
        "sector": "Financial Services",
        "industry": "Banking",
        "country": "Kazakhstan",
        "business_summary": "Bank CenterCredit is a banking institution. Its business depends on lending, deposits, payment services, credit quality, and macroeconomic conditions.",
        "long_term_note": "For long-term investors, key questions include stability of profitability, loan quality, funding, and capital adequacy.",
        "dividend_note": "Bank stocks can offer dividends, but investors should study earnings quality and balance sheet strength.",
    },
}

LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "kk": "🇰🇿 Қазақша",
    "cs": "🇨🇿 Čeština",
}

LANGUAGE_NAMES = {
    "ru": "Russian",
    "en": "English",
    "kk": "Kazakh",
    "cs": "Czech",
}

TEXTS = {
    "ru": {
        "start": "Привет, {name} 👋\n\nЯ бот для анализа и слежения за акциями.",
        "menu": "/list — список акций\n/portfolio — портфель\n/analyze — анализ",
        "choose_language": "Выберите язык / Choose language / Тілді таңдаңыз / Vyberte jazyk",
        "language_saved": "Язык сохранен: {language}",
        "menu_list": "📋 Список акций",
        "menu_portfolio": "💼 Мой портфель",
        "menu_analyze": "📊 Анализировать",
        "menu_watch_on": "📡 Включить слежение",
        "menu_watch_off": "⛔ Выключить слежение",
        "menu_help": "ℹ️ Помощь",
        "menu_language": "🌐 Сменить язык",
        "help_title": "{name}, что умеет бот:",
        "help_text": "/list — открыть список акций\n/portfolio — показать сохраненные акции\n/analyze — выбрать акцию для анализа\n/watch — включить авто-слежение за портфелем\n/unwatch — выключить авто-слежение\n\nКак пользоваться:\n1. Открой список акций\n2. Выбери бумагу\n3. Добавь в портфель\n4. Изучи анализ\n5. Включи слежение",
        "list_title": "{name}, список акций",
        "choose_stock": "Выбери бумагу:",
        "press_stock": "Нажми на нужную акцию:",
        "portfolio_empty": "💼 {name}, твой портфель пока пуст. Добавь акции через список.",
        "portfolio_title": "💼 Портфель {name}:",
        "portfolio_pick": "Выбери бумагу из портфеля:",
        "analyze_pick": "📊 {name}, выбери бумагу для анализа:",
        "watch_on": "📡 {name}, слежение за портфелем включено.",
        "watch_off": "⛔ {name}, слежение за портфелем выключено.",
        "stock_not_found": "Акция не найдена",
        "back_to_list": "🔙 Назад к списку",
        "add_portfolio": "➕ Добавить в портфель",
        "remove_portfolio": "➖ Удалить из портфеля",
        "short_analysis": "⚡ Короткий анализ",
        "full_analysis": "📘 Подробный анализ",
        "analysis_available": "доступен",
        "analysis_unavailable": "инфо без котировок",
        "yes": "да",
        "no": "нет",
        "on": "включено",
        "off": "выключено",
        "choose_action": "Выбери действие ниже.",
        "quote_error": "❌ По <b>{name}</b> сейчас не удалось получить котировки из Yahoo Finance. Показываю информационный анализ без рыночных цен.",
        "short_analysis_progress": "⚡ {name}, делаю короткий анализ по <b>{stock}</b>...",
        "full_analysis_progress": "📘 {name}, делаю подробный анализ по <b>{stock}</b>...",
        "doing_short": "Делаю короткий анализ...",
        "doing_full": "Делаю подробный анализ...",
        "added": "Добавил в портфель",
        "removed": "Удалил из портфеля",
        "already_added": "Акция уже в портфеле",
        "remove_failed": "Не удалось удалить",
        "stock_card_kase": "KASE",
        "stock_card_yahoo": "Источники котировок",
        "stock_card_analysis": "Анализ",
        "stock_card_portfolio": "В портфеле",
        "stock_card_tracking": "Слежение",
        "source": "Источник",
        "price": "Цена",
        "days_5": "5 дней",
        "month_1": "1 месяц",
        "signal_title": "🚨 Сигнал по {name}",
        "signal_growth": "Акция сильно выросла за последние 5 дней.",
        "signal_drop": "Акция заметно снизилась за последние 5 дней.",
        "analysis_header": "📊 {name}",
        "fallback_company_title": "1. Что это за компания:",
        "fallback_business_title": "2. Чем занимается компания:",
        "fallback_now_title": "3. Что сейчас происходит с акцией:",
        "fallback_longterm_title": "4. Подходит ли акция на долгосрок:",
        "fallback_dividends_title": "5. Выплаты акционерам:",
        "fallback_result_title": "6. Итог:",
        "fallback_dividend_note": "Важно: дата в истории дивидендов yfinance обычно относится к ex-dividend date, а не к фактической дате выплаты.",
        "fallback_no_dividends": "По доступным данным регулярные дивидендные выплаты не найдены или данных пока недостаточно.",
        "fallback_has_dividends": "Компания платит дивиденды. Последний зафиксированный дивиденд: <b>{last_dividend}</b> на дату <b>{last_date}</b>. Сумма дивидендов за последние 12 месяцев по доступной истории: <b>{recent_total}</b>.",
        "fallback_longterm_text_default": "Для долгосрочного инвестора важно смотреть не только на цену, но и на устойчивость бизнеса, сектор, прибыльность и наличие понятной стратегии роста.",
        "fallback_final_text": "Для начинающего инвестора акция интереснее тогда, когда ты понимаешь сам бизнес компании, ее устойчивость на длинной дистанции и политику выплат.",
        "fallback_no_description": "Подробное описание компании сейчас недоступно.",
        "fallback_sector_unknown": "не указан",
        "fallback_industry_unknown": "не указана",
        "trend_growth": "рост",
        "trend_decline": "снижение",
        "trend_sideways": "боковик",
        "trend_positive": "позитивный",
        "trend_negative": "негативный",
        "trend_neutral": "нейтральный",
        "no_market_data": "Рыночные котировки сейчас недоступны. Ниже — обзор компании и долгосрочных факторов.",
        "dividend_unknown": "Информация о дивидендах ограничена.",
    },
    "en": {
        "start": "Hello, {name} 👋\n\nI am a stock analysis and tracking bot.",
        "menu": "/list — stock list\n/portfolio — portfolio\n/analyze — analysis",
        "choose_language": "Choose language / Выберите язык / Тілді таңдаңыз / Vyberte jazyk",
        "language_saved": "Language saved: {language}",
        "menu_list": "📋 Stock list",
        "menu_portfolio": "💼 My portfolio",
        "menu_analyze": "📊 Analyze",
        "menu_watch_on": "📡 Enable tracking",
        "menu_watch_off": "⛔ Disable tracking",
        "menu_help": "ℹ️ Help",
        "menu_language": "🌐 Change language",
        "help_title": "{name}, what this bot can do:",
        "help_text": "/list — open the stock list\n/portfolio — show your saved stocks\n/analyze — choose a stock for analysis\n/watch — enable portfolio tracking\n/unwatch — disable portfolio tracking\n\nHow to use:\n1. Open the stock list\n2. Choose a stock\n3. Add it to your portfolio\n4. Read the analysis\n5. Enable tracking",
        "list_title": "{name}, stock list",
        "choose_stock": "Choose a stock:",
        "press_stock": "Tap the stock you need:",
        "portfolio_empty": "💼 {name}, your portfolio is empty. Add stocks from the list.",
        "portfolio_title": "💼 {name}'s portfolio:",
        "portfolio_pick": "Choose a stock from your portfolio:",
        "analyze_pick": "📊 {name}, choose a stock for analysis:",
        "watch_on": "📡 {name}, portfolio tracking enabled.",
        "watch_off": "⛔ {name}, portfolio tracking disabled.",
        "stock_not_found": "Stock not found",
        "back_to_list": "🔙 Back to list",
        "add_portfolio": "➕ Add to portfolio",
        "remove_portfolio": "➖ Remove from portfolio",
        "short_analysis": "⚡ Short analysis",
        "full_analysis": "📘 Detailed analysis",
        "analysis_available": "available",
        "analysis_unavailable": "info without quotes",
        "yes": "yes",
        "no": "no",
        "on": "enabled",
        "off": "disabled",
        "choose_action": "Choose an action below.",
        "quote_error": "❌ Could not get Yahoo Finance quotes for <b>{name}</b> right now. Showing an informational analysis without live market prices.",
        "short_analysis_progress": "⚡ {name}, preparing a short analysis for <b>{stock}</b>...",
        "full_analysis_progress": "📘 {name}, preparing a detailed analysis for <b>{stock}</b>...",
        "doing_short": "Preparing short analysis...",
        "doing_full": "Preparing detailed analysis...",
        "added": "Added to portfolio",
        "removed": "Removed from portfolio",
        "already_added": "Stock is already in the portfolio",
        "remove_failed": "Could not remove",
        "stock_card_kase": "KASE",
        "stock_card_yahoo": "Quote sources",
        "stock_card_analysis": "Analysis",
        "stock_card_portfolio": "In portfolio",
        "stock_card_tracking": "Tracking",
        "source": "Source",
        "price": "Price",
        "days_5": "5 days",
        "month_1": "1 month",
        "signal_title": "🚨 Signal for {name}",
        "signal_growth": "The stock rose sharply over the last 5 days.",
        "signal_drop": "The stock dropped noticeably over the last 5 days.",
        "analysis_header": "📊 {name}",
        "fallback_company_title": "1. What kind of company is this:",
        "fallback_business_title": "2. What does the company do:",
        "fallback_now_title": "3. What is happening with the stock now:",
        "fallback_longterm_title": "4. Is this stock suitable for long term:",
        "fallback_dividends_title": "5. Shareholder payments:",
        "fallback_result_title": "6. Conclusion:",
        "fallback_dividend_note": "Important: in yfinance, the dividend history date usually refers to the ex-dividend date, not the actual payment date.",
        "fallback_no_dividends": "No regular dividend record was found in available data, or the data is too limited.",
        "fallback_has_dividends": "The company pays dividends. Last recorded dividend: <b>{last_dividend}</b> on <b>{last_date}</b>. Total dividends over the last 12 months from available history: <b>{recent_total}</b>.",
        "fallback_longterm_text_default": "For a long-term investor, it is important to look not only at price, but also at business stability, sector, profitability, and whether the company has a clear growth strategy.",
        "fallback_final_text": "For a beginner investor, a stock becomes more interesting when you understand the business itself, its long-term resilience, and its payment policy.",
        "fallback_no_description": "A detailed company description is currently unavailable.",
        "fallback_sector_unknown": "not specified",
        "fallback_industry_unknown": "not specified",
        "trend_growth": "growth",
        "trend_decline": "decline",
        "trend_sideways": "sideways",
        "trend_positive": "positive",
        "trend_negative": "negative",
        "trend_neutral": "neutral",
        "no_market_data": "Live market quotes are currently unavailable. Below is a company overview and long-term analysis.",
        "dividend_unknown": "Dividend information is limited.",
    },
}

# Fallback to Russian for missing languages
TEXTS["kk"] = TEXTS["ru"].copy() | {
    "start": "Сәлем, {name} 👋\n\nМен акцияларды талдау және бақылау ботымын.",
    "menu": "/list — акциялар тізімі\n/portfolio — менің портфелім\n/analyze — талдау",
    "choose_language": "Тілді таңдаңыз / Choose language / Выберите язык / Vyberte jazyk",
    "language_saved": "Тіл сақталды: {language}",
    "menu_list": "📋 Акциялар тізімі",
    "menu_portfolio": "💼 Менің портфелім",
    "menu_analyze": "📊 Талдау",
    "menu_watch_on": "📡 Бақылауды қосу",
    "menu_watch_off": "⛔ Бақылауды өшіру",
    "menu_help": "ℹ️ Көмек",
    "menu_language": "🌐 Тілді өзгерту",
    "help_title": "{name}, бот не істей алады:",
    "list_title": "{name}, акциялар тізімі",
    "choose_stock": "Акцияны таңдаңыз:",
    "press_stock": "Қажетті акцияны басыңыз:",
    "portfolio_empty": "💼 {name}, портфеліңіз әзірге бос. Акцияларды тізімнен қосыңыз.",
    "portfolio_title": "💼 {name} портфелі:",
    "portfolio_pick": "Портфельден акция таңдаңыз:",
    "analyze_pick": "📊 {name}, талдау үшін акция таңдаңыз:",
    "watch_on": "📡 {name}, портфельді бақылау қосылды.",
    "watch_off": "⛔ {name}, портфельді бақылау өшірілді.",
    "stock_not_found": "Акция табылмады",
    "back_to_list": "🔙 Тізімге оралу",
    "add_portfolio": "➕ Портфельге қосу",
    "remove_portfolio": "➖ Портфельден өшіру",
    "short_analysis": "⚡ Қысқа талдау",
    "full_analysis": "📘 Толық талдау",
    "analysis_unavailable": "бағасыз ақпарат",
    "yes": "иә",
    "no": "жоқ",
    "on": "қосулы",
    "off": "өшірулі",
    "choose_action": "Төменнен әрекетті таңдаңыз.",
}
TEXTS["cs"] = TEXTS["en"].copy() | {
    "start": "Ahoj, {name} 👋\n\nJsem bot pro analýzu a sledování akcií.",
    "menu": "/list — seznam akcií\n/portfolio — portfolio\n/analyze — analýza",
    "choose_language": "Vyberte jazyk / Choose language / Выберите язык / Тілді таңдаңыз",
    "language_saved": "Jazyk uložen: {language}",
    "menu_list": "📋 Seznam akcií",
    "menu_portfolio": "💼 Moje portfolio",
    "menu_analyze": "📊 Analyzovat",
    "menu_watch_on": "📡 Zapnout sledování",
    "menu_watch_off": "⛔ Vypnout sledování",
    "menu_help": "ℹ️ Nápověda",
    "menu_language": "🌐 Změnit jazyk",
    "help_title": "{name}, co tento bot umí:",
    "list_title": "{name}, seznam akcií",
    "choose_stock": "Vyber akcii:",
    "press_stock": "Klikni na požadovanou akcii:",
    "portfolio_empty": "💼 {name}, tvoje portfolio je zatím prázdné. Přidej akcie ze seznamu.",
    "portfolio_title": "💼 Portfolio uživatele {name}:",
    "portfolio_pick": "Vyber akcii z portfolia:",
    "analyze_pick": "📊 {name}, vyber akcii k analýze:",
    "watch_on": "📡 {name}, sledování portfolia bylo zapnuto.",
    "watch_off": "⛔ {name}, sledování portfolia bylo vypnuto.",
    "stock_not_found": "Akcie nebyla nalezena",
    "back_to_list": "🔙 Zpět na seznam",
    "add_portfolio": "➕ Přidat do portfolia",
    "remove_portfolio": "➖ Odebrat z portfolia",
    "short_analysis": "⚡ Krátká analýza",
    "full_analysis": "📘 Podrobná analýza",
    "analysis_unavailable": "informace bez kotací",
}


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio (
            user_id INTEGER NOT NULL,
            stock_id TEXT NOT NULL,
            UNIQUE(user_id, stock_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS watchers (
            user_id INTEGER PRIMARY KEY,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts_sent (
            user_id INTEGER NOT NULL,
            stock_id TEXT NOT NULL,
            last_signal TEXT,
            UNIQUE(user_id, stock_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ru'
        )
        """
    )
    conn.commit()
    conn.close()


def escape_text(text: str) -> str:
    return html.escape(str(text), quote=False)


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def format_percent(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def cleanup_ai_html(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("```html", "").replace("```", "").strip()
    return cleaned


def get_user_name(user: types.User) -> str:
    if user.first_name:
        return escape_text(user.first_name)
    if user.username:
        return escape_text(user.username)
    return "friend"


def truncate_text(text: str, max_len: int = 500) -> str:
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def split_text_into_chunks(text: str, max_length: int = 4000) -> list[str]:
    if len(text) <= max_length:
        return [text]
    chunks = []
    current_chunk = ""
    paragraphs = text.split("\n\n")
    for paragraph in paragraphs:
        candidate = paragraph if not current_chunk else current_chunk + "\n\n" + paragraph
        if len(candidate) <= max_length:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = paragraph
            else:
                for i in range(0, len(paragraph), max_length):
                    chunks.append(paragraph[i:i + max_length])
                current_chunk = ""
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


async def send_long_message(message_obj, text: str, reply_markup=None):
    chunks = split_text_into_chunks(text)
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        await message_obj.answer(chunk, parse_mode="HTML", reply_markup=markup)


def get_user_language(user_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT language FROM user_settings WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] in TEXTS else "ru"


def set_user_language(user_id: int, language: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_settings (user_id, language)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
        """,
        (user_id, language),
    )
    conn.commit()
    conn.close()


def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_user_language(user_id)
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return text.format(**kwargs)


def add_to_portfolio(user_id: int, stock_id: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO portfolio (user_id, stock_id) VALUES (?, ?)", (user_id, stock_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_from_portfolio(user_id: int, stock_id: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM portfolio WHERE user_id = ? AND stock_id = ?", (user_id, stock_id))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_portfolio(user_id: int) -> list[str]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT stock_id FROM portfolio WHERE user_id = ? ORDER BY stock_id", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def set_watcher(user_id: int, active: bool):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO watchers (user_id, is_active)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET is_active = excluded.is_active
        """,
        (user_id, 1 if active else 0),
    )
    conn.commit()
    conn.close()


def is_watching(user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT is_active FROM watchers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def get_watchers() -> list[int]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM watchers WHERE is_active = 1")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_last_signal(user_id: int, stock_id: str) -> Optional[str]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT last_signal FROM alerts_sent WHERE user_id = ? AND stock_id = ?", (user_id, stock_id))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def set_last_signal(user_id: int, stock_id: str, signal: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO alerts_sent (user_id, stock_id, last_signal)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, stock_id) DO UPDATE SET last_signal = excluded.last_signal
        """,
        (user_id, stock_id, signal),
    )
    conn.commit()
    conn.close()


def has_analysis_source(stock: dict) -> bool:
    return True  # all stocks can produce useful info now


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=LANGUAGES["ru"], callback_data="set_lang:ru")],
            [InlineKeyboardButton(text=LANGUAGES["en"], callback_data="set_lang:en")],
            [InlineKeyboardButton(text=LANGUAGES["kk"], callback_data="set_lang:kk")],
            [InlineKeyboardButton(text=LANGUAGES["cs"], callback_data="set_lang:cs")],
        ]
    )


def main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(user_id, "menu_list"))],
            [KeyboardButton(text=t(user_id, "menu_portfolio")), KeyboardButton(text=t(user_id, "menu_analyze"))],
            [KeyboardButton(text=t(user_id, "menu_watch_on")), KeyboardButton(text=t(user_id, "menu_watch_off"))],
            [KeyboardButton(text=t(user_id, "menu_help")), KeyboardButton(text=t(user_id, "menu_language"))],
        ],
        resize_keyboard=True
    )


def stock_list_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for stock in STOCKS:
        rows.append([InlineKeyboardButton(text=f"{stock['kase_ticker']} — {stock['name']}", callback_data=f"stock:{stock['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stock_actions_keyboard(stock: dict, in_portfolio: bool, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(user_id, "short_analysis"), callback_data=f"analyze_short:{stock['id']}"),
                InlineKeyboardButton(text=t(user_id, "full_analysis"), callback_data=f"analyze_full:{stock['id']}"),
            ],
            [
                InlineKeyboardButton(
                    text=t(user_id, "add_portfolio") if not in_portfolio else t(user_id, "remove_portfolio"),
                    callback_data=f"toggle_portfolio:{stock['id']}",
                )
            ],
            [InlineKeyboardButton(text=t(user_id, "back_to_list"), callback_data="back_to_list")],
        ]
    )


def portfolio_keyboard(stock_ids: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for stock_id in stock_ids:
        stock = STOCKS_BY_ID.get(stock_id)
        if stock:
            rows.append([InlineKeyboardButton(text=f"{stock['kase_ticker']} — {stock['name']}", callback_data=f"stock:{stock_id}")])
    if not rows:
        rows = [[InlineKeyboardButton(text="📋", callback_data="back_to_list")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_stock_card(stock: dict, in_portfolio: bool, watching: bool, user_id: int) -> str:
    yahoo_text = ", ".join(stock["yahoo_tickers"]) if stock.get("yahoo_tickers") else "fallback info only"
    return (
        f"<b>{escape_text(stock['name'])}</b>\n"
        f"<b>{t(user_id, 'stock_card_kase')}:</b> {escape_text(stock['kase_ticker'])}\n"
        f"<b>{t(user_id, 'stock_card_yahoo')}:</b> {escape_text(yahoo_text)}\n"
        f"<b>{t(user_id, 'stock_card_analysis')}:</b> {t(user_id, 'analysis_available') if stock.get('yahoo_tickers') else t(user_id, 'analysis_unavailable')}\n"
        f"<b>{t(user_id, 'stock_card_portfolio')}:</b> {t(user_id, 'yes') if in_portfolio else t(user_id, 'no')}\n"
        f"<b>{t(user_id, 'stock_card_tracking')}:</b> {t(user_id, 'on') if watching else t(user_id, 'off')}\n\n"
        f"{t(user_id, 'choose_action')}"
    )


def get_stock_metrics_from_candidates(yahoo_tickers: list[str]) -> tuple[str, float, float, float]:
    last_error = None
    for ticker_symbol in yahoo_tickers:
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="1mo", interval="1d", auto_adjust=False)
            if hist.empty or "Close" not in hist.columns:
                continue
            close_series = hist["Close"].dropna()
            if close_series.empty:
                continue
            current_price = safe_float(close_series.iloc[-1])
            base_5d = safe_float(close_series.iloc[-5]) if len(close_series) >= 5 else safe_float(close_series.iloc[0])
            base_1mo = safe_float(close_series.iloc[0])
            change_5d = ((current_price - base_5d) / base_5d * 100) if base_5d else 0.0
            change_1mo = ((current_price - base_1mo) / base_1mo * 100) if base_1mo else 0.0
            return ticker_symbol, current_price, change_5d, change_1mo
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise ValueError("No live market data")
    raise ValueError("No live market data")


def get_company_info_from_candidates(stock: dict) -> tuple[str | None, dict]:
    empty_info = {
        "short_name": None,
        "long_name": None,
        "sector": None,
        "industry": None,
        "country": None,
        "website": None,
        "business_summary": None,
        "market_cap": None,
        "trailing_pe": None,
        "forward_pe": None,
        "dividend_yield": None,
        "dividend_rate": None,
        "payout_ratio": None,
        "long_term_note": None,
        "dividend_note": None,
    }
    yahoo_tickers = stock.get("yahoo_tickers", [])
    for ticker_symbol in yahoo_tickers:
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info or {}
            if info:
                merged = {
                    "short_name": info.get("shortName"),
                    "long_name": info.get("longName"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "country": info.get("country"),
                    "website": info.get("website"),
                    "business_summary": info.get("longBusinessSummary"),
                    "market_cap": info.get("marketCap"),
                    "trailing_pe": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "dividend_yield": info.get("dividendYield"),
                    "dividend_rate": info.get("dividendRate"),
                    "payout_ratio": info.get("payoutRatio"),
                    "long_term_note": None,
                    "dividend_note": None,
                }
                static_info = STATIC_COMPANY_INFO.get(stock["id"], {})
                for k, v in static_info.items():
                    if not merged.get(k):
                        merged[k] = v
                return ticker_symbol, merged
        except Exception:
            continue
    static_info = STATIC_COMPANY_INFO.get(stock["id"], {})
    merged = empty_info.copy()
    merged.update(static_info)
    return None, merged


def get_dividend_info_from_candidates(yahoo_tickers: list[str]) -> tuple[str | None, dict]:
    result = {"has_dividends": False, "last_dividend": None, "last_dividend_date": None, "dividend_count": 0, "recent_total": 0.0}
    for ticker_symbol in yahoo_tickers:
        try:
            ticker = yf.Ticker(ticker_symbol)
            dividends = ticker.dividends
            if dividends is None or len(dividends) == 0:
                continue
            dividends = dividends.dropna()
            if len(dividends) == 0:
                continue
            result["has_dividends"] = True
            result["dividend_count"] = int(len(dividends))
            result["last_dividend"] = float(dividends.iloc[-1])
            result["last_dividend_date"] = dividends.index[-1].strftime("%Y-%m-%d")
            try:
                last_12 = dividends.last("365D")
                result["recent_total"] = float(last_12.sum()) if len(last_12) > 0 else 0.0
            except Exception:
                result["recent_total"] = 0.0
            return ticker_symbol, result
        except Exception:
            continue
    return None, result


def fallback_analysis(stock: dict, price: Optional[float], change_5d: Optional[float], change_1mo: Optional[float], company_info: dict, dividend_info: dict, user_id: int) -> str:
    trend_5d = t(user_id, "trend_growth") if (change_5d or 0) > 0 else t(user_id, "trend_decline") if (change_5d or 0) < 0 else t(user_id, "trend_sideways")
    trend_1mo = t(user_id, "trend_positive") if (change_1mo or 0) > 0 else t(user_id, "trend_negative") if (change_1mo or 0) < 0 else t(user_id, "trend_neutral")
    summary = company_info.get("business_summary") or t(user_id, "fallback_no_description")
    summary = truncate_text(summary, 700)
    sector = company_info.get("sector") or t(user_id, "fallback_sector_unknown")
    industry = company_info.get("industry") or t(user_id, "fallback_industry_unknown")
    long_term_note = company_info.get("long_term_note") or t(user_id, "fallback_longterm_text_default")
    dividend_note = company_info.get("dividend_note") or t(user_id, "dividend_unknown")
    if dividend_info.get("has_dividends"):
        dividend_text = t(
            user_id, "fallback_has_dividends",
            last_dividend=f"{dividend_info['last_dividend']:.4f}",
            last_date=dividend_info["last_dividend_date"],
            recent_total=f"{dividend_info['recent_total']:.4f}",
        )
    else:
        dividend_text = t(user_id, "fallback_no_dividends")
    market_block = (
        f"{escape_text(stock['name'])} — {t(user_id, 'price')}: <b>{price:.2f}</b>. "
        f"{t(user_id, 'days_5')}: <b>{trend_5d}</b> ({format_percent(change_5d or 0)}), "
        f"{t(user_id, 'month_1')}: <b>{trend_1mo}</b> ({format_percent(change_1mo or 0)})."
        if price is not None else t(user_id, "no_market_data")
    )
    return (
        f"<b>{t(user_id, 'fallback_company_title')}</b>\n{escape_text(summary)}\n\n"
        f"<b>{t(user_id, 'fallback_business_title')}</b>\n"
        f"Sector: <b>{escape_text(sector)}</b>. Industry: <b>{escape_text(industry)}</b>.\n\n"
        f"<b>{t(user_id, 'fallback_now_title')}</b>\n{market_block}\n\n"
        f"<b>{t(user_id, 'fallback_longterm_title')}</b>\n{escape_text(long_term_note)}\n\n"
        f"<b>{t(user_id, 'fallback_dividends_title')}</b>\n{dividend_text}\n{escape_text(dividend_note)}\n"
        f"<i>{t(user_id, 'fallback_dividend_note')}</i>\n\n"
        f"<b>{t(user_id, 'fallback_result_title')}</b>\n{t(user_id, 'fallback_final_text')}"
    )


def build_prompt(stock: dict, price: Optional[float], change_5d: Optional[float], change_1mo: Optional[float], user_name: str, company_info: dict, dividend_info: dict, analysis_mode: str, language_code: str) -> str:
    summary = truncate_text(company_info.get("business_summary") or "Description unavailable", 800)
    length_instruction = "Keep the answer short and clear, around 700–1200 characters." if analysis_mode == "short" else "Make the answer detailed and useful for a beginner, around 1800–2500 characters."
    output_language = LANGUAGE_NAMES.get(language_code, "Russian")
    price_text = "unavailable" if price is None else f"{price:.2f}"
    ch5_text = "unavailable" if change_5d is None else format_percent(change_5d)
    ch1_text = "unavailable" if change_1mo is None else format_percent(change_1mo)
    dividends_block = (
        f"- Has dividends: {'yes' if dividend_info.get('has_dividends') else 'no'}\n"
        f"- Last dividend: {dividend_info.get('last_dividend')}\n"
        f"- Last dividend date: {dividend_info.get('last_dividend_date')}\n"
        f"- Total dividends over last 12 months: {dividend_info.get('recent_total')}\n"
    )
    return (
        f"You are a professional financial analyst.\n\n"
        f"Write a useful stock analysis for a beginner investor named {user_name}.\n"
        f"Write the final answer strictly in {output_language}.\n"
        f"Use simple language, avoid jargon, but stay accurate and useful.\n\n"
        f"Stock data:\n"
        f"- Company: {stock['name']}\n"
        f"- Ticker: {stock['kase_ticker']}\n"
        f"- Current price: {price_text}\n"
        f"- 5-day change: {ch5_text}\n"
        f"- 1-month change: {ch1_text}\n\n"
        f"Company data:\n"
        f"- Sector: {company_info.get('sector')}\n"
        f"- Industry: {company_info.get('industry')}\n"
        f"- Market cap: {company_info.get('market_cap')}\n"
        f"- Trailing P/E: {company_info.get('trailing_pe')}\n"
        f"- Forward P/E: {company_info.get('forward_pe')}\n"
        f"- Dividend Yield: {company_info.get('dividend_yield')}\n"
        f"- Dividend Rate: {company_info.get('dividend_rate')}\n"
        f"- Payout Ratio: {company_info.get('payout_ratio')}\n"
        f"- Business summary: {summary}\n"
        f"- Long-term note: {company_info.get('long_term_note')}\n"
        f"- Dividend note: {company_info.get('dividend_note')}\n\n"
        f"Dividend data:\n{dividends_block}\n"
        f"Structure:\n"
        f"1. What company is this in simple words\n"
        f"2. How it makes money and why it may be interesting for an investor\n"
        f"3. What is happening with the stock now\n"
        f"4. Whether this stock is suitable for long-term holding\n"
        f"5. Risks for a long-term investor\n"
        f"6. Shareholder payments\n"
        f"7. Final conclusion for a beginner\n\n"
        f"Important rules:\n"
        f"- Final answer only in {output_language}\n"
        f"- Use Telegram HTML tags such as <b>...</b> for headings\n"
        f"- Do not use Markdown\n"
        f"- Do not invent missing data\n"
        f"- If live quotes are unavailable, say that clearly and still give a useful company analysis\n"
        f"- Mention that yfinance dividend history usually refers to ex-dividend date, not actual payment date\n"
        f"- {length_instruction}\n"
    )


async def fetch_gemini_analysis(prompt: str, retries: int = 4) -> Optional[str]:
    if not GEMINI_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    timeout = aiohttp.ClientTimeout(total=45)
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    if resp.status == 200:
                        candidates = result.get("candidates", [])
                        if not candidates:
                            return None
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if not parts:
                            return None
                        text = parts[0].get("text")
                        return cleanup_ai_html(text) if text else None
                    if resp.status in (429, 500, 503) and attempt < retries - 1:
                        delay = (2 ** attempt) + random.uniform(0.5, 1.5)
                        await asyncio.sleep(delay)
                        continue
                    return None
        except Exception:
            if attempt < retries - 1:
                delay = (2 ** attempt) + random.uniform(0.5, 1.5)
                await asyncio.sleep(delay)
                continue
            return None
    return None


async def analyze_stock(stock: dict, user_name: str, user_id: int, analysis_mode: str = "full") -> str:
    yahoo_tickers = stock.get("yahoo_tickers") or []
    used_ticker = None
    price = None
    change_5d = None
    change_1mo = None
    try:
        if yahoo_tickers:
            used_ticker, price, change_5d, change_1mo = get_stock_metrics_from_candidates(yahoo_tickers)
    except Exception:
        pass
    _, company_info = get_company_info_from_candidates(stock)
    _, dividend_info = get_dividend_info_from_candidates(yahoo_tickers)
    body = None
    if GEMINI_KEY:
        prompt = build_prompt(stock, price, change_5d, change_1mo, user_name, company_info, dividend_info, analysis_mode, get_user_language(user_id))
        body = await fetch_gemini_analysis(prompt)
    if not body:
        body = fallback_analysis(stock, price, change_5d, change_1mo, company_info, dividend_info, user_id)
    source_text = used_ticker if used_ticker else "Static company info / fallback"
    header_lines = [
        f"<b>{t(user_id, 'analysis_header', name=escape_text(stock['name']))}</b>",
        f"<b>{t(user_id, 'stock_card_kase')}:</b> {escape_text(stock['kase_ticker'])}",
        f"<b>{t(user_id, 'source')}:</b> {escape_text(source_text)}",
    ]
    if price is not None:
        header_lines.append(f"<b>{t(user_id, 'price')}:</b> {price:.2f}")
        header_lines.append(f"<b>{t(user_id, 'days_5')}:</b> {format_percent(change_5d or 0)}")
        header_lines.append(f"<b>{t(user_id, 'month_1')}:</b> {format_percent(change_1mo or 0)}")
    else:
        header_lines.append(t(user_id, 'no_market_data'))
    return "\n".join(header_lines) + "\n\n" + body


async def monitor_portfolios():
    print("=== PORTFOLIO MONITOR STARTED ===")
    while True:
        users = get_watchers()
        for user_id in users:
            portfolio = get_portfolio(user_id)
            for stock_id in portfolio:
                stock = STOCKS_BY_ID.get(stock_id)
                if not stock or not stock.get("yahoo_tickers"):
                    continue
                try:
                    _, price, change_5d, change_1mo = get_stock_metrics_from_candidates(stock["yahoo_tickers"])
                    signal = None
                    if change_5d >= 2:
                        signal = "up"
                    elif change_5d <= -2:
                        signal = "down"
                    if not signal:
                        continue
                    last_signal = get_last_signal(user_id, stock_id)
                    if last_signal == signal:
                        continue
                    set_last_signal(user_id, stock_id, signal)
                    signal_text = t(user_id, "signal_growth") if signal == "up" else t(user_id, "signal_drop")
                    await bot.send_message(
                        user_id,
                        (
                            f"<b>{t(user_id, 'signal_title', name=escape_text(stock['name']))}</b>\n"
                            f"<b>{t(user_id, 'stock_card_kase')}:</b> {escape_text(stock['kase_ticker'])}\n"
                            f"<b>{t(user_id, 'price')}:</b> {price:.2f}\n"
                            f"<b>{t(user_id, 'days_5')}:</b> {format_percent(change_5d)}\n"
                            f"<b>{t(user_id, 'month_1')}:</b> {format_percent(change_1mo)}\n\n"
                            f"{signal_text}"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    continue
        await asyncio.sleep(300)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(t(message.from_user.id, "choose_language"), reply_markup=language_keyboard())


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user_name = get_user_name(message.from_user)
    await message.answer(
        f"<b>{t(message.from_user.id, 'help_title', name=user_name)}</b>\n{t(message.from_user.id, 'help_text')}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    user_name = get_user_name(message.from_user)
    await message.answer(
        f"<b>{t(message.from_user.id, 'list_title', name=user_name)}</b>\n{t(message.from_user.id, 'choose_stock')}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )
    await message.answer(t(message.from_user.id, "press_stock"), reply_markup=stock_list_keyboard())


@dp.message(Command("portfolio"))
async def cmd_portfolio(message: types.Message):
    user_name = get_user_name(message.from_user)
    stock_ids = get_portfolio(message.from_user.id)
    if not stock_ids:
        await message.answer(
            t(message.from_user.id, "portfolio_empty", name=user_name),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(message.from_user.id),
        )
        return
    lines = [f"<b>{t(message.from_user.id, 'portfolio_title', name=user_name)}</b>"]
    for stock_id in stock_ids:
        stock = STOCKS_BY_ID.get(stock_id)
        if stock:
            lines.append(f"• {escape_text(stock['kase_ticker'])} — {escape_text(stock['name'])}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard(message.from_user.id))
    await message.answer(t(message.from_user.id, "portfolio_pick"), reply_markup=portfolio_keyboard(stock_ids))


@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    user_name = get_user_name(message.from_user)
    await message.answer(
        t(message.from_user.id, "analyze_pick", name=user_name),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )
    await message.answer(t(message.from_user.id, "press_stock"), reply_markup=stock_list_keyboard())


@dp.message(Command("watch"))
async def cmd_watch(message: types.Message):
    user_name = get_user_name(message.from_user)
    set_watcher(message.from_user.id, True)
    await message.answer(t(message.from_user.id, "watch_on", name=user_name), parse_mode="HTML", reply_markup=main_menu_keyboard(message.from_user.id))


@dp.message(Command("unwatch"))
async def cmd_unwatch(message: types.Message):
    user_name = get_user_name(message.from_user)
    set_watcher(message.from_user.id, False)
    await message.answer(t(message.from_user.id, "watch_off", name=user_name), parse_mode="HTML", reply_markup=main_menu_keyboard(message.from_user.id))


@dp.message(F.text.in_(["📋 Список акций", "📋 Stock list", "📋 Акциялар тізімі", "📋 Seznam akcií"]))
async def btn_list(message: types.Message):
    await cmd_list(message)


@dp.message(F.text.in_(["💼 Мой портфель", "💼 My portfolio", "💼 Менің портфелім", "💼 Moje portfolio"]))
async def btn_portfolio(message: types.Message):
    await cmd_portfolio(message)


@dp.message(F.text.in_(["📊 Анализировать", "📊 Analyze", "📊 Талдау", "📊 Analyzovat"]))
async def btn_analyze(message: types.Message):
    await cmd_analyze(message)


@dp.message(F.text.in_(["📡 Включить слежение", "📡 Enable tracking", "📡 Бақылауды қосу", "📡 Zapnout sledování"]))
async def btn_watch(message: types.Message):
    await cmd_watch(message)


@dp.message(F.text.in_(["⛔ Выключить слежение", "⛔ Disable tracking", "⛔ Бақылауды өшіру", "⛔ Vypnout sledování"]))
async def btn_unwatch(message: types.Message):
    await cmd_unwatch(message)


@dp.message(F.text.in_(["ℹ️ Помощь", "ℹ️ Help", "ℹ️ Көмек", "ℹ️ Nápověda"]))
async def btn_help(message: types.Message):
    await cmd_help(message)


@dp.message(F.text.in_(["🌐 Сменить язык", "🌐 Change language", "🌐 Тілді өзгерту", "🌐 Změnit jazyk"]))
async def change_language_menu(message: types.Message):
    await message.answer(t(message.from_user.id, "choose_language"), reply_markup=language_keyboard())


@dp.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    set_user_language(user_id, lang)
    user_name = get_user_name(callback.from_user)
    await callback.message.answer(t(user_id, "language_saved", language=LANGUAGES[lang]), reply_markup=main_menu_keyboard(user_id))
    await callback.message.answer(f"{TEXTS[lang]['start'].format(name=user_name)}\n\n{TEXTS[lang]['menu']}", reply_markup=main_menu_keyboard(user_id))
    await callback.answer()


@dp.callback_query(F.data == "back_to_list")
async def back_to_list(callback: types.CallbackQuery):
    await callback.message.edit_text(t(callback.from_user.id, "press_stock"), reply_markup=stock_list_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("stock:"))
async def show_stock_card(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)
    if not stock:
        await callback.answer(t(callback.from_user.id, "stock_not_found"), show_alert=True)
        return
    in_portfolio = stock_id in get_portfolio(callback.from_user.id)
    watching = is_watching(callback.from_user.id)
    await callback.message.edit_text(
        build_stock_card(stock, in_portfolio, watching, callback.from_user.id),
        parse_mode="HTML",
        reply_markup=stock_actions_keyboard(stock, in_portfolio, callback.from_user.id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_portfolio:"))
async def toggle_portfolio(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)
    if not stock:
        await callback.answer(t(callback.from_user.id, "stock_not_found"), show_alert=True)
        return
    portfolio = get_portfolio(callback.from_user.id)
    in_portfolio = stock_id in portfolio
    if in_portfolio:
        removed = remove_from_portfolio(callback.from_user.id, stock_id)
        msg = t(callback.from_user.id, "removed") if removed else t(callback.from_user.id, "remove_failed")
    else:
        added = add_to_portfolio(callback.from_user.id, stock_id)
        msg = t(callback.from_user.id, "added") if added else t(callback.from_user.id, "already_added")
    in_portfolio = stock_id in get_portfolio(callback.from_user.id)
    watching = is_watching(callback.from_user.id)
    await callback.message.edit_text(
        build_stock_card(stock, in_portfolio, watching, callback.from_user.id),
        parse_mode="HTML",
        reply_markup=stock_actions_keyboard(stock, in_portfolio, callback.from_user.id),
    )
    await callback.answer(msg)


@dp.callback_query(F.data.startswith("analyze_short:"))
async def analyze_selected_stock_short(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)
    if not stock:
        await callback.answer(t(callback.from_user.id, "stock_not_found"), show_alert=True)
        return
    user_name = get_user_name(callback.from_user)
    await callback.answer(t(callback.from_user.id, "doing_short"))
    await callback.message.answer(
        t(callback.from_user.id, "short_analysis_progress", name=user_name, stock=escape_text(stock["name"])),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )
    result = await analyze_stock(stock, user_name, callback.from_user.id, analysis_mode="short")
    await send_long_message(callback.message, result, reply_markup=main_menu_keyboard(callback.from_user.id))


@dp.callback_query(F.data.startswith("analyze_full:"))
async def analyze_selected_stock_full(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)
    if not stock:
        await callback.answer(t(callback.from_user.id, "stock_not_found"), show_alert=True)
        return
    user_name = get_user_name(callback.from_user)
    await callback.answer(t(callback.from_user.id, "doing_full"))
    await callback.message.answer(
        t(callback.from_user.id, "full_analysis_progress", name=user_name, stock=escape_text(stock["name"])),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )
    result = await analyze_stock(stock, user_name, callback.from_user.id, analysis_mode="full")
    await send_long_message(callback.message, result, reply_markup=main_menu_keyboard(callback.from_user.id))


async def main():
    init_db()
    print("=== BOT STARTED ===")
    asyncio.create_task(monitor_portfolios())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
