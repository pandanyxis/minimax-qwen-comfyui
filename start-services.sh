#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${ENABLE_WEBUI:-true}" == "false" ]]; then
  exec /usr/local/bin/start-qwen
fi
if [[ "${ENABLE_WEBUI:-true}" != "true" ]]; then
  echo 'ENABLE_WEBUI must be true or false.' >&2
  exit 1
fi
: "${LLAMA_API_KEY:?Set LLAMA_API_KEY (at least 32 random characters)}"
: "${WEBUI_ADMIN_EMAIL:?Set WEBUI_ADMIN_EMAIL for your browser login}"
: "${WEBUI_ADMIN_PASSWORD:?Set WEBUI_ADMIN_PASSWORD for your browser login}"
if (( ${#LLAMA_API_KEY} < 32 || ${#WEBUI_ADMIN_PASSWORD} < 16 || ${#WEBUI_ADMIN_PASSWORD} > 72 )); then
  echo 'Use an API key of at least 32 characters and an admin password of 16-72 ASCII characters.' >&2
  exit 1
fi
export DATA_DIR=/workspace/open-webui
mkdir -p "$DATA_DIR"
umask 077
if [[ -z "${WEBUI_SECRET_KEY:-}" ]]; then
  if [[ ! -s "$DATA_DIR/.webui_secret_key" ]]; then
    "${WEBUI_BIN_DIR:-/opt/webui/bin}/python" -c 'import secrets; print(secrets.token_hex(32))' > "$DATA_DIR/.webui_secret_key"
  fi
  export WEBUI_SECRET_KEY="$(cat "$DATA_DIR/.webui_secret_key")"
fi
export OPENAI_API_BASE_URL=http://127.0.0.1:8080/v1
export OPENAI_API_BASE_URLS="$OPENAI_API_BASE_URL"
export OPENAI_API_KEY="$LLAMA_API_KEY"
export OPENAI_API_KEYS="$LLAMA_API_KEY"
export ENABLE_OLLAMA_API=false ENABLE_OPENAI_API=true
export WEBUI_AUTH=true ENABLE_SIGNUP=false
export DEFAULT_MODELS=qwen-hauhau
export DEFAULT_MODEL_METADATA='{"capabilities":{"vision":true}}'
export ENV=prod
pids=()
cleanup() {
  trap - EXIT TERM INT
  for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
/usr/local/bin/start-qwen &
pids+=("$!")
cd "$DATA_DIR"
"${WEBUI_BIN_DIR:-/opt/webui/bin}/open-webui" serve --host 0.0.0.0 --port 3000 &
pids+=("$!")
echo 'Open WebUI is starting on port 3000. The API is on port 8080 and becomes ready after model loading.'
set +e
wait -n "${pids[@]}"
status=$?
set -e
echo "A service exited (status $status); stopping the container so both services restart together." >&2
(( status == 0 )) && status=1
exit "$status"
