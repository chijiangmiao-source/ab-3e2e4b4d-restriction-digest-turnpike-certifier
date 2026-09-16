# Turnpike 重建服务（限制性内切酶图谱重建）

纯后端服务：根据毛细管电泳给出的**任意两切点间距离的多重集**，重建严格递增的
切点序列（Turnpike / 部分酶切问题）。重复距离按出现次数保留，镜像图谱
`{L - x}` 与原图谱视为同解。

- Python 3.13 · FastAPI · Pydantic v2 · pytest
- 核心算法为自实现的回溯重建：计数多重集扣除、可回滚分支剪枝、镜像去重；
  不调用通用约束求解器，也绝不枚举坐标区间（每个分支只考察最大剩余距离
  所隐含的两个候选位置）。

## 快速开始

```bash
# 构建并启动 API（宿主端口默认 8000，可用 API_PORT 覆盖）
API_PORT=9000 docker compose up api

# 一次性验收：等待 API 健康后运行全部验收检查，以退出码报告结果
docker compose up --exit-code-from verify verify
```

本地开发（Python 3.13）：

```bash
pip install -r requirements.txt
pytest                       # 单元 + API 测试
uvicorn app.main:app --port 8000
API_BASE_URL=http://127.0.0.1:8000 python verify.py   # 对运行中的实例做验收
```

交互式接口文档见 `http://localhost:8000/docs`。

## 请求语义

`POST /v1/reconstruct`，请求体为 JSON：

| 字段 | 类型 | 约束 | 含义 |
| --- | --- | --- | --- |
| `length` | 整数 | `2 .. 10^9` | 片段总长度 `L` |
| `cuts` | 整数 | `2 .. 32` | 切点数 `n`（含端点 `0` 与 `L`） |
| `distances` | 整数数组 | 恰好 `n(n-1)/2` 项，每项 `1 .. L` | 任意两切点间距离的多重集；重复值必须保留，顺序无关 |

示例：

```json
{
  "length": 17,
  "cuts": 6,
  "distances": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17]
}
```

非整数值（字符串、浮点、布尔）、缺字段、多字段、越界的 `length`/`cuts`
都会被模式校验拒绝（见下文错误语义）。

## 响应语义

成功时返回 `200`：

```json
{
  "status": "ambiguous",
  "solutions": [[0, 1, 4, 10, 12, 17], [0, 1, 8, 11, 13, 17]],
  "equivalence_classes": 2
}
```

- `status`
  - `unique`：仅一个镜像等价类，`solutions` 给出唯一规范解；
  - `ambiguous`：至少两个等价类，`solutions` 给出**字典序最小的两个不同规范解**；
  - `impossible`：输入合法但无解，`solutions` 为空，不泄露任何半成品。
- **规范解**：镜像集合 `{L - x}` 与原集合同解，每个等价类取二者中字典序
  较小者；解均为含 `0` 与 `L` 的严格递增序列。
- `equivalence_classes`：搜索实际找到的不同镜像等价类总数。
- 每个返回的见证在服务端都重新生成过距离计数，与输入多重集完全一致；
  同一请求重复发送，响应逐字节一致（搜索顺序、字段顺序、排序均确定）。

## 错误语义

所有客户端错误返回结构化信封（索引均为 0 基）：

```json
{
  "error": {
    "code": "distance_out_of_range",
    "message": "distance at index 1 is 0, outside the allowed range [1, 10]",
    "details": {"index": 1, "value": 0, "min": 1, "max": 10}
  }
}
```

| HTTP | `code` | 含义 | `details` |
| --- | --- | --- | --- |
| 422 | `validation_error` | 模式校验失败（类型、取值范围、未知字段等） | `issues`：逐条 `loc`/`type`/`msg` |
| 422 | `distance_count_mismatch` | 距离数量不等于 `n(n-1)/2` | `expected`、`actual`、`first_offending_index`（首个多余元素或首个缺失位置的下标） |
| 422 | `distance_out_of_range` | 距离值越出 `[1, L]`，指出首项 | `index`、`value`、`min`、`max` |
| 503 | `search_budget_exceeded` | 实例超出确定性搜索节点预算（2,000,000 节点） | `node_budget` |

数量校验先于取值校验；两者都只报告首个违规项。

## 项目结构

```
app/
  main.py       FastAPI 入口、校验顺序、见证复算校验
  turnpike.py   回溯重建核心（计数多重集 + 回滚 + 镜像去重）
  schemas.py    Pydantic 请求/响应模型
  errors.py     结构化错误信封与异常处理
tests/          pytest 单元与 API 测试
verify.py       一次性验收脚本（compose 中的 verify 服务）
Dockerfile      python:3.13-slim 镜像
docker-compose.yml  api（API_PORT 覆盖宿主端口）+ verify
```
