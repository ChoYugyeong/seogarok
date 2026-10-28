"""종료 예정 공지 수집·정규화 파이프라인 (seoga).

플랫폼: millie / ridiselect / sam / willa / crema
출력: JSONL, 1줄 1작품 (스키마는 base.Notice 참고)

핵심 원칙:
  - 공개·비로그인 엔드포인트만 사용한다.
  - 실수집 불가 플랫폼은 source_kind="fixture"로 명시하고 절대 실데이터처럼 꾸미지 않는다.
  - 원본 응답은 _cache/ 에 저장해 재현 가능하게 한다.
"""

__version__ = "0.1.0"
