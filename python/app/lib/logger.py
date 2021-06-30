import logging


def get_logger(app_name, logpath='/tmp/proc_pool.log', level='debug'):

    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR
    }

    logger = logging.getLogger(app_name)
    logger.setLevel(level_map.get(level))
    fh = logging.FileHandler(logpath)
    fh.setLevel(level_map.get(level))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def stream_logger(app_name, logpath='/tmp/proc_pool.log', level='debug'):

    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR
    }

    logger = logging.getLogger(app_name)
    logger.setLevel(level_map.get(level))
    sh = logging.StreamHandler()
    sh.setLevel(level_map.get(level))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger
