#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

show_help() {
  cat <<'EOF'
Drivee DataPilot launcher.

Usage:
  ./start.sh           full stack; seeds 10k synthetic trips on first run
  ./start.sh --full    seed 500k trips over 3 months instead
  ./start.sh --help    show this message

Requires Docker Desktop (or compatible) and a local LLM endpoint on
http://localhost:8080/v1 (see README -> LLM setup).
EOF
}

SAMPLE=10000
MONTHS=1
for arg in "$@"; do
  case "$arg" in
    --full) SAMPLE=500000; MONTHS=3 ;;
    --help|-h) show_help; exit 0 ;;
  esac
done

if [[ ! -f .env ]]; then
  echo "[start] no .env found, creating from .env.example with a random password"
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    PW=$(openssl rand -hex 16)
  else
    PW=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
  fi
  sed -i.bak "s/change_me_to_a_random_string/${PW}/g" .env && rm -f .env.bak
fi

if [[ ! -d ../model ]]; then
  echo "[start] ../model not found, creating empty stub"
  echo "        place qwen GGUF and bge-m3_en_ru inside before first /ask"
  mkdir -p ../model
fi

detect_llm_url() {
  if [[ -n "${LLAMA_CPP_URL:-}" ]] && [[ "${LLAMA_CPP_URL}" != *"host.docker.internal"* ]]; then
    echo "$LLAMA_CPP_URL"
    return
  fi
  local gw
  gw=$(ip route show 2>/dev/null | awk '/default/ {print $3; exit}')
  if [[ -n "$gw" ]] && curl -fsS --max-time 2 "http://${gw}:8080/v1/models" >/dev/null 2>&1; then
    echo "http://${gw}:8080/v1"
    return
  fi
  echo "http://host.docker.internal:8080/v1"
}

LLAMA_CPP_URL=$(detect_llm_url)
export LLAMA_CPP_URL
echo "[start] LLM endpoint: $LLAMA_CPP_URL"

echo "[start] docker compose up -d --build"
docker compose up -d --build

echo "[start] waiting for backend health..."
for _ in {1..60}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "[start] backend is healthy"
    break
  fi
  sleep 2
done

ROW_COUNT=$(docker compose exec -T postgres psql -U drivee -d drivee -tAc \
  "SELECT to_regclass('public.fct_trips') IS NOT NULL AND \
          (SELECT count(*) FROM fct_trips) > 0;" 2>/dev/null || echo "f")

if [[ "$ROW_COUNT" != "t" ]]; then
  echo "[start] seeding ${SAMPLE} synthetic trips over ${MONTHS} month(s)"
  docker compose exec -T backend python -m app.db.seed_from_tlc \
    --months "${MONTHS}" --sample "${SAMPLE}"
else
  echo "[start] fct_trips already populated, skipping seed"
fi

cat <<EOF

------------------------------------------------------------
Drivee DataPilot is up.

  Frontend       http://localhost:5173
  API docs       http://localhost:8000/docs
  Eval dashboard http://localhost:5173 -> Анализ

Try in the chat:
  - Сколько отмен по городам за прошлую неделю?
  - Сравни конверсию по каналам за последние 30 дней
  - Топ-3 города по количеству отменённых заказов на этой неделе

Stop:        docker compose down
Wipe data:   docker compose down -v
Run eval:    docker compose exec backend python -m eval.run_eval
------------------------------------------------------------
EOF
