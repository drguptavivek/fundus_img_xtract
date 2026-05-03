#!/bin/sh
set -eu

requirements_file="${1:?usage: build_venv.sh requirements.txt}"
venv_path="${UV_PROJECT_ENVIRONMENT:-/app/.venv}"
checksum_path="${venv_path}/.requirements.sha256"
current_checksum="$(sha256sum "$requirements_file" | awk '{print $1}')"

if [ -x "${venv_path}/bin/python" ] &&
   [ -f "$checksum_path" ] &&
   [ "$(cat "$checksum_path")" = "$current_checksum" ]; then
    echo "Using existing venv for ${requirements_file}"
    exit 0
fi

echo "Rebuilding venv for ${requirements_file}"
mkdir -p "$venv_path"
find "$venv_path" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
uv venv "$venv_path"
uv pip install --link-mode=copy --python "${venv_path}/bin/python" -r "$requirements_file"
printf '%s\n' "$current_checksum" > "$checksum_path"
