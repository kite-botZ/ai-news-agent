"""探测一批常见的 RSS 源，看哪些能通。

不改项目代码，只是临时验证网络和源可用性。
"""

import httpx

# 候选 RSS 源（从各种渠道搜集的，不保证都能通）
CANDIDATES = [
    # ============ 科技 / AI ============
    ("IT 之家", "https://www.ithome.com/rss/"),
    ("机器之心", "https://www.jiqizhixin.com/rss"),
    ("量子位", "https://www.qbitai.com/feed"),
    ("36 氪", "https://36kr.com/feed"),
    ("雷锋网", "https://www.leiphone.com/feed"),
    ("少数派", "https://sspai.com/feed"),

    # ============ 财经 ============
    ("第一财经", "https://www.yicai.com/rss/"),

    # ============ 国内综合 ============
    ("虎嗅", "https://www.huxiu.com/rss/0.xml"),
    ("爱范儿", "https://www.ifanr.com/feed"),
    ("InfoQ 中文", "https://www.infoq.cn/feed"),

    # ============ 国外（可能不通）============
    ("Hacker News", "https://hnrss.org/frontpage"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
]


def probe(name: str, url: str) -> tuple[str, bool, str]:
    """探测单个 RSS 源。返回 (name, 是否成功, 说明)。"""
    try:
        resp = httpx.get(
            url,
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code != 200:
            return (name, False, f"HTTP {resp.status_code}")

        # 简单判断是不是 XML
        content = resp.text[:200]
        if "<?xml" in content or "<rss" in content or "<feed" in content:
            return (name, True, f"OK ({len(resp.content)} bytes)")
        else:
            return (name, False, "返回内容不是 RSS/XML")

    except httpx.TimeoutException:
        return (name, False, "超时")
    except Exception as e:
        return (name, False, f"错误：{type(e).__name__}")


print(f"探测 {len(CANDIDATES)} 个 RSS 源，超时 10 秒\n")

ok_list = []
fail_list = []

for name, url in CANDIDATES:
    name, ok, msg = probe(name, url)
    status = "✅" if ok else "❌"
    print(f"{status} {name:14s} {msg}")
    print(f"     {url}")
    if ok:
        ok_list.append((name, url))
    else:
        fail_list.append((name, url))
    print()

print("=" * 60)
print(f"✅ 可用的源（{len(ok_list)} 个）：")
for name, url in ok_list:
    print(f"   - {name}: {url}")

print()
print(f"❌ 不可用的源（{len(fail_list)} 个）：")
for name, url in fail_list:
    print(f"   - {name}: {url}")