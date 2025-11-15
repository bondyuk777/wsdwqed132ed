import os
import re
import logging
import socket
import struct
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('server_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
SERVER_IP = 'Ваш ип' #Сюда вписать ип адрес пример: 00.00.00.00
SERVER_PORT = 27015 #Сюда вписать ваш порт, пример 27015
UPDATE_INTERVAL = 3000 #интервал автоотправки сообщения в ваш канал

class SourceServerQuery:
    last_response = None
    ENCODINGS = ['utf-8', 'cp1251', 'iso-8859-5', 'cp866', 'koi8-r', 'latin1']
    HEADER = b'\xFF\xFF\xFF\xFF'

    @staticmethod
    def remove_color_codes(name):
        return re.sub(r'\^\d', '', name).strip() if name else ''

    @staticmethod
    def decode_string(data):
        end = data.find(b'\x00')
        if end == -1:
            return "", data
        raw_bytes = data[:end]
        remaining = data[end+1:]
        for encoding in SourceServerQuery.ENCODINGS:
            try:
                decoded = raw_bytes.decode(encoding, errors='strict').strip()
                return decoded, remaining
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode('utf-8', errors='replace').strip(), remaining

    @staticmethod
    def get_info():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(5)
                payload = SourceServerQuery.HEADER + b'T' + b'Source Engine Query\x00'
                sock.sendto(payload, (SERVER_IP, SERVER_PORT))
                data = sock.recv(4096)

                if data[4] == 0x41:
                    challenge = struct.unpack('<l', data[5:9])[0]
                    payload = SourceServerQuery.HEADER + b'T' + b'Source Engine Query\x00' + struct.pack('<l', challenge)
                    sock.sendto(payload, (SERVER_IP, SERVER_PORT))
                    data = sock.recv(4096)

                if data[4] != 0x49:
                    return None

                data = data[6:]
                info = {}
                info['name'], data = SourceServerQuery.decode_string(data)
                info['map'], data = SourceServerQuery.decode_string(data)
                data = data[16:]
                info['version'], data = SourceServerQuery.decode_string(data)
                
                return {
                    'name': SourceServerQuery.remove_color_codes(info['name']),
                    'map': SourceServerQuery.remove_color_codes(info['map']),
                    'players': data[0] if len(data) >= 2 else 0,
                    'max_players': data[1] if len(data) >= 2 else 0
                }

        except Exception as e:
            logger.error(f"Ошибка запроса информации: {str(e)}")
            return None

    @staticmethod
    def get_players():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(5)
                payload = SourceServerQuery.HEADER + b'U' + b'\xFF\xFF\xFF\xFF'
                sock.sendto(payload, (SERVER_IP, SERVER_PORT))
                data = sock.recv(4096)

                if data[4] == 0x41:
                    challenge = struct.unpack('<l', data[5:9])[0]
                    payload = SourceServerQuery.HEADER + b'U' + struct.pack('<l', challenge)
                    sock.sendto(payload, (SERVER_IP, SERVER_PORT))
                    data = sock.recv(4096)

                if data[4] != 0x44:
                    return None

                players = []
                player_count = data[5]
                data = data[6:]

                for _ in range(player_count):
                    try:
                        data = data[1:]
                        name, data = SourceServerQuery.decode_string(data)
                        data = data[8:]
                        clean_name = SourceServerQuery.remove_color_codes(name)
                        if clean_name and clean_name != '.':
                            players.append(clean_name)
                    except Exception as e:
                        logger.error(f"Ошибка парсинга игрока: {str(e)}")
                        continue

                return players

        except Exception as e:
            logger.error(f"Ошибка запроса игроков: {str(e)}")
            return None

def generate_message(check_changes=True):
    try:
        current_data = (SourceServerQuery.get_info(), SourceServerQuery.get_players())
        
        if check_changes and current_data == SourceServerQuery.last_response:
            return None

        SourceServerQuery.last_response = current_data
        info, players = current_data

        if not info or not players:
            return "❌ Сервер не отвечает"

        message = [
            f"🔹 <b>{info['name']}</b>",
            f"🗺 Карта: <code>{info['map']}</code>",
            f"👥 Онлайн: <b>{len(players)}/32</b>",
            "\n📊 Игроки:"
        ]

        if players:
            message += [f"👤 {name}" for name in players]
        else:
            message.append("Сейчас никто не играет")

        return "\n".join(message)

    except Exception as e:
        logger.error(f"Ошибка генерации сообщения: {str(e)}")
        return "⚠️ Ошибка получения данных"

def send_update(context: CallbackContext):
    try:
        message = generate_message(check_changes=True)
        if message:
            context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=message,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка отправки: {str(e)}")

def handle_server_cmd(update: Update, context: CallbackContext):
    try:
        info = SourceServerQuery.get_info()
        players = SourceServerQuery.get_players()
        
        if not info or not players:
            update.message.reply_text("❌ Сервер не отвечает", parse_mode='HTML')
            return

        message = [
            f"🔹 <b>{info['name']}</b>",
            f"🗺 Карта: <code>{info['map']}</code>",
            f"👥 Онлайн: <b>{len(players)}/32</b>",
            "\n📊 Игроки:"
        ]

        if players:
            message += [f"👤 {name}" for name in players]
        else:
            message.append("Сейчас никто не играет")

        update.message.reply_text(
            text="\n".join(message),
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Ошибка команды: {str(e)}")
        update.message.reply_text("⚠️ Ошибка при получении данных", parse_mode='HTML')

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🤖 Бот мониторинга игрового сервера\n"
        "Используйте команду !сервер для проверки текущего статуса",
        parse_mode='HTML'
    )

def main():
    try:
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher

        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(MessageHandler(
            Filters.text & ~Filters.command & Filters.regex(r'^!сервер'),
            handle_server_cmd
        ))

        updater.job_queue.run_repeating(
            send_update,
            interval=UPDATE_INTERVAL,
            first=0
        )

        logger.info("Бот успешно запущен")
        updater.start_polling()
        updater.idle()

    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}")
        raise

if __name__ == '__main__':
    main()
