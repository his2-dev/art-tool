"""
CI용 Discord 전송 헬퍼.

output/news/*.json 메타 파일을 읽어:
  1) image_url에서 og:image 추출 (아티클 URL인 경우) 또는 직접 이미지 URL 사용
  2) news_poster로 PNG 생성 (실패 시 다크 배경으로 재시도)
  3) discord_sender로 채널 전송

메타 JSON 스키마:
{
    "news_title": "...",
    "news_url": "...",
    "image_url": "...",           # 아티클 URL 또는 직접 이미지 URL
    "headline1": "...",
    "headline2": "...",
    "source": "© ...",
    "caption": "...",
    "candidates": [{"title": "...", "url": "..."}, ...]
}
"""

import argparse
import json
import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.discord_sender import send_news_to_discord  # noqa: E402
from tools.news_poster import generate_news_poster  # noqa: E402


def _is_direct_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return True
    # 확장자 없어도 CDN URL이면 HEAD로 content-type 확인
    try:
        import requests as _req
        _hdrs = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        r = _req.head(url, timeout=8, allow_redirects=True, headers=_hdrs)
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def _resolve_image_url(image_url: str) -> str:
    """직접 이미지 URL이면 그대로, 아티클 URL이면 기사 내 최적 이미지 추출.

    og:image가 저해상도 썸네일(1200x630 등)인 경우가 많아, 본문 원본 이미지까지
    스캔해 해상도 검증 후 가장 좋은 것을 사용한다 (썸네일 화질 개선).
    """
    if not image_url:
        return ""
    if _is_direct_image_url(image_url):
        return image_url
    try:
        from tools.article_parser import find_best_image
        best, w, h = find_best_image(image_url, min_width=500, min_height=400)
        if best:
            print(f"[이미지] {w}x{h} 채택: {best[:80]}", file=sys.stderr)
            return best
    except Exception as e:
        print(f"[경고] 최적 이미지 탐색 실패 ({image_url}): {e}", file=sys.stderr)
    # 폴백: og:image만이라도 시도 (해상도 기준 미달이어도 회색 배경보다 낫다)
    try:
        from tools.article_parser import parse_article
        parsed = parse_article(image_url)
        return parsed.get("image_url", "")
    except Exception as e:
        print(f"[경고] og:image 추출 실패 ({image_url}): {e}", file=sys.stderr)
        return ""


def _generate(meta: dict, image_path: str, image_url: str) -> None:
    generate_news_poster(
        headline1=meta.get("headline1", ""),
        headline2=meta.get("headline2", ""),
        source=meta.get("source", ""),
        image_url=image_url or None,
        output_path=image_path,
        scale=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="메타 JSON을 읽어 이미지 생성 후 Discord 전송")
    parser.add_argument("meta_path")
    args = parser.parse_args()

    with open(args.meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    image_path = meta.get("image_path") or (
        args.meta_path[:-5] + ".png" if args.meta_path.endswith(".json") else args.meta_path + ".png"
    )

    # 항상 새로 생성 — 이미지 다운로드 실패 시 다크 배경으로 폴백
    resolved = _resolve_image_url(meta.get("image_url", ""))
    try:
        _generate(meta, image_path, resolved)
    except Exception as e:
        print(f"[경고] 이미지 다운로드 실패, 다크 배경으로 재시도: {e}", file=sys.stderr)
        _generate(meta, image_path, "")

    status = send_news_to_discord(
        image_path=image_path,
        news_title=meta.get("news_title", ""),
        news_url=meta.get("news_url", ""),
        headline1=meta.get("headline1", ""),
        headline2=meta.get("headline2", ""),
        source=meta.get("source", ""),
        caption=meta.get("caption", ""),
        candidates=meta.get("candidates"),
    )
    return 0 if status == 200 else 2


if __name__ == "__main__":
    sys.exit(main())
