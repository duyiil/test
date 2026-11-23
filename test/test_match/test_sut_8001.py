"""柴诗雨功能：demo/sut 被测服务联调（端口 8001，7 个 bug 可复现）。

对应测试用例 TCM-SUT-001 ~ 008，见本目录 README。
这组测试直接挂 demo/sut/main.py 的 app（进程内 TestClient），
不依赖外部端口；端口 8001 的约定用 TCM-SUT-008 校验 main.py 源码。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
import demo.sut.main as sut_main  # noqa: E402

app = sut_main.app


@pytest.fixture
def sut() -> TestClient:
    # 每个用例重置内存商品表，避免前一个用例创建的数据影响断言
    sut_main.PRODUCTS.clear()
    sut_main.PRODUCTS["p-1"] = {"id": "p-1", "name": "演示水杯", "price": "12.5"}
    with TestClient(app) as test_client:
        yield test_client


def test_bug1_unknown_product_returns_200_not_404(sut: TestClient) -> None:
    """TCM-SUT-001：商品不存在仍返回 200，契约声明 404。"""

    response = sut.get("/api/products/unknown-xyz")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] is None and body["price"] is None


def test_bug2_missing_name_still_created(sut: TestClient) -> None:
    """TCM-SUT-002：POST 缺少 name 仍返回 201。"""

    response = sut.post("/api/products", json={"price": 10.5})
    assert response.status_code == 201


def test_bug3_string_price_accepted(sut: TestClient) -> None:
    """TCM-SUT-003：price 传字符串仍返回 201 并原样保存。"""

    response = sut.post("/api/products", json={"name": "字符串价格商品", "price": "abc"})
    assert response.status_code == 201
    assert response.json()["price"] == "abc"


def test_bug4_zero_price_accepted(sut: TestClient) -> None:
    """TCM-SUT-004：price 为 0 仍被接受，契约最小值 0.01。"""

    response = sut.post("/api/products", json={"name": "零元商品", "price": 0})
    assert response.status_code == 201


def test_bug5_overlong_name_accepted(sut: TestClient) -> None:
    """TCM-SUT-005：name 超过 40 字符仍被接受。"""

    response = sut.post("/api/products", json={"name": "超" * 41, "price": 1.0})
    assert response.status_code == 201


def test_bug6_seed_product_price_is_string(sut: TestClient) -> None:
    """TCM-SUT-006：预置商品 p-1 的 price 是字符串 "12.5"。"""

    response = sut.get("/api/products/p-1")
    assert response.status_code == 200
    body = response.json()
    assert body["price"] == "12.5"
    assert isinstance(body["price"], str)


def test_bug7_duplicate_name_created_twice(sut: TestClient) -> None:
    """TCM-SUT-007：相同 name 重复创建，每次都返回 201。"""

    payload = {"name": "重复商品", "price": 9.9}
    first = sut.post("/api/products", json=payload)
    second = sut.post("/api/products", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    listing = sut.get("/api/products").json()["items"]
    names = [item["name"] for item in listing]
    assert names.count("重复商品") == 2


def test_sut_runs_on_port_8001() -> None:
    """TCM-SUT-008：联调端口约定为 8001（校验 main.py 启动参数）。"""

    source = (REPO_ROOT / "demo" / "sut" / "main.py").read_text(encoding="utf-8")
    assert "port=8001" in source
