import os
import logging
import requests


class TelegramLogHandler(logging.Handler):
    """Sends logs to Telegram Admin Chat"""

    def __init__(self):
        super().__init__()
        self.token = os.getenv("TELEGRAM_LOG_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_LOG_CHAT_ID")

    def emit(self, record):
        log_entry = self.format(record)
        if record.levelno >= logging.INFO:
            self.send_message(log_entry)

    def send_message(self, text):
        if not self.token or not self.chat_id:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            requests.post(url, data={
                "chat_id": self.chat_id,
                "text": text[:4000],
            }, timeout=30)
        except Exception:
            pass


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    c_handler = logging.StreamHandler()
    c_format = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)

    if os.getenv("TELEGRAM_LOG_BOT_TOKEN") and os.getenv("TELEGRAM_LOG_CHAT_ID"):
        t_handler = TelegramLogHandler()
        t_format = logging.Formatter('[%(levelname)s] %(message)s')
        t_handler.setFormatter(t_format)
        logger.addHandler(t_handler)

    logger.info("Logger initialized")
    return logger
