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
BOT_TOKEN = "telegramm token"
EMAIL_ACCOUNT = "emeil"
EMAIL_PASSWORD = "password application (Enable two-factor authentication App: Mail You will receive a password)"
PASSWORD = "your password for bot"

# ======== ИНИЦИАЛИЗАЦИЯ ========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния
AUTH, PHONE, COUNT, TEXT, CONFIRM = range(5)

authorized_users = set()
executor = None


# ======== ОТПРАВКА EMAIL ========
def _send_message_sync(recipient: str, text: str) -> bool:
    try:
        msg = MIMEText(text, 'plain', 'utf-8')
        msg['Subject'] = 'Сообщение от бота'
        msg['From'] = EMAIL_ACCOUNT
        msg['To'] = recipient

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False


async def send_message(recipient: str, text: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _send_message_sync, recipient, text)


# ======== ОБРАБОТЧИКИ ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "👋 Привет! Я создатель бота — your name.\n"
        "Если у вас есть вопросы или нужен пароль, напишите мне в Telegram: @your_use\n\n"
        "🤖 О боте:\n\n"
        "Этот бот предназначен для автоматической отправки нескольких email-сообщений "
        "на указанный Gmail-адрес.\n\n"
        "📌 Что он делает:\n"
        "• Отправляет заданное количество писем\n"
        "• Использует ваш текст сообщения\n"
        "• Показывает прогресс отправки\n\n"
        "📌 Для чего можно использовать:\n"
        "• Тестирование почты\n"
        "• Проверка уведомлений\n"
        "• Автоматическая отправка сообщений\n\n"
        "⚠️ Важно:\n"
        "Не злоупотребляйте — частая отправка может привести к блокировке со стороны почтовых сервисов.\n\n"
        "🔒 Введите пароль для продолжения:"
    )
    return AUTH


async def authenticate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("✅ Успешно! Введите Gmail получателя:")
        return PHONE
    await update.message.reply_text("❌ Неверный пароль:")
    return AUTH


async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    recipient = update.message.text

    if recipient.endswith("@gmail.com"):
        context.user_data['recipient'] = recipient

        await update.message.reply_text(
            "🔢 Сколько сообщений отправить? (1-10)\n\n"
            "⚠️ Важно: не злоупотребляйте отправкой сообщений."
        )

        return COUNT

    await update.message.reply_text("❌ Введите корректный Gmail:")
    return PHONE


async def get_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        count = int(update.message.text)
        if not 1 <= count <= 500:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите число 1-500:")
        return COUNT

    context.user_data['count'] = count
    await update.message.reply_text("✉️ Введите текст сообщения:")
    return TEXT


async def get_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['text'] = update.message.text

    await update.message.reply_text(
        f"Подтвердите:\n\n"
        f"📧 Email: {context.user_data['recipient']}\n"
        f"🔢 Кол-во: {context.user_data['count']}\n"
        f"✉️ Текст: {context.user_data['text']}",
        reply_markup=ReplyKeyboardMarkup([['▶️ Старт', '❌ Отмена']], resize_keyboard=True)
    )
    return CONFIRM


async def start_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    recipient = context.user_data.get('recipient')
    count = context.user_data.get('count')
    text = context.user_data.get('text')

    if not recipient or not count or not text:
        await update.message.reply_text("Ошибка. Начни заново /start")
        return ConversationHandler.END

    await update.message.reply_text("🚀 Начинаю отправку...", reply_markup=ReplyKeyboardRemove())

    success = 0
    errors = 0

    for i in range(1, count + 1):
        message = f"{text}\n\n({i}/{count})"

        if await send_message(recipient, message):
            success += 1
        else:
            errors += 1

        if i % 10 == 0 or i == count:
            await update.message.reply_text(f"📤 Отправлено: {i}/{count}")

        await asyncio.sleep(random.uniform(3, 6))  # анти-бан

    await update.message.reply_text(
    f"✅ Готово!\n"
    f"Успешно: {success}\n"
    f"Ошибок: {errors}\n"
    f"Чтобы начать заново введите команду /start."
)

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Отменено.Чтобы начать заново введите команду /start.",  reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ======== ЗАПУСК ========
def main():
    global executor

    while True:
        try:
            if executor:
                executor.shutdown(wait=False)

            executor = ThreadPoolExecutor(max_workers=2)

            app = Application.builder().token(BOT_TOKEN).build()

            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("start", start)],
                states={
                    AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, authenticate)],
                    PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
                    COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_count)],
                    TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_text)],
                    CONFIRM: [
                        MessageHandler(filters.Regex('^▶️ Старт$'), start_mailing),
                        MessageHandler(filters.Regex('^❌ Отмена$'), cancel),
                    ],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            app.add_handler(conv_handler)

            logger.info("Бот запущен")
            app.run_polling()

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
