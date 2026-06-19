"""
인스타그램 뉴스 게시물 이미지 생성기
Figma 20181111 템플릿 기반

사용법:
    python tools/news_poster.py \
        --headline1 "국립현대미술관" \
        --headline2 "전시 관람료 인상" \
        --source "© 국립현대미술관" \
        --image_url "https://example.com/image.jpg" \
        --output "portfolio/instagram/news/2026-04-11.png"

    # 뱃지 표시하려면:
    python tools/news_poster.py ... --badge "place"
"""

import argparse
import os
import sys
from io import BytesIO
from datetime import date

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 상수 ──────────────────────────────────────────────
CANVAS_W, CANVAS_H = 1080, 1350

# 폰트 경로 (우선순위: 레포 내 assets/fonts → Windows 사용자 폰트 → 시스템 폰트)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR_REPO = os.path.join(_SCRIPT_DIR, "assets", "fonts")
FONT_DIR_WIN_USER = os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts")
FONT_DIR_WIN_SYS = "C:/Windows/Fonts"
FONT_DIR_LINUX = "/usr/share/fonts"


def _find_font(name: str) -> str:
    """레포 → Windows 사용자 → Windows 시스템 → Linux 순으로 폰트 검색.
    .ttf 못 찾으면 .otf 확장자도 시도."""
    candidates = [name, name.replace(".ttf", ".otf"), name.replace(".otf", ".ttf")]
    search_dirs = [FONT_DIR_REPO, FONT_DIR_WIN_USER, FONT_DIR_WIN_SYS]
    # Linux: /usr/share/fonts 하위 재귀 검색
    if os.path.exists(FONT_DIR_LINUX):
        for root, _, files in os.walk(FONT_DIR_LINUX):
            search_dirs.append(root)

    for candidate in candidates:
        for d in search_dirs:
            p = os.path.join(d, candidate)
            if os.path.exists(p):
                return p
    return os.path.join(FONT_DIR_REPO, name)


PRETENDARD_BOLD = _find_font("Pretendard-Bold.ttf")
PRETENDARD_REGULAR = _find_font("Pretendard-Regular.ttf")
CLASH_DISPLAY_MEDIUM = _find_font("ClashDisplay-Medium.otf")

# 에셋 경로
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo_w.png")

# 레이아웃 (Figma 기준 상대좌표)
LOGO_POS = (72, 72)
LOGO_SIZE = (124, 56)
LOGO_LUMA_THRESHOLD = 165

# 그라데이션: 하단 60% 영역, 더 부드럽게
SHADOW_START_RATIO = 0.4  # 캔버스 40% 지점부터 시작
SHADOW_MAX_ALPHA = 180

# 업스케일 배율이 이 값을 넘으면 선명 보정 대신 블러 배경 처리
# (저화질 원본을 억지로 키우면 픽셀·노이즈가 두드러짐 → 깔끔한 블러가 낫다)
LOW_RES_BLUR_THRESHOLD = 2.4

HEADLINE1_Y = 935
HEADLINE2_Y = 1055

SOURCE_RIGHT_MARGIN = 72
SOURCE_Y = 1261

BADGE_X = 430
BADGE_Y = 851
BADGE_W = 220
BADGE_H = 64
BADGE_TEXT_X = 450
BADGE_TEXT_Y = 867
BADGE_RADIUS = 32


def download_image(url: str) -> Image.Image:
    """URL에서 이미지를 다운로드하여 PIL Image로 반환.
    curl_cffi가 있으면 Chrome 핑거프린트로 우회 (한국 뉴스 사이트 403 대응)."""
    try:
        from tools.article_parser import http_get
        resp = http_get(url, timeout=15)
    except ImportError:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGB")


