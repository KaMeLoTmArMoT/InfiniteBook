import logging
import sys


def setup_logger(name: str = "InfiniteBook", log_file: str = "app_debug.log"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent propagation to root logger (avoid double logs with uvicorn)
    logger.propagate = False

    # Clear existing handlers if any (for reload mode)
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File Handler (DEBUG - everything)
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console Handler (INFO - clean output)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# Global instance to import elsewhere
log = setup_logger()
