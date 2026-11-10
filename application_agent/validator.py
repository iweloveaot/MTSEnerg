import re
from typing import Optional


def normalize_phone(
    phone: Optional[str],
) -> Optional[str]:
    """
    Нормализует российский номер телефона.

    Примеры:

    8 (999) 123-45-67
        ->
    +79991234567

    +7 999 123 45 67
        ->
    +79991234567

    Если номер некорректный,
    возвращает None.
    """

    if not phone:
        return None

    digits = re.sub(
        r"\D",
        "",
        phone,
    )

    # Например:
    # 89991234567
    if (
        len(digits) == 11
        and digits.startswith("8")
    ):
        digits = "7" + digits[1:]

    # Например:
    # 79991234567
    if (
        len(digits) == 11
        and digits.startswith("7")
    ):
        return "+" + digits

    # Например:
    # 9991234567
    if len(digits) == 10:
        return "+7" + digits

    return None


def is_valid_phone(
    phone: Optional[str],
) -> bool:
    """
    Проверяет, можно ли распознать
    строку как корректный номер.
    """

    return normalize_phone(phone) is not None