#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$BACKEND_DIR/build"
DIST_DIR="$BACKEND_DIR/dist"
ZIP_PATH="$DIST_DIR/function.zip"
PYTHON="${PYTHON:-python3}"

rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

if "$PYTHON" -m pip --version >/dev/null 2>&1; then
  "$PYTHON" -m pip install \
    --quiet \
    --platform manylinux2014_aarch64 \
    --implementation cp \
    --python-version 3.13 \
    --only-binary=:all: \
    --upgrade \
    --target "$BUILD_DIR" \
    -r "$BACKEND_DIR/requirements.txt"
elif command -v uv >/dev/null 2>&1; then
  uv pip install \
    --quiet \
    --python "$PYTHON" \
    --python-platform aarch64-manylinux2014 \
    --python-version 3.13 \
    --only-binary :all: \
    --target "$BUILD_DIR" \
    -r "$BACKEND_DIR/requirements.txt"
else
  echo "need pip in $PYTHON or uv on PATH" >&2
  exit 1
fi

cp -R "$BACKEND_DIR/app" "$BUILD_DIR/app"

find "$BUILD_DIR" -type d \( -name "__pycache__" -o -name "tests" -o -name "test" -o -name "*.dist-info" \) -prune -exec rm -rf {} +
find "$BUILD_DIR" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
find "$BUILD_DIR" -exec touch -t 200001010000 {} +

(
  cd "$BUILD_DIR"
  find . -type f | LC_ALL=C sort | zip -X -q -@ "$ZIP_PATH"
)

SIZE=$(du -h "$ZIP_PATH" | cut -f1)
echo "built $ZIP_PATH ($SIZE)"
