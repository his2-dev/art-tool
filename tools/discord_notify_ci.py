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
        r = _req.head(url, timeout=8, allow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def _resolve_image_url(image_url: str) -> str:
    """직접 이미지 URL이면 그대로, 아티클 URL이면 og:image 추출."""
    if not image_url:
        return ""
    if _is_direct_image_url(image_url):
        return image_url
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
