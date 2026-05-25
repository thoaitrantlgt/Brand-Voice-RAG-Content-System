"""
logging.py — Centralized Logging Configuration
SRP: Module này chỉ chịu trách nhiệm setup logger cho toàn ứng dụng.
Dùng loguru để có structured log, rotation, và màu sắc đẹp hơn stdlib.
"""
import sys
from loguru import logger


def setup_logging(debug: bool = False) -> None:
    """
    Cấu hình logger toàn cục.
    Gọi 1 lần khi app khởi động trong main.py.
    """
    logger.remove()  # Xóa handler mặc định

    log_level = "DEBUG" if debug else "INFO"
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console output
    logger.add(
        sys.stderr,
        format=log_format,
        level=log_level,
        colorize=True,
    )

    # File output (rotate mỗi ngày, giữ 7 ngày)
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        encoding="utf-8",
    )

    logger.info("Logger initialized | level={}", log_level)


# Re-export logger để các module khác import từ đây
__all__ = ["logger", "setup_logging"]
