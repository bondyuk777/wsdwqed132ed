import os
import logging
import time
import urllib.request
from urllib.error import URLError, HTTPError

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)
from telegram.error import TimedOut
from dotenv import load_dotenv

# ===== ЛОГИРОВАНИЕ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('server_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== НАСТРОЙКИ ОКРУЖЕНИЯ =====
load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# URL, который мониторим (можно сменить в боте)
SERVER_URL = "https://adadadadad-97sj.onrender.com/"

# URL самого бота / сервиса на Render, чтобы он пинговал СЕБЯ
# Пример: SELF_URL=https://adadadadad-97sj.onrender.com/
SELF_URL = os.getenv('SELF_URL')

# интервал автоотправки статуса в канал (в секундах)
UPDATE_INTERVAL = 60  # 1 минута

# состояния для ConversationHandler
SET_SITE = 1


def check_site(url: str):
    """Делаем HTTP-запрос к сайту и возвращаем статус + время отклика."""
    try:
        start = time.time()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "ok": True,
                "status": status_code,
                "elapsed": elapsed_ms,
            }
    except HTTPError as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "ok": False,
            "status": e.code,
            "elapsed": elapsed_ms,
            "error": f"HTTPError: {e.code}"
        }
    except URLError as e:
        return {
            "ok": False,
            "status": None,
            "elapsed": None,
            "error": f"URLError: {e.reason}"
        }
    except Exception as e:
        return {
            "ok": False,
            "status": None,
            "elapsed": None,
            "error": f"Exception: {e}"
        }


def generate_message() -> str:
    """Формируем текст для канала/чата по текущему SERVER_URL."""
    result = check_site(SERVER_URL)

    if not result["ok"] and result["status"] is None:
        # Сайт вообще не открылся
        return (
            f"❌ Сайт недоступен\n"
            f"🌐 URL: <code>{SERVER_URL}</code>\n"
            f"⚠️ Ошибка: <code>{result.get('error', 'неизвестно')}</code>"
        )

    status = result["status"]
    elapsed = result["elapsed"]

    if result["ok"]:
        emoji = "✅"
        status_text = "OK"
    else:
        emoji = "⚠️"
        status_text = result.get("error", "Ошибка")

    return (
        f"{emoji} Статус сайта\n"
        f"🌐 URL: <code>{SERVER_URL}</code>\n"
        f"📡 HTTP статус: <b>{status}</b>\n"
        f"⏱ Задержка: <b>{elapsed} мс</b>\n"
        f"ℹ️ {status_text}"
    )


def send_update(context: CallbackContext):
    """Периодическая отправка статуса в канал (каждую минуту)."""
    try:
        message = generate_message()
        logger.info(f"Пинг {SERVER_URL} → отправка в канал")
        context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")


def ping_self(context: CallbackContext):
    """Пинг самого себя (SELF_URL) каждую минуту — только в лог, без Телеги."""
    if not SELF_URL:
        return  # если не задан SELF_URL, просто ничего не делаем
    try:
        result = check_site(SELF_URL)
        if result["ok"]:
            logger.info(
                f"[SELF PING] {SELF_URL} OK, "
                f"status={result['status']}, {result['elapsed']} ms"
            )
        else:
            logger.warning(
                f"[SELF PING] {SELF_URL} FAIL, "
                f"status={result.get('status')}, error={result.get('error')}"
            )
    except Exception as e:
        logger.error(f"[SELF PING] Ошибка при пинге SELF_URL: {e}")


def show_status(update: Update, context: CallbackContext):
    """Показать статус сайта (по кнопке)."""
    try:
        message = generate_message()
        update.message.reply_text(
            text=message,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка показа статуса: {e}")
        update.message.reply_text("⚠️ Ошибка при получении статуса", parse_mode='HTML')


def start(update: Update, context: CallbackContext):
    """Старт: показываем кнопки."""
    keyboard = [
        [KeyboardButton("📊 Статус сайта")],
        [KeyboardButton("⚙️ Сменить сайт")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        "🤖 Бот мониторинга сайта\n"
        "Выбери действие на кнопках ниже:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


def change_site_start(update: Update, context: CallbackContext):
    """Попросить пользователя прислать новый URL."""
    update.message.reply_text(
        "Отправь ссылку на сайт, который нужно мониторить.\n"
        "Например: <code>https://adadadadad-97sj.onrender.com/</code>",
        parse_mode='HTML'
    )
    return SET_SITE


def set_site_value(update: Update, context: CallbackContext):
    """Пользователь прислал URL — сохраняем его в память."""
    global SERVER_URL
    text = update.message.text.strip()

    # Простейшая проверка
    if not (text.startswith("http://") or text.startswith("https://")):
        update.message.reply_text(
            "⚠️ Неверный формат URL.\nПример: <code>https://example.com/</code>",
            parse_mode='HTML'
        )
        return SET_SITE

    SERVER_URL = text
    logger.info(f"Установлен новый URL для мониторинга: {SERVER_URL}")

    update.message.reply_text(
        f"✅ Сайт обновлён:\n<code>{SERVER_URL}</code>",
        parse_mode='HTML'
    )

    # Покажем снова меню
    start(update, context)
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Ок, отменено.", parse_mode='HTML')
    start(update, context)
    return ConversationHandler.END


def main():
    if not TOKEN:
        logger.critical(
            "Переменная окружения TELEGRAM_BOT_TOKEN не задана. "
            "Укажи токен бота в настройках Render (Environment / Env Vars)."
        )
        return

    if not CHANNEL_ID:
        logger.critical(
            "Переменная окружения TELEGRAM_CHANNEL_ID не задана. "
            "Укажи ID канала/чата в настройках Render (Environment / Env Vars)."
        )
        return

    if not SELF_URL:
        logger.warning(
            "SELF_URL не задан. Сам себе бот пинговать не будет. "
            "Если хочешь self-ping — добавь SELF_URL в Env Vars."
        )

    request_kwargs = {
        'read_timeout': 30,
        'connect_timeout': 10,
    }

    while True:
        try:
            updater = Updater(
                TOKEN,
                use_context=True,
                request_kwargs=request_kwargs
            )

            dp = updater.dispatcher

            # /start
            dp.add_handler(CommandHandler("start", start))

            # Кнопка "📊 Статус сайта"
            dp.add_handler(MessageHandler(
                Filters.regex(r'^📊 Статус сайта$'),
                show_status
            ))

            # Диалог смены сайта
            conv_handler = ConversationHandler(
                entry_points=[MessageHandler(
                    Filters.regex(r'^⚙️ Сменить сайт$'),
                    change_site_start
                )],
                states={
                    SET_SITE: [
                        MessageHandler(Filters.text & ~Filters.command, set_site_value)
                    ],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )
            dp.add_handler(conv_handler)

            # Старый текстовый триггер по желанию
            dp.add_handler(MessageHandler(
                Filters.text & ~Filters.command & Filters.regex(r'^!сайт'),
                show_status
            ))

            # Периодический статус в канал (каждую минуту)
            updater.job_queue.run_repeating(
                send_update,
                interval=UPDATE_INTERVAL,
                first=0
            )

            # Периодический self-ping, тоже каждую минуту
            if SELF_URL:
                updater.job_queue.run_repeating(
                    ping_self,
                    interval=60,
                    first=0
                )

            logger.info(
                f"Бот запущен. Мониторим: {SERVER_URL}, "
                f"self-ping: {SELF_URL if SELF_URL else 'выключен'}, "
                f"интервал: {UPDATE_INTERVAL} сек"
            )
            updater.start_polling()
            updater.idle()
            break

        except TimedOut as e:
            logger.warning(f"Telegram TimedOut: {e}. Повторный запуск через 5 секунд...")
            time.sleep(5)

        except Exception as e:
            logger.critical(f"Критическая ошибка: {e}", exc_info=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
