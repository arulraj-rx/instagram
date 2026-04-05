import logging


def setup_logging():
    logger = logging.getLogger("InstagramAuto")
    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(formatter)

    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger
