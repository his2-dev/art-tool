# -*- coding: utf-8 -*-
"""브랜드 프로파일 로더.

한 파이프라인으로 여러 피드를 굴리기 위한 얇은 레이어다. 브랜드 JSON을 읽어
환경변수로 펼쳐놓기만 한다. news_poster / discord_sender 는 그 환경변수를 보고
로고와 발신자명을 바꾼다. 브랜드를 지정하지 않으면 아무것도 건드리지 않으므로
기존 p;art 발행 경로는 이 파일이 있든 없든 동일하게 동작한다.

사용:
    python -m tools.brand --list
    python tools/brand.py --show artnews

    # 다른 스크립트에서
    from tools.brand import apply_brand
    apply_brand("artnews")      # 이 시점부터 환경변수가 세팅된다
"""

import argparse
import io
import json
import os
import sys

# 윈도우 콘솔 기본 코드페이지(cp949)에서 한글·기호 출력이 깨지거나 죽는다.
# 예약 실행 로그도 이 경로로 나오므로 표준 출력을 UTF-8로 고정한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND_DIR = os.path.join(ROOT, "tools", "brands")


class BrandError(RuntimeError):
    pass


def list_brands():
    if not os.path.isdir(BRAND_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(BRAND_DIR) if f.endswith(".json")
    )


def load_brand(name: str) -> dict:
    path = os.path.join(BRAND_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise BrandError(
            f"브랜드 '{name}' 없음. 있는 것: {', '.join(list_brands()) or '(없음)'}"
        )
    # BOM 방어 — 예약 실행이 만든 파일이 섞일 수 있다
    with io.open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def apply_brand(name: str, strict: bool = True) -> dict:
    """브랜드 설정을 환경변수로 펼친다. 설정값이 null이면 건드리지 않는다.

    strict=True 면 로고 파일이 실제로 없을 때 예외를 낸다. 로고가 빠진 채로
    발행되면 다른 브랜드 로고가 붙은 이미지가 나가버리기 때문이다.
    """
    cfg = load_brand(name)

    logo = cfg.get("logo")
    if logo:
        logo_abs = logo if os.path.isabs(logo) else os.path.join(ROOT, logo)
        if not os.path.exists(logo_abs):
            msg = f"[{name}] 로고 파일 없음: {logo_abs}"
            if strict:
                raise BrandError(msg)
            print(f"[경고] {msg} — 기본 로고로 진행", file=sys.stderr)
        else:
            os.environ["NEWS_LOGO_PATH"] = logo_abs

    d = cfg.get("discord") or {}
    for key, env in (
        ("username", "DISCORD_USERNAME"),
        ("embed_title", "DISCORD_EMBED_TITLE"),
        ("embed_color", "DISCORD_EMBED_COLOR"),
    ):
        if d.get(key) is not None:
            os.environ[env] = str(d[key])

    # 웹훅은 값이 아니라 '어느 환경변수에서 읽을지'를 지정한다.
    # 시크릿을 브랜드 JSON에 절대 적지 않기 위해서다 (이 레포는 PUBLIC).
    src = d.get("webhook_env")
    if src and src != "DISCORD_WEBHOOK_URL":
        val = os.environ.get(src)
        if not val:
            raise BrandError(
                f"[{name}] 환경변수 {src} 가 비어 있다. "
                f".env 또는 GitHub Secret에 웹훅을 넣어야 한다."
            )
        os.environ["DISCORD_WEBHOOK_URL"] = val

    os.environ["NEWS_BRAND"] = name
    return cfg


def load_dotenv(path: str = None) -> int:
    """로컬 개발용. .env 를 읽어 아직 없는 키만 환경변수로 넣는다.

    CI에서는 GitHub Secrets가 이미 환경변수로 들어오므로 이 함수는 아무것도 안 한다
    (.env 파일이 없다). 기존 값을 덮어쓰지 않는 것이 핵심이다.
    """
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return 0
    n = 0
    with io.open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="브랜드 프로파일 확인")
    ap.add_argument("--list", action="store_true", help="브랜드 목록")
    ap.add_argument("--show", metavar="BRAND", help="브랜드 설정 출력")
    args = ap.parse_args()

    if args.list:
        for b in list_brands():
            cfg = load_brand(b)
            print(f"  {b:10} {cfg.get('label','')}")
        return 0
    if args.show:
        cfg = load_brand(args.show)
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
