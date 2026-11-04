"""演示接口契约。

这是平台侧手写的契约，供 Mock Provider 使用。
它不读取 demo/sut 的实现，也不包含该服务里的缺陷结论。
"""

from __future__ import annotations

DEMO_CONTRACT: list[dict[str, object]] = [
    {
        "method": "GET",
        "path": "/api/products",
        "summary": "商品列表",
        "requiresAuth": False,
        "query": [{"name": "page", "type": "integer", "required": False, "minimum": 1}],
        "pathParams": [],
        "body": None,
        "responses": {
            "200": {
                "type": "object",
                "properties": {"items": {"type": "array"}},
            }
        },
    },
    {
        "method": "GET",
        "path": "/api/products/{id}",
        "summary": "商品详情",
        "requiresAuth": False,
        "query": [],
        "pathParams": [{"name": "id", "type": "string", "required": True, "example": "p-1"}],
        "body": None,
        "responses": {
            "200": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                },
            },
            "404": {"description": "商品不存在"},
        },
    },
    {
        "method": "POST",
        "path": "/api/products",
        "summary": "创建商品",
        "requiresAuth": False,
        "query": [],
        "pathParams": [],
        "body": {
            "type": "object",
            "required": ["name", "price"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 40, "example": "示例商品"},
                "price": {"type": "number", "minimum": 0.01, "maximum": 100000, "example": 10.5},
            },
        },
        "responses": {
            "201": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                },
            },
            "400": {"description": "参数不合法"},
        },
    },
]