def crop_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """이미지를 target 비율로 crop 후 resize.

    - 가로 초과분은 중앙 crop, 세로 초과분은 상단 1/3 지점 기준 crop
      (인물·작품이 보통 상단에 위치)
    - 업스케일 배율이 클 때는 2단계 리사이즈 + 언샤프로 계단 현상 완화
    """
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = int((src_h - new_h) * 0.33)
        img = img.crop((0, top, src_w, top + new_h))

    crop_w, crop_h = img.size
    upscale = target_w / max(crop_w, 1)

    if upscale > LOW_RES_BLUR_THRESHOLD:
        # 원본이 너무 작아 선명한 업스케일이 불가능 → 픽셀이 두드러지는 것보다
        # 의도적인 블러 배경이 깔끔하게 보임 (텍스트·로고는 이후 선명하게 올라감)
        resized = img.resize((target_w, target_h), Image.LANCZOS)
        radius = max(6, int(target_w / 140))
        resized = resized.filter(ImageFilter.GaussianBlur(radius=radius))
        print(f"[화질] 업스케일 {upscale:.1f}x — 저화질 보정으로 블러 배경 적용 (radius={radius})")
        return resized

    if upscale > 1.75:
        # 2단계 업스케일: 중간 크기를 거치면 보간 품질이 좋아짐
        mid_w = int(crop_w * (upscale ** 0.5))
        mid_h = int(crop_h * (upscale ** 0.5))
        img = img.resize((mid_w, mid_h), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=3))

    resized = img.resize((target_w, target_h), Image.LANCZOS)
    if upscale > 1.05:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1.8, percent=110, threshold=3))
    return resized


