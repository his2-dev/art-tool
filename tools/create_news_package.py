"""
뉴스 게시물 패키지 생성기

한 번의 실행으로 아래 파일을 함께 생성합니다.
- 이미지: output/news/YYYY-MM-DD_slug.png
- 캡션: output/news/YYYY-MM-DD_slug.md
- 메타데이터: output/news/YYYY-MM-DD_slug.json
"""

import argparse
import json
import os
import re
from datetime import date

from figma_handoff import create_figma_handoff
from news_poster import generate_news_poster


def slugify(value: str) -> str:
    """Windows 파일명에 안전한 슬러그로 정리."""
    cleaned = re.sub(r"\s+", "_", value.strip())
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]", "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "news"


def build_paths(base_dir: str, post_date: str, slug: str):
    stem = f"{post_date}_{slug}"
    return {
        "image": os.path.join(base_dir, f"{stem}.png"),
        "caption": os.path.join(base_dir, f"{stem}.md"),
        "metadata": os.path.join(base_dir, f"{stem}.json"),
    }


def normalize_hashtags(value: str) -> list:
    tags = []
    for raw in value.split():
        tag = raw if raw.startswith("#") else f"#{raw}"
        if tag not in tags:
            tags.append(tag)
    return tags


def write_caption(path: str, payload: dict):
    lines = [
        "# 뉴스 게시물",
        "",
        f"- 날짜: {payload['date']}",
        f"- 기사 제목: {payload['article_title'] or '미입력'}",
        f"- 기사 링크: {payload['article_url'] or '미입력'}",
        f"- 이미지 출처: {payload['source']}",
        "",
        "## 헤드라인",
        payload["headline1"],
        payload["headline2"],
        "",
        "## 캡션",
        payload["summary"].strip(),
        "",
        "## 해시태그",
        " ".join(payload["hashtags"]),
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="뉴스 이미지+캡션+메타데이터 저장")
    parser.add_argument("--headline1", required=True, help="제목 1줄")
    parser.add_argument("--headline2", required=True, help="제목 2줄")
    parser.add_argument("--source", required=True, help="이미지 출처")
    parser.add_argument("--summary", required=True, help="인스타 캡션 본문")
    parser.add_argument("--hashtags", required=True, help="공백으로 구분한 해시태그")
    parser.add_argument("--slug", required=True, help="파일명용 키워드")
    parser.add_argument("--article_title", default="", help="원문 기사 제목")
    parser.add_argument("--article_url", default="", help="원문 기사 URL")
    parser.add_argument("--image_url", help="배경 이미지 URL")
    parser.add_argument("--image_path", help="배경 이미지 로컬 경로")
    parser.add_argument("--badge", default=None, help="뱃지 텍스트")
    parser.add_argument("--date", dest="post_date", default=date.today().isoformat(), help="게시 날짜 YYYY-MM-DD")
    parser.add_argument("--output_dir", default=None, help="출력 폴더")
    parser.add_argument("--skip_figma_handoff", action="store_true", help="Figma 핸드오프 파일 생성 안 함")
    args = parser.parse_args()

    post_date = args.post_date
    slug = slugify(args.slug)
    output_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "output",
        "news",
    )
    os.makedirs(output_dir, exist_ok=True)

    paths = build_paths(output_dir, post_date, slug)
    hashtags = normalize_hashtags(args.hashtags)

    generate_news_poster(
        headline1=args.headline1,
        headline2=args.headline2,
        source=args.source,
        image_url=args.image_url,
        image_path=args.image_path,
        badge_text=args.badge,
        output_path=paths["image"],
    )

    payload = {
        "date": post_date,
        "slug": slug,
        "headline1": args.headline1,
        "headline2": args.headline2,
        "source": args.source,
        "summary": args.summary,
        "hashtags": hashtags,
        "article_title": args.article_title,
        "article_url": args.article_url,
        "image_url": args.image_url or "",
        "image_path": args.image_path or "",
        "badge": args.badge or "",
        "image_output": paths["image"],
    }

    write_caption(paths["caption"], payload)
    with open(paths["metadata"], "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    handoff_result = None
    if not args.skip_figma_handoff:
        handoff_result = create_figma_handoff(
            template_id="news_thumbnail",
            slug=slug,
            fields={
                "headline1": args.headline1,
                "headline2": args.headline2,
                "source": args.source,
            },
            source=args.source,
            article_title=args.article_title,
            article_url=args.article_url,
            summary=args.summary,
            hashtags=hashtags,
            image_path=args.image_path,
            image_url=args.image_url,
            post_date=post_date,
        )

    print(f"[완료] 이미지: {paths['image']}")
    print(f"[완료] 캡션: {paths['caption']}")
    print(f"[완료] 메타데이터: {paths['metadata']}")
    if handoff_result:
        print(f"[완료] Figma 핸드오프: {handoff_result['directory']}")


if __name__ == "__main__":
    main()
