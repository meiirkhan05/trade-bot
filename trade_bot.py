
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
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в .env")

if not GEMINI_KEY:
    raise ValueError("Не найден GEMINI_API_KEY в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_NAME = "portfolio.db"
GEMINI_MODEL = "gemini-2.5-flash-lite"

STOCKS = [
    {
        "id": "HSBK",
        "name": "Halyk Bank",
        "kase_ticker": "HSBK",
        "yahoo_tickers": ["HSBK.IL"],
    },
    {
        "id": "KZAP",
        "name": "Kazatomprom",
        "kase_ticker": "KZAP",
        "yahoo_tickers": ["KAP.IL"],
    },
    {
        "id": "KSPI",
        "name": "Kaspi.kz",
        "kase_ticker": "KSPI",
        "yahoo_tickers": ["KSPI"],
    },
    {
        "id": "KCEL",
        "name": "Kcell",
        "kase_ticker": "KCEL",
        "yahoo_tickers": ["KCEL.L"],
    },
    {
        "id": "KZTK",
        "name": "Kazakhtelecom",
        "kase_ticker": "KZTK",
        "yahoo_tickers": ["KZHXY", "KZTA.F"],
    },
    {
        "id": "KZTO",
        "name": "KazTransOil",
        "kase_ticker": "KZTO",
        "yahoo_tickers": [],
    },
    {
        "id": "KEGC",
        "name": "KEGOC",
        "kase_ticker": "KEGC",
        "yahoo_tickers": [],
    },
    {
        "id": "CCBN",
        "name": "Bank CenterCredit",
        "kase_ticker": "CCBN",
        "yahoo_tickers": [],
    },
]

STOCKS_BY_ID = {item["id"]: item for item in STOCKS}

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список акций")],
        [KeyboardButton(text="💼 Мой портфель"), KeyboardButton(text="📊 Анализировать")],
        [KeyboardButton(text="📡 Включить слежение"), KeyboardButton(text="⛔ Выключить слежение")],
        [KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True
)


TEXTS = {
    "start": {
        "ru": "Привет, {name} 👋\n\nЯ бот для анализа акций.",
        "en": "Hello, {name} 👋\n\nI am a stock analysis bot.",
        "kk": "Сәлем, {name} 👋\n\nМен акцияларды талдайтын ботпын.",
        "cs": "Ahoj, {name} 👋\n\nJsem bot pro analýzu akcií.",
    },
    "menu": {
        "ru": "/list — список акций\n/portfolio — портфель\n/analyze — анализ",
        "en": "/list — stock list\n/portfolio — portfolio\n/analyze — analysis",
        "kk": "/list — акциялар тізімі\n/portfolio — портфель\n/analyze — талдау",
        "cs": "/list — seznam akcií\n/portfolio — portfolio\n/analyze — analýza",
    }
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
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ru'
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
    return "друг"


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
        await message_obj.answer(
            chunk,
            parse_mode="HTML",
            reply_markup=markup
        )


def add_to_portfolio(user_id: int, stock_id: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO portfolio (user_id, stock_id) VALUES (?, ?)",
            (user_id, stock_id),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_from_portfolio(user_id: int, stock_id: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM portfolio WHERE user_id = ? AND stock_id = ?",
        (user_id, stock_id),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_portfolio(user_id: int) -> list[str]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT stock_id FROM portfolio WHERE user_id = ? ORDER BY stock_id",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_user_language(user_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT language FROM user_settings WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if row and row[0]:
        return row[0]
    return "ru"


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
    cur.execute(
        "SELECT last_signal FROM alerts_sent WHERE user_id = ? AND stock_id = ?",
        (user_id, stock_id),
    )
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
    return bool(stock.get("yahoo_tickers"))


def get_primary_ticker(stock: dict) -> str:
    tickers = stock.get("yahoo_tickers") or []
    return tickers[0] if tickers else "не подключен"


def stock_list_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for stock in STOCKS:
        rows.append([
            InlineKeyboardButton(
                text=f"{stock['kase_ticker']} — {stock['name']}",
                callback_data=f"stock:{stock['id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "kk": "🇰🇿 Қазақша",
    "cs": "🇨🇿 Čeština",
}


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=LANGUAGES["ru"], callback_data="set_lang:ru")],
            [InlineKeyboardButton(text=LANGUAGES["en"], callback_data="set_lang:en")],
            [InlineKeyboardButton(text=LANGUAGES["kk"], callback_data="set_lang:kk")],
            [InlineKeyboardButton(text=LANGUAGES["cs"], callback_data="set_lang:cs")],
        ]
    )


def stock_actions_keyboard(stock: dict, in_portfolio: bool) -> InlineKeyboardMarkup:
    rows = []

    if has_analysis_source(stock):
        rows.append([
            InlineKeyboardButton(text="⚡ Короткий анализ", callback_data=f"analyze_short:{stock['id']}"),
            InlineKeyboardButton(text="📘 Подробный анализ", callback_data=f"analyze_full:{stock['id']}")
        ])

    rows.append([
        InlineKeyboardButton(
            text="➕ Добавить в портфель" if not in_portfolio else "➖ Удалить из портфеля",
            callback_data=f"toggle_portfolio:{stock['id']}",
        )
    ])

    rows.append([
        InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_list")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def portfolio_keyboard(stock_ids: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for stock_id in stock_ids:
        stock = STOCKS_BY_ID.get(stock_id)
        if stock:
            rows.append([
                InlineKeyboardButton(
                    text=f"{stock['kase_ticker']} — {stock['name']}",
                    callback_data=f"stock:{stock_id}",
                )
            ])

    if not rows:
        rows = [[InlineKeyboardButton(text="📋 Открыть список акций", callback_data="back_to_list")]]

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_stock_card(stock: dict, in_portfolio: bool, watching: bool) -> str:
    yahoo_text = ", ".join(stock["yahoo_tickers"]) if stock.get("yahoo_tickers") else "пока не подключен"
    analysis_text = "доступен" if has_analysis_source(stock) else "пока недоступен"

    return (
        f"<b>{escape_text(stock['name'])}</b>\n"
        f"<b>KASE:</b> {escape_text(stock['kase_ticker'])}\n"
        f"<b>Yahoo ticker:</b> {escape_text(yahoo_text)}\n"
        f"<b>Анализ:</b> {analysis_text}\n"
        f"<b>В портфеле:</b> {'да' if in_portfolio else 'нет'}\n"
        f"<b>Слежение:</b> {'включено' if watching else 'выключено'}\n\n"
        f"Выбери действие ниже."
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
        raise ValueError("Не удалось получить историю цен из Yahoo Finance")
    raise ValueError("Не удалось получить историю цен из Yahoo Finance")


def get_company_info_from_candidates(yahoo_tickers: list[str]) -> tuple[str | None, dict]:
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
    }

    for ticker_symbol in yahoo_tickers:
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info or {}
            if info:
                return ticker_symbol, {
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
                }
        except Exception:
            continue

    return None, empty_info


def get_dividend_info_from_candidates(yahoo_tickers: list[str]) -> tuple[str | None, dict]:
    result = {
        "has_dividends": False,
        "last_dividend": None,
        "last_dividend_date": None,
        "dividend_count": 0,
        "recent_total": 0.0,
    }

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


def fallback_analysis(
    ticker_name: str,
    price: float,
    change_5d: float,
    change_1mo: float,
    company_info: dict,
    dividend_info: dict,
) -> str:
    trend_5d = "рост" if change_5d > 0 else "снижение" if change_5d < 0 else "боковик"
    trend_1mo = "позитивный" if change_1mo > 0 else "негативный" if change_1mo < 0 else "нейтральный"

    summary = company_info.get("business_summary") or "Подробное описание компании сейчас недоступно."
    summary = truncate_text(summary, 450)

    sector = company_info.get("sector") or "не указан"
    industry = company_info.get("industry") or "не указана"

    if dividend_info.get("has_dividends"):
        dividend_text = (
            f"Компания платит дивиденды. "
            f"Последний зафиксированный дивиденд: <b>{dividend_info['last_dividend']:.4f}</b> "
            f"на дату <b>{dividend_info['last_dividend_date']}</b>. "
            f"Сумма дивидендов за последние 12 месяцев по доступной истории: "
            f"<b>{dividend_info['recent_total']:.4f}</b>."
        )
    else:
        dividend_text = (
            "По доступным данным история дивидендов не найдена или компания не делает регулярных выплат акционерам."
        )

    long_term_text = (
        "Для долгосрочного инвестора важно смотреть не только на цену, но и на устойчивость бизнеса, сектор, "
        "прибыльность и наличие понятной стратегии роста. "
        "Если компания сильная по бизнесу и переживает рыночные просадки без разрушения модели, она обычно интереснее для долгосрока."
    )

    return (
        f"<b>1. Что это за компания:</b>\n"
        f"{escape_text(summary)}\n\n"

        f"<b>2. Чем занимается компания:</b>\n"
        f"Сектор: <b>{escape_text(sector)}</b>. "
        f"Отрасль: <b>{escape_text(industry)}</b>.\n\n"

        f"<b>3. Что сейчас происходит с акцией:</b>\n"
        f"Сейчас акция <b>{escape_text(ticker_name)}</b> торгуется по цене <b>{price:.2f}</b>. "
        f"За 5 дней бумага показывает <b>{trend_5d}</b> ({format_percent(change_5d)}), "
        f"а за месяц картина выглядит как <b>{trend_1mo}</b> ({format_percent(change_1mo)}).\n\n"

        f"<b>4. Подходит ли акция на долгосрок:</b>\n"
        f"{long_term_text}\n\n"

        f"<b>5. Выплаты акционерам:</b>\n"
        f"{dividend_text}\n"
        f"<i>Важно: дата в истории дивидендов у yfinance обычно относится к ex-dividend date, а не к фактической дате выплаты.</i>\n\n"

        f"<b>6. Итог:</b>\n"
        f"Для начинающего инвестора эта акция интереснее тогда, когда ты понимаешь сам бизнес компании, "
        f"ее устойчивость на длинной дистанции и политику выплат, а не смотришь только на текущую цену."
    )


def build_prompt(
    ticker_name: str,
    ticker_symbol: str,
    price: float,
    change_5d: float,
    change_1mo: float,
    user_name: str,
    company_info: dict,
    dividend_info: dict,
    analysis_mode: str,
) -> str:
    summary = company_info.get("business_summary") or "Описание компании недоступно"
    summary = truncate_text(summary, 700)

    length_instruction = (
        "Ответ должен быть коротким и ясным, примерно 700–1200 символов."
        if analysis_mode == "short"
        else "Ответ должен быть подробным и полезным новичку, примерно 1800–2500 символов."
    )

    sector = company_info.get("sector") or "не указан"
    industry = company_info.get("industry") or "не указана"
    market_cap = company_info.get("market_cap")
    trailing_pe = company_info.get("trailing_pe")
    forward_pe = company_info.get("forward_pe")
    dividend_yield = company_info.get("dividend_yield")
    dividend_rate = company_info.get("dividend_rate")
    payout_ratio = company_info.get("payout_ratio")

    dividends_block = (
        f"- Есть дивиденды: {'да' if dividend_info.get('has_dividends') else 'нет'}\n"
        f"- Последний дивиденд: {dividend_info.get('last_dividend')}\n"
        f"- Дата последнего дивиденда: {dividend_info.get('last_dividend_date')}\n"
        f"- Сумма дивидендов за последние 12 месяцев: {dividend_info.get('recent_total')}\n"
    )

    return (
        f"Ты профессиональный финансовый аналитик.\n\n"
        f"Сделай полезный анализ для начинающего инвестора по имени {user_name}.\n"
        f"Пиши простым языком, без сложного жаргона, но по делу.\n\n"

        f"Данные по акции:\n"
        f"- Компания: {ticker_name}\n"
        f"- Тикер: {ticker_symbol}\n"
        f"- Текущая цена: {price:.2f}\n"
        f"- Изменение за 5 дней: {format_percent(change_5d)}\n"
        f"- Изменение за 1 месяц: {format_percent(change_1mo)}\n\n"

        f"Данные по компании:\n"
        f"- Сектор: {sector}\n"
        f"- Отрасль: {industry}\n"
        f"- Рыночная капитализация: {market_cap}\n"
        f"- Trailing P/E: {trailing_pe}\n"
        f"- Forward P/E: {forward_pe}\n"
        f"- Dividend Yield: {dividend_yield}\n"
        f"- Dividend Rate: {dividend_rate}\n"
        f"- Payout Ratio: {payout_ratio}\n"
        f"- Краткое описание бизнеса: {summary}\n\n"

        f"Информация по выплатам:\n"
        f"{dividends_block}\n"

        f"Сделай ответ по структуре:\n"
        f"1. Что это за компания простыми словами\n"
        f"2. Чем она зарабатывает и почему она может быть интересна инвестору\n"
        f"3. Что сейчас происходит с акцией\n"
        f"4. Подходит ли акция на долгосрок\n"
        f"5. Какие есть риски для долгосрочного инвестора\n"
        f"6. Выплаты компании акционерам: платит ли дивиденды, как это выглядит по доступным данным\n"
        f"7. Итог для новичка: покупать сейчас, ждать или изучить глубже\n\n"

        f"Очень важно:\n"
        f"- Ответ только на русском языке\n"
        f"- Используй HTML-теги Telegram\n"
        f"- Каждый заголовок делай жирным через <b>...</b>\n"
        f"- Не используй Markdown\n"
        f"- Не используй символы **, __, #, *, ```\n"
        f"- Не придумывай данные, которых нет\n"
        f"- Если по дивидендам информации мало, так и напиши\n"
        f"- Упомяни, что в истории yfinance дата дивидендов обычно относится к ex-dividend date\n"
        f"- {length_instruction}\n"
    )


async def fetch_gemini_analysis(prompt: str, retries: int = 5) -> Optional[str]:
    url = (
        f"https://generativelanguage.googleapis.com/v1/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    )

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
                        if not text:
                            return None
                        return cleanup_ai_html(text)

                    if resp.status in (429, 500, 503):
                        if attempt < retries - 1:
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


async def analyze_stock(stock: dict, user_name: str, analysis_mode: str = "full") -> str:
    yahoo_tickers = stock.get("yahoo_tickers") or []

    if not yahoo_tickers:
        return (
            f"<b>📊 {escape_text(stock['name'])}</b>\n"
            f"<b>Тикер KASE:</b> {escape_text(stock['kase_ticker'])}\n\n"
            f"Для этой бумаги пока не подключен надежный источник котировок, поэтому анализ временно недоступен.\n"
            f"Но ты уже можешь сохранить ее в портфель."
        )

    used_ticker, price, change_5d, change_1mo = get_stock_metrics_from_candidates(yahoo_tickers)
    _, company_info = get_company_info_from_candidates(yahoo_tickers)
    _, dividend_info = get_dividend_info_from_candidates(yahoo_tickers)

    prompt = build_prompt(
        ticker_name=stock["name"],
        ticker_symbol=stock["kase_ticker"],
        price=price,
        change_5d=change_5d,
        change_1mo=change_1mo,
        user_name=user_name,
        company_info=company_info,
        dividend_info=dividend_info,
        analysis_mode=analysis_mode,
    )

    ai_text = await fetch_gemini_analysis(prompt)

    if ai_text:
        body = ai_text
    else:
        body = fallback_analysis(
            ticker_name=stock["name"],
            price=price,
            change_5d=change_5d,
            change_1mo=change_1mo,
            company_info=company_info,
            dividend_info=dividend_info,
        )

    return (
        f"<b>📊 {escape_text(stock['name'])}</b>\n"
        f"<b>Тикер KASE:</b> {escape_text(stock['kase_ticker'])}\n"
        f"<b>Источник:</b> {escape_text(used_ticker)}\n"
        f"<b>Цена:</b> {price:.2f}\n"
        f"<b>5 дней:</b> {format_percent(change_5d)}\n"
        f"<b>1 месяц:</b> {format_percent(change_1mo)}\n\n"
        f"{body}"
    )


async def monitor_portfolios():
    print("=== PORTFOLIO MONITOR STARTED ===")

    while True:
        users = get_watchers()

        for user_id in users:
            portfolio = get_portfolio(user_id)

            for stock_id in portfolio:
                stock = STOCKS_BY_ID.get(stock_id)
                if not stock or not has_analysis_source(stock):
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

                    signal_text = "сильно выросла" if signal == "up" else "заметно снизилась"

                    await bot.send_message(
                        user_id,
                        (
                            f"🚨 <b>Сигнал по {escape_text(stock['name'])}</b>\n"
                            f"<b>KASE:</b> {escape_text(stock['kase_ticker'])}\n"
                            f"<b>Цена:</b> {price:.2f}\n"
                            f"<b>5 дней:</b> {format_percent(change_5d)}\n"
                            f"<b>1 месяц:</b> {format_percent(change_1mo)}\n\n"
                            f"Акция {signal_text} за последние 5 дней."
                        ),
                        parse_mode="HTML",
                    )

                except Exception:
                    continue

        await asyncio.sleep(300)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Выберите язык / Choose language / Тілді таңдаңыз / Vyberte jazyk",
        reply_markup=language_keyboard(),
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user_name = get_user_name(message.from_user)

    await message.answer(
        f"<b>{user_name}, что умеет бот:</b>\n"
        "/list — открыть список акций\n"
        "/portfolio — показать сохраненные акции\n"
        "/analyze — выбрать акцию для анализа\n"
        "/watch — включить авто-слежение за портфелем\n"
        "/unwatch — выключить авто-слежение\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Открой список акций\n"
        "2. Выбери бумагу\n"
        "3. Добавь в портфель\n"
        "4. Изучи анализ\n"
        "5. Включи слежение",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    user_name = get_user_name(message.from_user)

    await message.answer(
        f"<b>{user_name}, список акций</b>\nВыбери бумагу:",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )
    await message.answer(
        "Нажми на нужную акцию:",
        reply_markup=stock_list_keyboard(),
    )


@dp.message(Command("portfolio"))
async def cmd_portfolio(message: types.Message):
    user_name = get_user_name(message.from_user)
    stock_ids = get_portfolio(message.from_user.id)

    if not stock_ids:
        await message.answer(
            f"💼 {user_name}, твой портфель пока пуст. Добавь акции через список.",
            parse_mode="HTML",
            reply_markup=main_keyboard,
        )
        return

    lines = [f"<b>💼 Портфель {user_name}:</b>"]
    for stock_id in stock_ids:
        stock = STOCKS_BY_ID.get(stock_id)
        if stock:
            lines.append(f"• {escape_text(stock['kase_ticker'])} — {escape_text(stock['name'])}")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )
    await message.answer(
        "Выбери бумагу из портфеля:",
        reply_markup=portfolio_keyboard(stock_ids),
    )


@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    user_name = get_user_name(message.from_user)

    await message.answer(
        f"📊 {user_name}, выбери бумагу для анализа:",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )
    await message.answer(
        "Нажми на нужную акцию:",
        reply_markup=stock_list_keyboard(),
    )


@dp.message(Command("watch"))
async def cmd_watch(message: types.Message):
    user_name = get_user_name(message.from_user)
    set_watcher(message.from_user.id, True)

    await message.answer(
        f"📡 {user_name}, слежение за портфелем включено.",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )


@dp.message(Command("unwatch"))
async def cmd_unwatch(message: types.Message):
    user_name = get_user_name(message.from_user)
    set_watcher(message.from_user.id, False)

    await message.answer(
        f"⛔ {user_name}, слежение за портфелем выключено.",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )


@dp.message(F.text == "📋 Список акций")
async def btn_list(message: types.Message):
    await cmd_list(message)


@dp.message(F.text == "💼 Мой портфель")
async def btn_portfolio(message: types.Message):
    await cmd_portfolio(message)


@dp.message(F.text == "📊 Анализировать")
async def btn_analyze(message: types.Message):
    await cmd_analyze(message)


@dp.message(F.text == "📡 Включить слежение")
async def btn_watch(message: types.Message):
    await cmd_watch(message)


@dp.message(F.text == "⛔ Выключить слежение")
async def btn_unwatch(message: types.Message):
    await cmd_unwatch(message)


@dp.message(F.text == "ℹ️ Помощь")
async def btn_help(message: types.Message):
    await cmd_help(message)


@dp.callback_query(F.data == "back_to_list")
async def back_to_list(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Нажми на нужную акцию:",
        reply_markup=stock_list_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("stock:"))
async def show_stock_card(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)

    if not stock:
        await callback.answer("Акция не найдена", show_alert=True)
        return

    in_portfolio = stock_id in get_portfolio(callback.from_user.id)
    watching = is_watching(callback.from_user.id)

    await callback.message.edit_text(
        build_stock_card(stock, in_portfolio, watching),
        parse_mode="HTML",
        reply_markup=stock_actions_keyboard(stock, in_portfolio),
    )
    await callback.answer()
    

@dp.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: types.CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id

    set_user_language(user_id, lang)

    user_name = callback.from_user.first_name

    text = (
        TEXTS["start"][lang].format(name=user_name)
        + "\n\n"
        + TEXTS["menu"][lang]
    )

    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_portfolio:"))
async def toggle_portfolio(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)

    if not stock:
        await callback.answer("Акция не найдена", show_alert=True)
        return

    portfolio = get_portfolio(callback.from_user.id)
    in_portfolio = stock_id in portfolio

    if in_portfolio:
        removed = remove_from_portfolio(callback.from_user.id, stock_id)
        msg = "Удалил из портфеля" if removed else "Не удалось удалить"
    else:
        added = add_to_portfolio(callback.from_user.id, stock_id)
        msg = "Добавил в портфель" if added else "Акция уже в портфеле"

    in_portfolio = stock_id in get_portfolio(callback.from_user.id)
    watching = is_watching(callback.from_user.id)

    await callback.message.edit_text(
        build_stock_card(stock, in_portfolio, watching),
        parse_mode="HTML",
        reply_markup=stock_actions_keyboard(stock, in_portfolio),
    )
    await callback.answer(msg)


@dp.callback_query(F.data.startswith("analyze_short:"))
async def analyze_selected_stock_short(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)

    if not stock:
        await callback.answer("Акция не найдена", show_alert=True)
        return

    user_name = get_user_name(callback.from_user)

    await callback.answer("Делаю короткий анализ...")
    await callback.message.answer(
        f"⚡ {user_name}, делаю короткий анализ по <b>{escape_text(stock['name'])}</b>...",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )

    try:
        result = await analyze_stock(stock, user_name, analysis_mode="short")
        await send_long_message(callback.message, result, reply_markup=main_keyboard)
    except Exception:
        await callback.message.answer(
            f"❌ По <b>{escape_text(stock['name'])}</b> сейчас не удалось получить котировки из Yahoo Finance. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=main_keyboard,
        )


@dp.callback_query(F.data.startswith("analyze_full:"))
async def analyze_selected_stock_full(callback: types.CallbackQuery):
    stock_id = callback.data.split(":")[1]
    stock = STOCKS_BY_ID.get(stock_id)

    if not stock:
        await callback.answer("Акция не найдена", show_alert=True)
        return

    user_name = get_user_name(callback.from_user)

    await callback.answer("Делаю подробный анализ...")
    await callback.message.answer(
        f"📘 {user_name}, делаю подробный анализ по <b>{escape_text(stock['name'])}</b>...",
        parse_mode="HTML",
        reply_markup=main_keyboard,
    )

    try:
        result = await analyze_stock(stock, user_name, analysis_mode="full")
        await send_long_message(callback.message, result, reply_markup=main_keyboard)
    except Exception:
        await callback.message.answer(
            f"❌ По <b>{escape_text(stock['name'])}</b> сейчас не удалось получить котировки из Yahoo Finance. Попробуй позже.",
            parse_mode="HTML",
            reply_markup=main_keyboard,
        )


async def main():
    init_db()
    print("=== BOT STARTED ===")
    asyncio.create_task(monitor_portfolios())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())