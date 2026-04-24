from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
        description=(
            "Postgres DSN. Должен быть задан через переменную окружения "
            "DATABASE_URL (см. .env.example). Пустая строка означает, что "
            "переменная не передана — backend упадёт на старте, не "
            "подцепляя дефолтные креды."
        ),
    )
    chroma_path: Path = Field(default=Path("/data/chroma"), alias="CHROMA_PATH")
    semantic_path: Path = Field(default=Path("/app/semantic/drivee.yaml"), alias="SEMANTIC_PATH")
    fewshots_path: Path = Field(default=Path("/app/prompts/fewshots.yaml"), alias="FEWSHOTS_PATH")

    llama_cpp_url: str = Field(default="http://host.docker.internal:8080/v1", alias="LLAMA_CPP_URL")
    llama_cpp_model: str = Field(default="qwen2.5-coder", alias="LLAMA_CPP_MODEL")
    llama_cpp_api_key: str = Field(default="sk-no-key", alias="LLAMA_CPP_API_KEY")
    llama_cpp_timeout_s: int = Field(default=120, alias="LLAMA_CPP_TIMEOUT_S")
    llama_cpp_max_tokens: int = Field(default=768, alias="LLAMA_CPP_MAX_TOKENS")
    llama_cpp_max_parallel: int = Field(
        default=1,
        alias="LLAMA_CPP_MAX_PARALLEL",
        ge=1,
        le=8,
        description=(
            "Сколько генераций кандидатов пускать параллельно. По умолчанию 1 — "
            "стандартный llama-server отдаёт 500 на конкурентные /v1/chat/completions. "
            "Поднимать до 2–4 имеет смысл только если сервер запущен с `--parallel N` "
            "и включён continuous batching."
        ),
    )

    embedding_model: str = Field(default="/models/bge-m3_en_ru", alias="EMBEDDING_MODEL")

    candidates_n: int = Field(default=3, alias="CANDIDATES_N")
    confidence_threshold: float = Field(default=0.62, alias="CONFIDENCE_THRESHOLD")

    critic_max_attempts: int = Field(
        default=3,
        alias="CRITIC_MAX_ATTEMPTS",
        ge=1,
        le=5,
        description=(
            "Максимум попыток critic_fix, когда guardrails зарезали все начальные "
            "кандидаты. 1 — single-shot (старое поведение), 3 — текущий дефолт. "
            "На каждой попытке поднимается temperature, чтобы модель не повторяла "
            "одну и ту же ошибку."
        ),
    )
    verify_empty_results: bool = Field(
        default=True,
        alias="VERIFY_EMPTY_RESULTS",
        description=(
            "Если безопасный SQL отработал, но вернул 0 строк И содержит фильтр "
            "по времени — отдаём его критику на перепроверку границ интервала. "
            "Ловит баг «на этой неделе», когда правая граница совпадает с левой. "
            "Лишний вызов LLM только на подозрительных пустых результатах."
        ),
    )

    voting_enabled: bool = Field(
        default=True,
        alias="VOTING_ENABLED",
        description=(
            "Общий тумблер голосования по результатам выполнения. Выключать "
            "имеет смысл для A/B-сравнения со старой ветвью self-consistency "
            "на уровне AST."
        ),
    )
    voting_timeout_s: float = Field(
        default=5.0,
        alias="VOTING_TIMEOUT_S",
        ge=0.5,
        le=60.0,
        description=(
            "Wall-clock лимит на ВСЁ голосование (не на одного кандидата). Он же "
            "становится `statement_timeout` для каждой Postgres-сессии — один "
            "подвисший запрос не съест весь пул."
        ),
    )
    voting_max_executions: int = Field(
        default=5,
        alias="VOTING_MAX_EXECUTIONS",
        ge=1,
        le=10,
        description="Жёсткий лимит на число кандидатов, уходящих в пул потоков.",
    )
    voting_max_parallel: int = Field(
        default=3,
        alias="VOTING_MAX_PARALLEL",
        ge=1,
        le=10,
        description="Размер пула потоков. Каждый воркер открывает свой psycopg-коннект.",
    )
    voting_abstain_consensus: float = Field(
        default=0.5,
        alias="VOTING_ABSTAIN_CONSENSUS",
        ge=0.0,
        le=1.0,
        description=(
            "Если consensus_strength НИЖЕ этого значения И лучший score в пределах "
            "`voting_abstain_score_buffer` от порога уверенности — форсим clarify "
            "(адаптивное воздержание)."
        ),
    )
    voting_abstain_score_buffer: float = Field(
        default=0.10,
        alias="VOTING_ABSTAIN_SCORE_BUFFER",
        ge=0.0,
        le=0.5,
    )
    voting_consensus_bonus: float = Field(
        default=1.05,
        alias="VOTING_CONSENSUS_BONUS",
        ge=1.0,
        le=1.5,
        description=(
            "Множитель к best.score, когда ВСЕ выполненные кандидаты сошлись "
            "(consensus_strength == 1.0). После умножения обрезается до 1.0."
        ),
    )

    value_linking_enabled: bool = Field(
        default=True,
        alias="VALUE_LINKING_ENABLED",
        description=(
            "Общий тумблер value linking: сопоставление NL-токенов с "
            "проиндексированными enum-значениями из БД, чтобы подложить в "
            "промпт канонические значения. Выключать для A/B со старой веткой."
        ),
    )
    value_linking_max_links: int = Field(
        default=8,
        alias="VALUE_LINKING_MAX_LINKS",
        ge=1,
        le=30,
        description=(
            "Лимит на число пар (token, db_value), уходящих в LLM. Больше — "
            "больше контекста, больше токенов и выше шанс, что неверный, но "
            "правдоподобный матч собьёт модель."
        ),
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    environment: str = Field(default="dev", alias="ENVIRONMENT")
    frontend_origin: str = Field(default="*", alias="FRONTEND_ORIGIN")

    api_token: str = Field(
        default="",
        alias="API_TOKEN",
        description=(
            "Общий секрет, который должен прийти в заголовке X-API-Token на "
            "каждый /api/* запрос. Пустая строка выключает авторизацию (только "
            "dev): в prod значение ОБЯЗАТЕЛЬНО, иначе API отдаёт ручки без "
            "аутентификации."
        ),
    )
    admin_token: str = Field(
        default="",
        alias="ADMIN_TOKEN",
        description=(
            "Усиленный секрет для ручек, которые меняют подключение к источнику "
            "или перезаписывают семантический слой. Если пусто — используется "
            "api_token."
        ),
    )
    allowed_roles: str = Field(
        default="business_user,analyst",
        alias="ALLOWED_ROLES",
        description="Список role-id через запятую, которые принимает API.",
    )

    eval_results_dir: str | None = Field(
        default=None,
        alias="EVAL_RESULTS_DIR",
        description=(
            "Переопределение пути к директории с результатами eval-харнесса. "
            "Если не задано — /api/eval/summary ищет eval/results/ по дереву "
            "проекта."
        ),
    )

    rate_limit_enabled: bool = Field(
        default=True,
        alias="RATE_LIMIT_ENABLED",
        description=(
            "Общий тумблер HTTP-rate-limit поверх slowapi. В тестах выключается "
            "автоматически через фикстуру в conftest.py. В dev можно вручную "
            "выключить через .env, если лимит мешает при отладке."
        ),
    )
    rate_limit_storage_uri: str = Field(
        default="memory://",
        alias="RATE_LIMIT_STORAGE_URI",
        description=(
            "Backend для хранения счётчиков. По умолчанию in-memory (годится "
            "только для одного воркера). Для мульти-воркер / мульти-инстанс "
            "деплоя укажите redis://host:6379 — иначе счётчики расходятся. "
            "Формат строки — из библиотеки `limits`."
        ),
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_prod(self) -> bool:
        return self.environment.lower() == "prod"

    @property
    def effective_admin_token(self) -> str:
        return self.admin_token or self.api_token

    @property
    def allowed_roles_set(self) -> set[str]:
        return {r.strip() for r in self.allowed_roles.split(",") if r.strip()}


settings = Settings()
