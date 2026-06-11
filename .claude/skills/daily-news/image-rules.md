# image_url 규칙 — 회색 배경·저화질 방지의 핵심

`news_url`(Discord 링크용 한국 기사)과 `image_url`(CI가 이미지 추출하는 URL)은 **항상 분리**.
CI는 curl_cffi Chrome 핑거프린트로 우회하지만, Actions IP 자체가 차단된 한국 뉴스 사이트는
실패 → 회색 배경 폴백으로 퀄리티가 망한다.

## ✅ image_url 우선순위

1. **직접 CDN 이미지 URL** (`.jpg`/`.png`/`.webp`로 끝나는 URL) — 항상 통과.
   기사 페이지에서 원본 이미지 주소를 직접 추출하는 것이 가장 확실. **가로 1000px 이상 권장**
2. 한국 영문 매체: `koreaherald.com`, `koreajoongangdaily.joins.com`
3. 국제 컬쳐/패션: `hypebeast.com`, `dezeen.com`, `wallpaper.com`, `vogue.com`, `architecturaldigest.com`
4. 갤러리 공식 영문: `kukjegallery.com`, `pkmgallery.com`, `lvmh.com`
5. 국내 (간헐적 성공): `design.co.kr`, `mk.co.kr`, `chosun.com`, `joongang.co.kr`, `kmib.co.kr`

## ❌ 절대 불가 (CI에서 403 확인됨)

- `*.go.kr`, `kh.or.kr`, `korea.kr` — 정부·공공기관 전반
- `biz.heraldcorp.com`, `news1.kr` 등 한국 주요 뉴스 사이트

## 운영 패턴

한국어 기사 → `news_url`. **같은 소식의 영문 보도를 검색** (`koreaherald.com`, `hypebeast.com` 등) → `image_url`.

## 이미지 사전 검증 (후보 확정 전)

- image_url의 실제 이미지 크기 확인 — **가로 800px 미만이면 다른 출처를 찾거나 후보 탈락**
- 저화질 원본은 CI에서 블러 배경 처리되어 분위기만 남는다 (블러는 최후 수단)
- 인물 단독 증명사진·로고·포스터 글씨 위주 이미지는 감점

## 화질 파이프라인 참고 (코드가 자동 처리 — 별도 조치 불필요)

- CI는 og:image뿐 아니라 기사 본문 이미지까지 스캔해 가장 고해상도 이미지를 채택
- 원본이 작으면 출력 배율 자동 하향 (과업스케일 방지), 업스케일 2.4배 초과 시 블러 배경
