import os
import re
import json
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, filters, ContextTypes
import requests

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

def call_perplexity(prompt: str, model: str = "deepseek-r1") -> str:
    """Вызов Perplexity API"""
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Ты профессиональный футбольный аналитик. КРИТИЧЕСКИ ВАЖНО: используй только АКТУАЛЬНЫЕ и ПРОВЕРЕННЫЕ данные из надежных источников. Проверяй факты дважды. Если данных недостаточно - укажи это явно."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        # Если deepseek-r1 не работает, пробуем sonar-pro
        if model == "deepseek-r1":
            return call_perplexity(prompt, model="sonar-pro")
        return f"Ошибка API: {str(e)}"

def parse_match_input(text: str) -> tuple:
    """Парсинг ввода пользователя формата 'команда1 - команда2 дд.мм.гг'"""
    pattern = r"(.+?)\s*-\s*(.+?)\s+(\d{2}\.\d{2}\.\d{2})"
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        team1 = match.group(1).strip()
        team2 = match.group(2).strip()
        date_str = match.group(3).strip()
        return team1, team2, date_str
    return None, None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    
    keyboard = [[InlineKeyboardButton("💰 Купить прогнозы", callback_data="buy")]]
    
    await update.message.reply_text(
        f"⚽ Привет! Я бот-аналитик футбольных матчей.\n\n"
        f"💎 Ваш баланс: {balance} прогнозов\n\n"
        f"Отправь матч в формате:\n"
        f"команда1 - команда2 дд.мм.гг\n\n"
        f"Например: ювентус - милан 07.10.25",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⭐ 3 прогноза - 100 звезд", callback_data="buy_3")],
        [InlineKeyboardButton("⭐ 15 прогнозов - 250 звезд", callback_data="buy_15")],
        [InlineKeyboardButton("🎁 10 прогнозов БЕСПЛАТНО", url="https://t.me/tribute/app?startapp=svTk")]
    ]
    
    await query.edit_message_text(
        "💰 Выберите пакет:\n\n"
        "⭐ 3 прогноза - 100 звезд\n"
        "⭐ 15 прогнозов - 250 звезд\n\n"
        "🎁 Или получите 10 прогнозов БЕСПЛАТНО\n"
        "при покупке подписки на премиум канал!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def process_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    packages = {
        "buy_3": (3, 100, "3 прогноза"),
        "buy_15": (15, 250, "15 прогнозов")
    }
    
    if query.data not in packages:
        return
    
    predictions, stars, title = packages[query.data]
    
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=f"Покупка {predictions} прогнозов на футбольные матчи",
        payload=f"{predictions}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=stars)]
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    predictions = int(update.message.successful_payment.invoice_payload)
    
    add_balance(user_id, predictions)
    balance = get_balance(user_id)
    
    await update.message.reply_text(
        f"✅ Оплата прошла успешно!\n\n"
        f"💎 Добавлено: {predictions} прогнозов\n"
        f"💎 Ваш баланс: {balance} прогнозов"
    )

def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        return {"usage": {}, "balance": {}}

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f)

def get_balance(user_id):
    data = load_data()
    return data["balance"].get(str(user_id), 0)

def add_balance(user_id, amount):
    data = load_data()
    user_key = str(user_id)
    data["balance"][user_key] = data["balance"].get(user_key, 0) + amount
    save_data(data)

def can_use(user_id):
    return get_balance(user_id) > 0

def use_prediction(user_id):
    data = load_data()
    user_key = str(user_id)
    if data["balance"].get(user_key, 0) > 0:
        data["balance"][user_key] -= 1
        save_data(data)
        return True
    return False

async def analyze_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на анализ матча"""
    user_id = update.effective_user.id
    
    if not can_use(user_id):
        keyboard = [[InlineKeyboardButton("💰 Купить прогнозы", callback_data="buy")]]
        await update.message.reply_text(
            "⛔ У вас закончились прогнозы!\n\n"
            "Купите пакет прогнозов или получите 10 бесплатно\n"
            "при покупке подписки на премиум канал.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    user_input = update.message.text
    team1, team2, match_date = parse_match_input(user_input)
    
    if not team1 or not team2 or not match_date:
        await update.message.reply_text(
            "❌ Неверный формат. Используй:\n"
            "команда1 - команда2 дд.мм.гг\n\n"
            "Пример: ювентус - милан 07.10.25"
        )
        return
    
    await update.message.reply_text("⏳ Анализирую матч, подожди...")
    
    if not use_prediction(user_id):
        await update.message.reply_text("❌ Ошибка списания прогноза")
        return
    
    prompt = f"""Проанализируй матч {team1} vs {team2} на дату {match_date}.

ОБЯЗАТЕЛЬНО используй ТОЛЬКО актуальные данные из проверенных источников (официальные сайты лиг, Transfermarkt, ESPN, BBC Sport).

Проведи глубокий анализ:

1. ФОРМА КОМАНД (последние 5-10 матчей):
   - {team1}: точные результаты с датами и счетом
   - {team2}: точные результаты с датами и счетом
   - Укажи турнир каждого матча

2. ЛИЧНЫЕ ВСТРЕЧИ (последние 5 матчей H2H):
   - Дата, счет, турнир
   - Статистика голов, владения

3. ТЕКУЩЕЕ ПОЛОЖЕНИЕ:
   - Место в турнирной таблице
   - Очки, разница мячей
   - Домашняя/выездная статистика

4. КЛЮЧЕВЫЕ ФАКТОРЫ:
   - Травмы и дисквалификации (с именами игроков)
   - Мотивация (борьба за место, еврокубки, вылет)
   - Тактика и стиль игры

5. ПРОГНОЗ:
   - Исход (1X2) с вероятностью в %
   - Тотал (больше/меньше 2.5) с вероятностью
   - Обоснование каждого прогноза

ЕСЛИ данных недостаточно или они устарели - ОБЯЗАТЕЛЬНО укажи это!"""
    
    result = call_perplexity(prompt)
    
    # Форматируем ответ (убираем markdown символы из результата)
    clean_result = result.replace('**', '').replace('*', '').replace('###', '').replace('##', '').replace('#', '')
    
    # Преобразуем таблицы в читаемый формат
    lines = clean_result.split('\n')
    formatted_lines = []
    for line in lines:
        if '|' in line and not line.strip().startswith('|---'):
            # Убираем символы таблицы и форматируем
            clean_line = line.replace('|', ' ').strip()
            if clean_line:
                formatted_lines.append(clean_line)
        elif not line.strip().startswith('|---'):
            formatted_lines.append(line)
    
    clean_result = '\n'.join(formatted_lines)
    
    response = f"⚽ <b>Анализ матча</b>\n"
    response += f"<b>{team1} - {team2}</b>\n"
    response += f"📅 Дата: {match_date}\n\n"
    response += clean_result
    
    await update.message.reply_text(response, parse_mode="HTML")

def main():
    """Запуск бота"""
    if not PERPLEXITY_API_KEY or not TELEGRAM_BOT_TOKEN:
        print("❌ Установите переменные окружения PERPLEXITY_API_KEY и TELEGRAM_BOT_TOKEN")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buy_menu, pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(process_buy, pattern="^buy_"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_match))
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
