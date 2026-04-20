import re

# Регулярное выражение для поиска URL
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

# Паттерны для персональных данных (PII)
PII_PATTERNS = {
    "email": re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'),
    "phone": re.compile(r'(?:\+7|8)\s?\(?\d{3}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}'),
    "credit_card": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
    "url": re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
}

# Паттерн для поиска нераскрытых Unicode-последовательностей (типа \u041f)
UNICODE_ESCAPE_PATTERN = re.compile(r'\\u[0-9a-fA-F]{4}')

# Признаки "кракозябр" (типичные ошибки кодировки CP1251 -> UTF-8)
MOJIBAKE_SAMPLES = ["РїСЂРё", "09;01", "Р РµР°Р"]