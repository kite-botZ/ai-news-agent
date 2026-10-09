"""测试 fetch_rss 工具。"""
from app.agent.tools import execute_tool

print("=== 拉取 IT 之家 RSS ===")
result = execute_tool("fetch_rss", {
    "url": "https://www.ithome.com/rss/",
    "limit": 5,
})

if "error" in result:
    print("错误：", result["error"])
else:
    print(f"共 {result['count']} 条新闻：")
    for i, news in enumerate(result["news"], 1):
        print(f"\n{i}. {news['title']}")
        print(f"   {news['link']}")
        print(f"   {news['summary'][:100]}...")