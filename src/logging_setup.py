import logging
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)s | %(message)s"


def get_logger(name="bot"):
    Path("logs").mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler("logs/bot.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT))
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(_FMT))
        logger.addHandler(ch)

    # Propagar logs src.engine.* e src.macro.* para o mesmo ficheiro
    _attach_to_file("src.engine", "logs/bot.log")
    _attach_to_file("src.macro", "logs/bot.log")
    _attach_to_file("src.monitoring", "logs/bot.log")

    return logger


def _attach_to_file(logger_name: str, log_file: str) -> None:
    """Liga o logger de um módulo ao mesmo FileHandler do bot.log."""
    lg = logging.getLogger(logger_name)
    lg.setLevel(logging.INFO)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename.endswith("bot.log")
               for h in lg.handlers):
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT))
        lg.addHandler(fh)
        lg.propagate = False
