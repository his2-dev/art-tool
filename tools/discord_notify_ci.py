"""
CI용 Discord 전송 헬퍼.
output/news/YYYY-MM-DD_키워드.json 메타 파일을 읽어 같은 이름의 .png 이미지와 함께 Discord로 전송합니다.

메타 JSON 스키마:
{
    "news_title": "...",
    "news_url": "...",
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

# 프로젝트 루트를 import path에 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.discord_sender import send_news_to_discord  # noqa: E402


def _resolve_image_path(meta_path: str, meta: dict) -> str:
    # 메타에 image_path가 있으면 우선, 없으면 .json → .png로 치환
    candidate = meta.get("image_path")
    if candidate and os.path.exists(candidate):
        return candidate
    sibling = meta_path[:-5] + ".png" if meta_path.endswith(".json") else meta_path + ".png"
    return sibling


def main() -> int:
    parser = argparse.ArgumentParser(description="메타 JSON을 읽어 Discord로 전송")
    parser.add_argument("meta_path", help="output/news/*.json 경로")
    args = parser.parse_args()

    with open(args.meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    image_path = _resolve_image_path(args.meta_path, meta)
    if not os.path.exists(image_path):
        print(f"[오류] 이미지 파일 없음: {image_path}", file=sys.stderr)
        return 1

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
