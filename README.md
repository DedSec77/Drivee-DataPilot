# Drivee DataPilot

Self-service аналитика на естественном языке для ride-hailing данных.
Пишешь вопрос по-русски — получаешь SQL, таблицу и график. Всё работает
локально, никаких обращений к внешним API.

## Стек

- **Backend** — FastAPI, PostgreSQL 16, ChromaDB, sentence-transformers, sqlglot
- **Frontend** — React 18, Vite, Tailwind, shadcn/ui, Recharts
- **LLM** — любой OpenAI-совместимый `/v1` (llama.cpp, Ollama, vLLM, TGI)

## Быстрый старт

Что нужно:

- Docker Desktop (на Windows — с WSL2)
- 8 ГБ RAM
- Локальный LLM на `http://localhost:8080/v1` — см. раздел «LLM» ниже

```bash
git clone <repo-url> drivee-datapilot
cd drivee-datapilot
./start.sh
```

Скрипт сам:

1. сгенерирует случайный `POSTGRES_PASSWORD`, если нет `.env`;
2. определит адрес LLM исходя из сетевого gateway;
3. поднимет Postgres + backend + frontend через `docker compose`;
4. засеет `fct_trips` десятью тысячами синтетических поездок (идемпотентно).

Через ~30 секунд открывается <http://localhost:5173>.

## LLM

Backend общается с любым endpoint-ом, который понимает OpenAI `/v1`. По
умолчанию — `http://host.docker.internal:8080/v1` (работает на Docker
Desktop из коробки). Переопределяется через `LLAMA_CPP_URL` в `.env`.

Рекомендуемый локальный вариант — `llama.cpp`:

```bash
huggingface-cli download \
    matrixportal/Qwen2.5-Coder-7B-Instruct-Q4_K_M-GGUF \
    qwen2.5-coder-7b-instruct-q4_k_m.gguf \
    --local-dir ../model

cd ../model
git clone https://huggingface.co/BorisTM/bge-m3_en_ru
cd bge-m3_en_ru && git lfs pull

./llama-server -m qwen2.5-coder-7b-instruct-q4_k_m.gguf \
    -c 8192 --port 8080 --host 0.0.0.0 --chat-template chatml
```

Можно заменить на Ollama, vLLM, TGI или hosted endpoint — важно только,
чтобы был `/v1/chat/completions`.

## Что умеет

| # | Запрос | Что происходит |
|---|---|---|
| 1 | «Сколько отмен по городам за прошлую неделю?» | bar chart, SQL, применённые guardrails, уверенность |
| 2 | «Покажи продажи» | clarify-диалог с чипами (выручка / поездки / AOV / MAU) |
| 3 | «Сравни конверсию по каналам за последние 30 дней» | line chart по каналам |
| 4 | «А за прошлый месяц?» (после №3) | follow-up резолвится из истории |
| 5 | Save → Approve | шаблон попадает в few-shot; похожие вопросы идут точнее |
| 6 | «Запустить сейчас» в Schedules | CSV кладётся в `/files/scheduled/` |
| 7 | «Покажи телефоны пассажиров Москвы» | `PII_COLUMN` блок + RBAC + маска на фронте |
| 8 | `DROP TABLE fct_trips` | `NON_SELECT` блок (AST ловит до Postgres) |

## Метрики

Последний прогон `python -m eval.run_eval` на текущем gold-сете
(30 русскоязычных бизнес-вопросов + 4 security-теста, итого 34 кейса):

| Метрика | Значение |
|---|---|
| Кейсов всего | 34 |
| Ответили (`answered`) | 25 |
| Guard-блоки сработали (`guard_pass`) | 4 / 4 |
| **EX** — execution row equality | **0.24** |
| **CM** — component match | **0.94** |
| EM — exact SQL match | 0.16 |
| VES — cost-aware EX | 0.21 |
| Средняя уверенность | 0.85 |
| Средняя латентность | 6.1 сек |

EX — главная метрика: бизнесу важен правильный ответ, а не побайтовое
совпадение SQL с gold. Это тот же приоритет, что и в BIRD benchmark.
CM 0.94 при EX 0.24 означает, что структура SQL почти всегда верна —
ошибаемся на значениях и фильтрах (value-linker / where-clause),
а не на выборе таблиц и агрегаций.

Главные классы ошибок из `eval/results/report.json`:

| Класс | Кол-во |
|---|---|
| `value_mismatch` | 6 |
| `limit_mismatch` | 6 |
| `missing_status_filter` | 5 |
| `clarify_returned` | 5 |
| `row_count_mismatch` | 1 |
| `order_by_mismatch` | 1 |

Таксономия нужна, чтобы понимать, куда инвестировать следующий спринт —
расширение gold-сета до 100+ кейсов и usage-калибровка запланированы.

## Экономия

Грубая оценка для команды из 5 аналитиков, средняя ставка 250 000 ₽/мес,
60 % рутины покрываются self-service:

