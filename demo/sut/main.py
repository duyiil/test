"""作者自建的最小商品服务。

仓库里没有团队的 demo/sut/main.py，也没有他们预埋缺陷的原文。
本文件是 Phase 2 为了把执行链路跑通而新写的，缺陷只存在于这个服务里。
用例生成器不会导入本模块。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="ZhiTest demo SUT (author-built)")

# 预置数据里的 price 故意是字符串。这是本文件自己的行为，不是从外部缺陷清单抄来的。
PRODUCTS: dict[str, dict[str, object]] = {
    "p-1": {"id": "p-1", "name": "演示水杯", "price": "12.5"},
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "author-demo-sut"}


@app.get("/api/products")
def list_products() -> dict[str, list[dict[str, object]]]:
    return {"items": list(PRODUCTS.values())}


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, object]:
    found = PRODUCTS.get(product_id)
    if found is None:
        # 与一份声明了 404 的契约不一致：未知商品仍返回 200。
        return {"id": product_id, "name": None, "price": None}
    return found


@app.post("/api/products")
def create_product(body: dict[str, object]) -> JSONResponse:
    # 不校验必填、类型、边界和重名。这些缺口写在 demo/sut/README.md。
    new_id = f"p-{len(PRODUCTS) + 1}"
    item = {"id": new_id, "name": body.get("name"), "price": body.get("price")}
    PRODUCTS[new_id] = item
    return JSONResponse(status_code=201, content=item)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9000)
