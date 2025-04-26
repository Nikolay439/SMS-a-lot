import logging
import smtplib
from email.mime.text import MIMEText
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from telegram.error import Conflict

# ======== НАСТРОЙКИ ========
BOT_TOKEN = "7590796088:AAFeSBZO3RImkrokG51G8RJbr8WY-3ALR4A"
EMAIL_ACCOUNT = "saurtuntuntuntun43@gmail.com"
EMAIL_PASSWORD = "lgrb fwrf uayt xzoh"
PASSWORD = "2010"

# ======== ИНИЦИАЛИЗАЦИЯ ========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные
AUTH, PHONE, COUNT, CONFIRM = range(4)
authorized_users = set()
executor = None  # Пул потоков

# ======== ОТПРАВКА СООБЩЕНИЯ ========
def _send_message_sync(recipient: str, text: str) -> bool:
    try:
        msg = MIMEText(text, 'plain', 'utf-8')
        msg['Subject'] = ''
        msg['From'] = EMAIL_ACCOUNT
        msg['To'] = recipient

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {str(e)}")
        return False

async def send_message(recipient: str, text: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _send_message_sync, recipient, text)

# ======== ОБРАБОТЧИКИ ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🔒 Введите пароль:")
    return AUTH

async def authenticate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("✅ Авторизация успешна! Введите ваш Gmail-адрес:")
        return PHONE
    await update.message.reply_text("❌ Неверный пароль! Попробуйте снова:")
    return AUTH

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    recipient = update.message.text
    if recipient.endswith('@gmail.com'):
        context.user_data['recipient'] = recipient
        await update.message.reply_text("🔢 Введите количество сообщений (1-500):")
        return COUNT
    await update.message.reply_text("❌ Введите корректный Gmail-адрес:")
    return PHONE

async def get_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        count = int(update.message.text)
        if not 1 <= count <= 500:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите число от 1 до 500:")
        return COUNT

    context.user_data['count'] = count
    await update.message.reply_text(
        f"Подтвердите:\nEmail: {context.user_data['recipient']}\nКол-во сообщений: {count}",
        reply_markup=ReplyKeyboardMarkup([['▶️ Старт', '❌ Отмена']], resize_keyboard=True)
    )
    return CONFIRM

async def start_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    recipient = context.user_data.get('recipient')
    count = context.user_data.get('count')

    if not recipient or not count:
        await update.message.reply_text("Ошибка данных. Начните заново /start", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    await update.message.reply_text(
        f"🚀 Начинаю рассылку {count} сообщений...",
        reply_markup=ReplyKeyboardRemove()
    )

    success = errors = 0
    for i in range(1, count + 1):
        if await send_message(recipient, f"Сообщение {i}/{count} от бота"):
            success += 1
        else:
            errors += 1
        if i % 10 == 0 or i == count:
            await update.message.reply_text(f"📤 Отправлено: {i}/{count}")
        await asyncio.sleep(2)

    await update.message.reply_text(f"✅ Готово! Успешно: {success}, Ошибок: {errors}")

    # Очистить все данные
    context.user_data.clear()
    authorized_users.clear()

    # Перекинуть пользователя на авторизацию
    await update.message.reply_text("🔁 Перезапуск бота.\n\n🔒 Введите пароль:")
    return AUTH

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ======== ОБРАБОТКА ОШИБОК И ПЕРЕЗАПУСК БОТА ========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ловит ошибки в ходе работы бота, в том числе если переписка была удалена."""
    if isinstance(context.error, Conflict):
        logger.error("Переписка с ботом была удалена или пользователь заблокировал бота.")
        await update.message.reply_text("Переписка была удалена, перезапускаю бота...")
        # Перезапуск бота
        await update.message.reply_text("🔄 Перезапуск...\n\n🔒 Введите пароль:")
        return AUTH

# ======== ЗАПУСК ========
def main():
    global executor
    while True:
        try:
            authorized_users.clear()
            if executor:
                executor.shutdown(wait=False)
            executor = ThreadPoolExecutor(max_workers=1)

            app = Application.builder().token(BOT_TOKEN).build()

            # Обработчик ошибок
            app.add_error_handler(error_handler)

            conv_handler = ConversationHandler(
                entry_points=[CommandHandler('start', start)],
                states={
                    AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, authenticate)],
                    PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
                    COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_count)],
                    CONFIRM: [
                        MessageHandler(filters.Regex('^▶️ Старт$'), start_mailing),
                        MessageHandler(filters.Regex('^❌ Отмена$'), cancel)
                    ]
                },
                fallbacks=[CommandHandler('cancel', cancel)]
            )

            app.add_handler(conv_handler)

            logger.info("Бот запущен")
            app.run_polling()

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()