| До | После |
|---|---|
| 2 дня на типовой запрос | 5–10 секунд |
| 0 % вопросов без аналитика | ~25 % (EX) сейчас, цель 70 %+ |
| 500 000 запросов/мес через GPT-4o ≈ 30 000 $ | 0 $ (llama.cpp локально) |
| Утечка PII в облачный LLM | весь pipeline в периметре |

## Архитектура

Ядро pipeline:

```
RU/EN вопрос
    ↓
FastAPI /api/ask
    ↓
1. retrieval     bge-m3 по семантическому YAML и few-shot, off-topic гейт
2. value linking NL-токены в канонические значения БД (BRIDGE-style)
3. generate      LLM × N кандидатов (variable temperature)
4. guard         sqlglot AST: PII, allowlist, EXPLAIN cost, joins
5. selector      weighted score (consensus + schema + cost + simplicity)
6. critic        repair-pass если лучший кандидат упал
7. voting        запускаем выживших, голосуем по канонизированному результату
8. clarify       низкая уверенность → диалог с чипами
9. execute       безопасный SQL в Postgres
10. render       таблица + график + «как я понял» + audit log
```

## Раскладка проекта

```
drivee-datapilot/
├── start.sh                 запуск в одну команду
├── docker-compose.yml       postgres + backend + frontend
├── .env.example             шаблон конфигурации
├── docs/
│   └── architecture.svg
├── backend/
│   ├── app/
│   │   ├── api/             FastAPI роутеры
│   │   ├── core/            NL→SQL pipeline
│   │   └── db/              ORM, сессии, seed
│   ├── semantic/drivee.yaml бизнес-глоссарий
│   ├── prompts/             system prompt + few-shot
│   ├── eval/                offline gold set
│   └── tests/               pytest
├── frontend/                React + Vite + Tailwind
└── scripts/
    └── init.sql             bootstrap Postgres
```

## Eval

Offline-проверка качества на curated gold-сете:

```bash
docker compose exec backend python -m eval.run_eval
docker compose exec backend python -m eval.run_eval --only q01,q06,q21
```

- 30 русскоязычных бизнес-вопросов + 4 security-проверки
- Метрики: EM (exact match), CM (component match), EX (execution row
  equality), VES (cost-aware EX)
- Отчёт: `eval/results/report.md` и `report.json` — тот же самый файл
  UI показывает во вкладке **Анализ → Оценка качества**

## Тесты

```bash
docker compose exec backend pytest tests/ -v
```

Покрывают AST-guardrails (DROP/DELETE/UPDATE-блоки, unknown table, deny
list, PII-колонки, требование фильтра по времени, лимит join-ов,
разрешение CTE-алиасов, comment injection) и слой интерпретации.

## Почему локально

| Что волнует | Почему не внешний LLM |
|---|---|
| **PII** | Телефоны, email, платежи. Внешний LLM в pipeline — неприемлемый риск. |
| **Доступность** | OpenAI, Anthropic, OpenRouter из российского периметра работают нестабильно. llama.cpp работает air-gapped. |
| **Стоимость** | 500 тыс. запросов в месяц через GPT-4o ≈ 30 тыс. долларов. Одна RTX 4090 + Qwen2.5-Coder-7B тянет ту же нагрузку бесплатно. |
| **Портируемость** | Работает с любым OpenAI-совместимым endpoint. Swap llama-server → vLLM / Ollama / TGI без правки кода. |

## Полезные команды

```bash
docker compose ps                                  # статус контейнеров
docker compose logs -f backend                     # логи бэкенда
docker compose down                                # остановить (тома сохраняются)
docker compose down -v                             # остановить + стереть все данные
docker compose restart backend                     # перезапустить только backend

curl -X POST -H 'Content-Type: application/json' \
     -d '{"logs":true}' http://localhost:8000/api/admin/reset
```

Сбросить отдельные таблицы можно и через UI: **Настройки → Данные**.

## Что-то не работает

| Симптом | Что делать |
|---|---|
| `password authentication failed for user "drivee"` | Старый volume с другим паролем. `docker compose down -v && ./start.sh`. |
| `NetworkError` в браузере | Backend ещё прогревается (bge-m3 грузится один раз при старте). Дождаться `Application startup complete` в `docker compose logs -f backend`. |
| `connection refused` к LLM | llama-server не запущен на `:8080`. Поднять (см. раздел «LLM») и повторить. |
| `[prewarm] value linker skipped` | bge-m3 не прокачался через git-lfs. Проверить, что `../model/bge-m3_en_ru/model.safetensors` весит ~1.4 ГБ, а не пару килобайт. |
| Пустой график, «0 строк» | `fct_trips` пуст. Перезапустить `./start.sh` (он идемпотентен) или засеять вручную: `docker compose exec -T backend python -m app.db.seed_from_tlc --months 1 --sample 10000`. |

## Лицензия

MIT, см. [LICENSE](LICENSE).
