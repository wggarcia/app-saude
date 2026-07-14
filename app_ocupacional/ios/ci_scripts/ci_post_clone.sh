#!/bin/sh
# Xcode Cloud — executa após o clone do repositório.
# Instala Flutter e prepara as dependências antes do xcodebuild.
set -e

FLUTTER_VERSION="3.44.6"
FLUTTER_DIR="$HOME/flutter"

echo "==> Instalando Flutter $FLUTTER_VERSION"
if [ ! -d "$FLUTTER_DIR" ]; then
  git clone --depth 1 --branch "$FLUTTER_VERSION" \
    https://github.com/flutter/flutter.git "$FLUTTER_DIR"
fi

export PATH="$FLUTTER_DIR/bin:$PATH"

echo "==> flutter pub get"
cd "$CI_PRIMARY_REPOSITORY_PATH/app_ocupacional"
flutter pub get

echo "==> pod install"
cd ios
pod install --repo-update

echo "==> Pronto"
