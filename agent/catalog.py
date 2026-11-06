"""상품 카탈로그: data/products.json을 읽어 AI에게 줄 텍스트로 만든다."""

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "products.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def products_by_id() -> dict[str, dict]:
    return {p["id"]: p for p in load_catalog()["products"]}


def catalog_text() -> str:
    """시스템 프롬프트에 넣을 카탈로그 전문. 바이트가 매번 같아야 프롬프트 캐시가 맞는다."""
    cat = load_catalog()
    header = (
        f"[상품 카탈로그] {cat['bank']} / 확인일 {cat['checked_at']}\n"
        f"{cat['source_note']}\n"
    )
    body = json.dumps(cat["products"], ensure_ascii=False, indent=1, sort_keys=True)
    return header + body
