import os
import re
from datetime import datetime
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
                "content": "Ты эксперт по футбольной аналитике. Анализируй матчи на основе статистики, формы команд, личных встреч и других факторов."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
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

async def analyze_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на анализ матча"""
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
    
    prompt = f"""Проанализируй футбольный матч {team1} - {team2}, который состоится {match_date}.

Предоставь:
1. Краткий анализ текущей формы обеих команд
2. Статистику личных встреч
3. Ключевые факторы (травмы, дисквалификации, мотивация)
4. Прогноз на исход матча (победа команды 1, ничья, победа команды 2) с вероятностью
5. Прогноз на тотал голов (больше/меньше 2.5) с обоснованием

Будь конкретен и основывайся на реальных данных."""
    
    result = call_perplexity(prompt)
    
    # Форматируем ответ
    response = f"⚽ <b>Анализ матча</b>\n"
    response += f"<b>{team1} - {team2}</b>\n"
    response += f"📅 Дата: {match_date}\n\n"
    response += result
    
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
