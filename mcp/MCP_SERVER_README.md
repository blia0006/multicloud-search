# multicloud-search MCP Server

> 本文件即 MCP 模块的 README（为避免与项目根目录 `README.md` 同名混淆，命名为 `MCP_SERVER_README.md`）。
> 项目总览见 [`../README.md`](../README.md)，完整接口文档见 [`../docs/MCP_USAGE.md`](../docs/MCP_USAGE.md)。

四家云厂商（腾讯云 / 阿里云 / 华为云 / 火山引擎）产品文档检索与 ECS/CVM 价格对比的 MCP 服务。

- 传输：**stdio**；协议：JSON-RPC 2.0 / MCP `2024-11-05`
- 依赖：**仅 Python 标准库**（Python 3.8+）
- 数据：`../data/products.json`（176 个产品）、`../data/ecs_prices.json`（4 地域 × 5 规格 × 4 厂商）

## 工具

| 工具 | 说明 |
| --- | --- |
| `search_cloud_docs` | 四家产品文档聚合搜索（支持缩写与跨云同类召回） |
| `compare_ecs_price` | 同地域同配置的四家 ECS/CVM 刊例价对比 + 价差结论 |
| `find_equivalent_products` | 跨云同类产品对照（CVM ↔ ECS ↔ ECS ↔ ECS） |
| `list_cloud_products` | 按厂商/类目列出收录产品 |
| `list_cloud_regions` | 统一地域 → 四家地域 ID 映射 |

## 接入

```json
{
  "mcpServers": {
    "multicloud-search": {
      "command": "python3",
      "args": ["/绝对路径/课题一/mcp/multicloud_mcp_server.py"]
    }
  }
}
```

## 快速验证

```bash
python3 ../tools/mcp_selftest.py                      # 18 项检查
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 multicloud_mcp_server.py
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_cloud_docs","arguments":{"query":"对象存储","limit":4}}}' | python3 multicloud_mcp_server.py
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"compare_ecs_price","arguments":{"vcpu":4,"memory_gb":8}}}' | python3 multicloud_mcp_server.py
```

完整参数说明、返回结构与更多调用示例见 [`../docs/MCP_USAGE.md`](../docs/MCP_USAGE.md)。
