# Maintainer: Sujatro Ganguli <iamsurjog@gmail.com>
pkgname=Vessel
pkgver=0.0.0
pkgrel=1
pkgdesc="A local-first desktop knowledge workspace with AI-powered RAG. Everything runs on your machine — no cloud, no telemetry, no accounts. Write notes, store materials, and ask questions entirely offline. "
arch=('any')
url="https://github.com/iamsurjog/Vessel"
license=('MIT')
optdepends=('tesseract' 'ffmpeg' 'ollama')
makedepends=('python')

source=("git+${url}.git")
sha256sums=('SKIP')

build() {
    cd "${pkgname}"
    python3 -m venv ./.venv
    source ./.venv/bin/activate
    pip install -r requirements.txt
    pip install pyinstaller
    pyinstaller --onefile --windowed --add-data "main.qml:." main.py
    deactivate
}

package() {
    cd "${pkgname}"
    # Create the destination directory first
    install -Dm755 "dist/main" "$pkgdir/usr/bin/vessel"
}

