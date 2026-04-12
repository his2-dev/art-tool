"""
뉴스 게시물 생성기 환경 셋업 스크립트

처음 한 번만 실행하면 됩니다:
    python tools/setup_assets.py

- Pretendard / Clash Display 폰트를 tools/assets/fonts/ 에 다운로드
- Figma에서 로고(logo_w.png)를 내보내기
- Windows에서 실행 시, 이미 설치된 폰트를 fonts/ 폴더로 복사

[Codex / Linux 환경]에서 실행하면 GitHub에서 폰트를 자동으로 다운로드합니다.
"""

import os
import sys
import shutil
import platform

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo_w.png")

os.makedirs(FONTS_DIR, exist_ok=True)

REQUIRED_FONTS = {
    "Pretendard-Bold.ttf": None,
    "Pretendard-Regular.ttf": None,
    "ClashDisplay-Medium.otf": None,
}

# ── 1. Windows: 시스템 폰트 폴더에서 복사 ──────────────────
def copy_from_windows_fonts():
    user_font_dir = os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts")
    system_font_dir = "C:/Windows/Fonts"

    copied = 0
    for fname in REQUIRED_FONTS:
        dst = os.path.join(FONTS_DIR, fname)
        if os.path.exists(dst):
            print(f"  [skip] {fname} (이미 존재)")
            continue
        for src_dir in [user_font_dir, system_font_dir]:
            src = os.path.join(src_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"  [복사] {fname}")
                copied += 1
                break
        else:
            print(f"  [없음] {fname} — 수동으로 tools/assets/fonts/에 복사해주세요")
    return copied


# ── 2. Linux/Mac: GitHub에서 다운로드 ──────────────────────
def download_fonts():
    import requests

    # Pretendard (오픈소스, MIT 라이선스)
    # https://github.com/orioncactus/pretendard
    pretendard_base = (
        "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/"
    )
    pretendard_fonts = {
        "Pretendard-Bold.ttf": f"{pretendard_base}Pretendard-Bold.otf",
        "Pretendard-Regular.ttf": f"{pretendard_base}Pretendard-Regular.otf",
    }

    # Clash Display (무료, Personal Use License)
    # https://www.fontshare.com/fonts/clash-display
    clash_url = "https://api.fontshare.com/v2/fonts/download/clash-display"

    headers = {"User-Agent": "Mozilla/5.0"}

    for fname, url in pretendard_fonts.items():
        # Pretendard는 otf로 받아서 ttf로 저장 (Pillow는 otf도 읽음)
        actual_fname = fname.replace(".ttf", ".otf")
        dst = os.path.join(FONTS_DIR, actual_fname)
        if os.path.exists(dst):
            print(f"  [skip] {actual_fname}")
            continue
        print(f"  [다운로드] {actual_fname}...")
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            with open(dst, "wb") as f:
                f.write(r.content)
            print(f"  [완료] {actual_fname} ({len(r.content)//1024}KB)")
        except Exception as e:
            print(f"  [실패] {actual_fname}: {e}")

    # Clash Display: zip으로 배포되므로 안내만
    clash_dst = os.path.join(FONTS_DIR, "ClashDisplay-Medium.otf")
    if not os.path.exists(clash_dst):
        print("""
  [Clash Display 수동 설치 필요]
  1. https://www.fontshare.com/fonts/clash-display 에서 다운로드
  2. ClashDisplay-Medium.otf 를 tools/assets/fonts/ 에 복사
  (뱃지 미사용 시 불필요 — news_poster.py --badge 옵션 사용 안 하면 생략 가능)
""")


# ── 3. Figma에서 로고 내보내기 ────────────────────────────
def download_logo():
    if os.path.exists(LOGO_PATH):
        print(f"  [skip] logo_w.png (이미 존재)")
        return

    figma_token = os.environ.get("FIGMA_API_KEY", "")
    if not figma_token:
        print("""
  [로고 수동 설치 필요]
  환경변수 FIGMA_API_KEY 가 없습니다.
  또는 tools/assets/logo_w.png 를 직접 복사해주세요.
""")
        return

    import requests

    # 로고_W 노드 내보내기
    node_id = "I31:631;4738:23066"
    import urllib.parse
    encoded = urllib.parse.quote(node_id)
    file_key = "HFgX7HKHYYHwjCVBgA6mYD"

    resp = requests.get(
        f"https://api.figma.com/v1/images/{file_key}?ids={encoded}&format=png&scale=4",
        headers={"X-Figma-Token": figma_token},
        timeout=20,
    )
    data = resp.json()
    img_url = list(data.get("images", {}).values())[0]
    if not img_url:
        print("  [실패] Figma 로고 URL을 가져오지 못했습니다")
        return

    img_resp = requests.get(img_url, timeout=20)
    with open(LOGO_PATH, "wb") as f:
        f.write(img_resp.content)
    print(f"  [완료] logo_w.png 다운로드")


# ── 메인 ────────────────────────────────────────────────
def main():
    system = platform.system()
    print(f"\n[셋업 시작] OS: {system}\n")

    print("== 폰트 ==")
    if system == "Windows":
        copy_from_windows_fonts()
    else:
        download_fonts()

    print("\n== 로고 ==")
    download_logo()

    print("\n[셋업 완료] tools/assets/ 구조:")
    for f in sorted(os.listdir(ASSETS_DIR)):
        print(f"  {f}")
    fonts = os.listdir(FONTS_DIR)
    for f in sorted(fonts):
        print(f"    fonts/{f}")


if __name__ == "__main__":
    main()
