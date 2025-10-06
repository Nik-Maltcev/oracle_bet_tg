import os
import re
import json
from datetime import datetime, date
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
    """Команда /start"""
    await update.message.reply_text(
        "⚽ Привет! Я бот-аналитик футбольных матчей.\n\n"
        "Отправь мне матч в формате:\n"
        "команда1 - команда2 дд.мм.гг\n\n"
        "Например: ювентус - милан 07.10.25\n\n"
        "Я проанализирую матч и дам прогноз!"
    )

def load_usage():
    """Загрузка данных об использовании"""
    try:
        with open('usage.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def save_usage(data):
    """Сохранение данных об использовании"""
    with open('usage.json', 'w') as f:
        json.dump(data, f)

def can_use_today(user_id):
    """Проверка лимита на сегодня"""
    usage = load_usage()
    today = str(date.today())
    user_key = str(user_id)
    
    if user_key not in usage:
        usage[user_key] = {}
    
    if today not in usage[user_key]:
        usage[user_key] = {today: 0}
    
    return usage[user_key].get(today, 0) < 1

def increment_usage(user_id):
    """Увеличение счетчика использования"""
    usage = load_usage()
    today = str(date.today())
    user_key = str(user_id)
    
    if user_key not in usage:
        usage[user_key] = {}
    
    usage[user_key][today] = usage[user_key].get(today, 0) + 1
    save_usage(usage)

async def analyze_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на анализ матча"""
    user_id = update.effective_user.id
    
    # Проверка лимита
    if not can_use_today(user_id):
        await update.message.reply_text(
            "⛔ Вы уже использовали свой прогноз на сегодня.\n"
            "Возвращайтесь завтра!"
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
    
    # Увеличиваем счетчик
    increment_usage(user_id)
    
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_match))
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
