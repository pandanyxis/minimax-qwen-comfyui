#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p /workspace/ComfyUI/{models,input,output,temp,user}
/opt/hf/bin/python /opt/combined/provision-helpers.py
/opt/venv/bin/python /opt/combined/provision-civitai.py /workspace/ComfyUI/models
for pair in CIVITAI_CHECKPOINTS:checkpoints CIVITAI_LORAS:loras; do
  key="${pair%%:*}"
  folder="${pair#*:}"
  IFS=',' read -ra identifiers <<< "${!key:-}"
  for identifier in "${identifiers[@]}"; do
    [[ -z "${identifier// /}" ]] && continue
    /opt/venv/bin/python /opt/combined/download-civitai.py \
      --identifier "${identifier// /}" --output "/workspace/ComfyUI/models/$folder"
  done
done
cat > /workspace/combined/model-paths.yaml <<'EOF'
personal:
  base_path: /workspace/ComfyUI/models
  checkpoints: checkpoints
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  clip_vision: clip_vision
  vae: vae
  loras: loras
  vae_approx: vae_approx
  custom_nodes: /ComfyUI/custom_nodes
EOF
cd /ComfyUI
pids=()
cleanup() {
  trap - EXIT TERM INT
  for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# The token is inherited through the environment, never process arguments.
export JUPYTER_TOKEN
/opt/venv/bin/jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root \
  --ServerApp.root_dir=/workspace &
pids+=("$!")
/opt/venv/bin/python main.py --listen 0.0.0.0 --port 8188 \
  --disable-dynamic-vram --preview-method taesd \
  --base-directory /workspace/ComfyUI \
  --extra-model-paths-config /workspace/combined/model-paths.yaml &
pids+=("$!")
set +e
wait -n "${pids[@]}"
status=$?
set -e
(( status == 0 )) && status=1
exit "$status"
