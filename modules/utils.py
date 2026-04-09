import logging


from modules.telegram_logger import TelegramLogHandler


def setup_logging():
    logger = logging.getLogger("InstagramAuto")
    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S")
    )

    telegram_handler = TelegramLogHandler()
    telegram_handler.setFormatter(
        logging.Formatter("[Instagram][%(levelname)s] %(message)s")
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(telegram_handler)

    logger.handlers.clear()
    logger.propagate = True
    return logger
