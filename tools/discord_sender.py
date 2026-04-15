"""
Discord webhook으로 뉴스 썸네일 + 정보를 전송하는 유틸리티.
Windows에서 curl 한글 인코딩 깨짐 방지를 위해 Python requests 사용.
"""

import json
import requests


WEBHOOK_URL = "https://discord.com/api/webhooks/1492898081841217748/vj4X1wToV4HD-rPqv7DyQ2Zxg3dUYlZWOiq6uft0OZw9SlLTJmtgrEwi29IwdqdSd4aM"
APP_URL = "https://artmag-news-tool.streamlit.app"


def send_news_to_discord(
    image_path: str,
    news_title: str,
    news_url: str,
    headline1: str,
    headline2: str,
    source: str,
    caption: str,
    candidates: list[dict] = None,
):
    """Discord webhook으로 뉴스 썸네일 이미지와 정보를 전송합니다.

    Args:
        image_path: 생성된 PNG 파일 경로
        news_title: 선택된 뉴스 제목
        news_url: 선택된 뉴스 URL
        headline1: 헤드라인 1줄
        headline2: 헤드라인 2줄
        source: 출처 (예: © W Korea)
        caption: 인스타 캡션 (해시태그 포함)
        candidates: 다른 후보 기사 리스트 [{"title": ..., "url": ...}, ...]
    """
    import os
    filename = os.path.basename(image_path)

    # 후보 기사 텍스트
    candidates_text = ""
    if candidates:
        lines = []
        for i, c in enumerate(candidates, 1):
            lines.append(f"{i}. {c['title']}\n{c['url']}")
        candidates_text = "\n".join(lines)

    embed = {
        "title": "🎨 p.art_mag 오늘의 뉴스",
        "color": 3447003,
        "image": {"url": f"attachment://{filename}"},
        "fields": [
            {
                "name": "📰 선택된 뉴스",
                "value": f"{news_title}\n{news_url}",
                "inline": False,
            },
            {
                "name": "📝 헤드라인",
                "value": f"{headline1} / {headline2}",
                "inline": True,
            },
            {
                "name": "📸 출처",
                "value": source,
                "inline": True,
            },
            {
                "name": "🖊️ 캡션",
                "value": caption[:1024],  # Discord field 최대 1024자
                "inline": False,
            },
        ],
    }

    if candidates_text:
        embed["fields"].append({
            "name": "📋 다른 후보 기사",
            "value": candidates_text[:1024],
            "inline": False,
        })

    embed["fields"].append({
        "name": "🔧 직접 만들기",
        "value": f"[썸네일 생성기 열기]({APP_URL})",
        "inline": False,
    })

    payload = {"embeds": [embed]}

    with open(image_path, "rb") as f:
        files = {"file": (filename, f, "image/png")}
        r = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps(payload, ensure_ascii=False)},
            files=files,
        )

    if r.status_code == 200:
        print(f"[완료] Discord 전송 성공")
    else:
        print(f"[경고] Discord embed 실패 ({r.status_code}), 텍스트로 재시도")
        # fallback: 텍스트만
        fallback = (
            f"🎨 오늘의 뉴스: {news_title}\n"
            f"📝 헤드라인: {headline1} / {headline2}\n"
            f"🔗 기사: {news_url}\n"
            f"🖊️ 캡션: {caption[:500]}\n"
            f"🔧 직접 만들기: {APP_URL}"
        )
        requests.post(WEBHOOK_URL, json={"content": fallback})

    return r.status_code


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discord로 뉴스 썸네일 전송")
    parser.add_argument("--image", required=True, help="이미지 파일 경로")
    parser.add_argument("--title", required=True, help="뉴스 제목")
    parser.add_argument("--url", required=True, help="뉴스 URL")
    parser.add_argument("--headline1", required=True)
    parser.add_argument("--headline2", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--caption", required=True)
    args = parser.parse_args()

    send_news_to_discord(
        image_path=args.image,
        news_title=args.title,
        news_url=args.url,
        headline1=args.headline1,
        headline2=args.headline2,
        source=args.source,
        caption=args.caption,
    )
