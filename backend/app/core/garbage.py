from __future__ import annotations

import re

_WORD_RE = re.compile(r"[а-яёa-z]+", re.IGNORECASE)
_VOWELS: frozenset[str] = frozenset("аеёиоуыэюяaeiouy")

_DOMAIN_HINTS: frozenset[str] = frozenset(
    {
        "отмен",
        "поезд",
        "пассажир",
        "водител",
        "клиент",
        "пользовател",
        "выручк",
        "доход",
        "чек",
        "тариф",
        "канал",
        "город",
        "сегмент",
        "рейтинг",
        "длит",
        "расст",
        "опозд",
        "завершён",
        "завершен",
        "успеш",
        "активн",
        "новый",
        "средн",
        "средни",
        "процент",
        "доля",
        "количеств",
        "число",
        "сколько",
        "покажи",
        "сравни",
        "топ",
        "группир",
        "минут",
        "час",
        "день",
        "дня",
        "дней",
        "неделя",
        "недел",
        "месяц",
        "квартал",
        "год",
        "прошл",
        "послед",
        "ближайш",
        "сегодня",
        "вчера",
        "завтра",
        "утро",
        "вечер",
        "ночь",
        "surge",
        "ETA",
        "retention",
        "cohort",
        "trip",
        "cancel",
        "fare",
        "user",
        "driver",
        "rider",
        "revenue",
        "count",
        "sum",
        "avg",
        "top",
        "compare",
        "show",
        "how",
        "what",
        "where",
        "city",
        "channel",
        "last",
        "week",
        "month",
        "day",
        "previous",
        "segment",
        "ratio",
        "percent",
    }
)


def _balanced_vowels(token: str) -> bool:
    if not token:
        return False
    v = sum(1 for c in token if c in _VOWELS)
    return 0.2 <= v / len(token) <= 0.7


def looks_like_garbage(q: str) -> bool:
    q = q.strip()
    if len(q) < 3:
        return True

    letters = sum(1 for c in q if c.isalpha())
    if letters / max(1, len(q)) < 0.5:
        return True

    tokens = [t.lower() for t in _WORD_RE.findall(q)]
    meaningful = [t for t in tokens if len(t) >= 2]
    if not meaningful:
        return True

    if not any(_balanced_vowels(t) for t in meaningful):
        return True

    q_lower = q.lower()
    return bool(not any(hint in q_lower for hint in _DOMAIN_HINTS))
