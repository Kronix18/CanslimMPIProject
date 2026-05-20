import logging
import sys

def get_rank_logger(module_name: str):
    """Configures a logger that includes the MPI rank if available."""
    logger = logging.getLogger(module_name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