def draw_gradient_shadow(canvas: Image.Image, canvas_w: int, canvas_h: int):
    """하단 그라데이션 오버레이 (부드러운 투명→검정)."""
    shadow_y = int(canvas_h * SHADOW_START_RATIO)
    shadow_h = canvas_h - shadow_y

    overlay = Image.new("RGBA", (canvas_w, shadow_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(shadow_h):
        progress = y / shadow_h
        alpha = int(SHADOW_MAX_ALPHA * (progress ** 2.0))
        alpha = min(alpha, SHADOW_MAX_ALPHA)
        draw.line([(0, y), (canvas_w, y)], fill=(0, 0, 0, alpha))

    region = canvas.crop((0, shadow_y, canvas_w, canvas_h)).convert("RGBA")
    composited = Image.alpha_composite(region, overlay)
    canvas.paste(composited, (0, shadow_y))


def draw_headline(draw: ImageDraw.Draw, text: str, y: int, font: ImageFont.FreeTypeFont, canvas_w: int):
    """중앙 정렬 헤드라인 렌더링."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (canvas_w - text_w) // 2
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def draw_badge(
    canvas: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    badge_x: int,
    badge_y: int,
    badge_w: int,
    badge_h: int,
    badge_text_x: int,
    badge_text_y: int,
    badge_radius: int,
):
    """반투명 흰색 배경 뱃지 + 텍스트 + 화살표."""
    badge_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge_overlay)

    badge_draw.rounded_rectangle(
        [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
        radius=badge_radius,
        fill=(255, 255, 255, 128),
    )

    badge_draw.text(
        (badge_text_x, badge_text_y),
        text,
        fill=(0, 0, 0),
        font=font,
    )

    # 화살표 (chevron-down)
    arrow_x = badge_x + badge_w - int(48 * badge_w / BADGE_W) + int(12 * badge_w / BADGE_W)
    arrow_y = badge_y + (badge_h - int(12 * badge_h / BADGE_H)) // 2 + int(4 * badge_h / BADGE_H)
    arrow_mid_x = arrow_x + int(12 * badge_w / BADGE_W)
    arrow_end_x = arrow_x + int(24 * badge_w / BADGE_W)
    arrow_mid_y = arrow_y + int(10 * badge_h / BADGE_H)
    badge_draw.line(
        [(arrow_x, arrow_y), (arrow_mid_x, arrow_mid_y), (arrow_end_x, arrow_y)],
        fill=(0, 0, 0),
        width=max(1, int(3 * badge_w / BADGE_W)),
    )

    canvas_rgba = canvas.convert("RGBA")
    result = Image.alpha_composite(canvas_rgba, badge_overlay)
    canvas.paste(result.convert("RGB"))


def draw_source(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    canvas_w: int,
    source_right_margin: int,
    source_y: int,
):
    """우하단 출처 텍스트."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = canvas_w - source_right_margin - text_w
    draw.text((x, source_y), text, fill=(147, 147, 147), font=font)


def overlay_logo(canvas: Image.Image, logo_pos: tuple, logo_size: tuple, logo_color: str = "auto"):
    """좌상단 로고 오버레이.

    Args:
        logo_color: "auto" (배경 밝기 자동), "white", "black"
    """
    if not os.path.exists(LOGO_PATH):
        print(f"[경고] 로고 파일 없음: {LOGO_PATH}")
        return

    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo = logo.resize(logo_size, Image.LANCZOS)

    if logo_color == "white":
        color = (255, 255, 255)
    elif logo_color == "black":
        color = (0, 0, 0)
    else:
        # 자동: 배경 밝기 기반
        logo_box = (
            logo_pos[0],
            logo_pos[1],
            logo_pos[0] + logo_size[0],
            logo_pos[1] + logo_size[1],
        )
        bg_region = canvas.crop(logo_box).convert("RGB")
        pixels = list(bg_region.getdata())
        avg_luma = sum((0.299 * r) + (0.587 * g) + (0.114 * b) for r, g, b in pixels) / max(len(pixels), 1)
        color = (0, 0, 0) if avg_luma >= LOGO_LUMA_THRESHOLD else (255, 255, 255)

    tinted_logo = Image.new("RGBA", logo.size, color + (0,))
    tinted_logo.putalpha(logo.getchannel("A"))
    canvas.paste(tinted_logo, logo_pos, tinted_logo)


def generate_news_poster(
    headline1: str,
    headline2: str,
    source: str,
    image_url: str = None,
    image_path: str = None,
    badge_text: str = None,
    output_path: str = None,
    scale: float = 1,
    logo_color: str = "auto",
) -> str:
    """뉴스 게시물 이미지를 생성하고 저장합니다."""
    if scale < 1:
        raise ValueError("scale 은 1 이상이어야 합니다.")

    # 1. 배경 이미지 (스케일 결정 전에 로드 — 원본 해상도에 맞춰 출력 배율 제한)
    bg = None
    if image_path and os.path.exists(image_path):
        bg = Image.open(image_path).convert("RGB")
    elif image_url:
        try:
            bg = download_image(image_url)
        except Exception as e:
            print(f"[배경] 이미지 다운로드 실패({e}) → 어두운 배경으로 대체 (CI가 image_url로 재생성)")
            bg = None

    scale_value = float(scale)
    if bg is not None:
        # 원본에서 캔버스 비율로 crop했을 때 쓸 수 있는 가로폭 기준으로
        # 의미 없는 과업스케일 방지 (예: 1200x630 원본을 2160x2700으로 4배 확대)
        src_w, src_h = bg.size
        usable_w = min(src_w, src_h * CANVAS_W / CANVAS_H)
        supported_scale = max(1.0, usable_w / CANVAS_W)
        if supported_scale < scale_value:
            scale_value = round(supported_scale, 2)
            print(f"[배율] 원본 {src_w}x{src_h} → 출력 배율 {scale_value}x로 제한 (과업스케일 방지)")

    canvas_w = int(round(CANVAS_W * scale_value))
    canvas_h = int(round(CANVAS_H * scale_value))
    logo_pos = (int(round(LOGO_POS[0] * scale_value)), int(round(LOGO_POS[1] * scale_value)))
    logo_size = (int(round(LOGO_SIZE[0] * scale_value)), int(round(LOGO_SIZE[1] * scale_value)))
    headline1_y = int(round(HEADLINE1_Y * scale_value))
    headline2_y = int(round(HEADLINE2_Y * scale_value))
    source_right_margin = int(round(SOURCE_RIGHT_MARGIN * scale_value))
    source_y = int(round(SOURCE_Y * scale_value))
    badge_x = int(round(BADGE_X * scale_value))
    badge_y = int(round(BADGE_Y * scale_value))
    badge_w = int(round(BADGE_W * scale_value))
    badge_h = int(round(BADGE_H * scale_value))
    badge_text_x = int(round(BADGE_TEXT_X * scale_value))
    badge_text_y = int(round(BADGE_TEXT_Y * scale_value))
    badge_radius = int(round(BADGE_RADIUS * scale_value))

    if bg is None:
        bg = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 30))

    canvas = crop_cover(bg, canvas_w, canvas_h)
    canvas = canvas.convert("RGBA")

    # 2. 그라데이션 오버레이
    draw_gradient_shadow(canvas, canvas_w, canvas_h)

    # 3. 로고
    overlay_logo(canvas, logo_pos, logo_size, logo_color=logo_color)

    # RGB로 변환 후 텍스트 렌더링
    canvas_rgb = canvas.convert("RGB")

    # 4. 폰트 로드
    try:
        font_headline = ImageFont.truetype(PRETENDARD_BOLD, int(round(96 * scale_value)))
        font_source = ImageFont.truetype(PRETENDARD_REGULAR, int(round(24 * scale_value)))
    except OSError as e:
        print(f"[오류] 폰트 로드 실패: {e}")
        print("Pretendard Bold, Regular 설치 필요")
        sys.exit(1)

    # 5. 뱃지 (옵션, 기본 비활성)
    if badge_text:
        try:
            font_badge = ImageFont.truetype(CLASH_DISPLAY_MEDIUM, int(round(48 * scale_value)))
            draw_badge(
                canvas_rgb,
                badge_text,
                font_badge,
                badge_x,
                badge_y,
                badge_w,
                badge_h,
                badge_text_x,
                badge_text_y,
                badge_radius,
            )
        except OSError:
            print("[경고] Clash Display 폰트 없음, 뱃지 생략")

    draw = ImageDraw.Draw(canvas_rgb)

    # 6. 헤드라인
    draw_headline(draw, headline1, headline1_y, font_headline, canvas_w)
    draw_headline(draw, headline2, headline2_y, font_headline, canvas_w)

    # 7. 출처
    draw_source(draw, source, font_source, canvas_w, source_right_margin, source_y)

    # 8. 저장
    if not output_path:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "output", "news",
        )
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{date.today().isoformat()}.png")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas_rgb.save(output_path, "PNG", quality=95)
    print(f"[완료] 이미지 저장: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="뉴스 게시물 이미지 생성")
    parser.add_argument("--headline1", required=True, help="제목 1줄")
    parser.add_argument("--headline2", required=True, help="제목 2줄")
    parser.add_argument("--source", required=True, help="이미지 출처 (예: © 국립현대미술관)")
    parser.add_argument("--image_url", help="배경 이미지 URL")
    parser.add_argument("--image_path", help="배경 이미지 로컬 경로")
    parser.add_argument("--badge", default=None, help="뱃지 텍스트 (미입력 시 뱃지 없음)")
    parser.add_argument("--output", help="출력 파일 경로")
    parser.add_argument("--scale", type=float, default=1, help="출력 배율 (1=1080x1350, 1.5=1620x2025, 2=2160x2700)")
    parser.add_argument("--logo-color", default="auto", choices=["auto", "white", "black"], help="로고 색상 (기본: auto)")
    args = parser.parse_args()

    generate_news_poster(
        headline1=args.headline1,
        headline2=args.headline2,
        source=args.source,
        image_url=args.image_url,
        image_path=args.image_path,
        badge_text=args.badge,
        output_path=args.output,
        scale=args.scale,
        logo_color=args.logo_color,
    )


if __name__ == "__main__":
    main()
