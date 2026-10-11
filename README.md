# AI 新闻助手 · Daily AI News Agent

一个基于 **ReAct 循环 + Function Calling** 的每日 AI 新闻简报 Agent。

用户填写自己的订阅偏好（关注的关键词、话题），Agent 会自己去拉取 RSS 新闻源、按偏好筛选、
生成一份 Markdown 简报并存档。工具调用顺序（调哪个工具、调几次、什么时候停）**完全由 LLM 决定**，
不是硬编码的线性流程。

> 对应笔试题：**选项 A · Agent Loop —— 每日 AI 新闻助手**

---

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / uvicorn |
| Agent | 手写 ReAct 循环（未用 LangChain 等框架）+ OpenAI 兼容的 Function Calling |
| 大模型 | 硅基流动（SiliconFlow），模型可在 `.env` 里配置 |
| 前端 | Vue 3 + TypeScript + Vite + vue-router + axios |
| 生成时机 | 进入新闻页时按需自动生成（当天已有则跳过） |
| 存储 | 文件系统（每用户一个目录），无数据库 |
| 测试 | pytest，96 个用例，不联网、不调模型 |

---

## 快速开始

### 0. 前置

- Python 3.11+
- Node.js 18+
- 一个[硅基流动](https://siliconflow.cn)的 API Key

### 1. 后端

```bash
cd backend

# 建虚拟环境（可选）
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# 装依赖（依赖清单在项目根目录）
pip install -r ../requirements.txt

# 配置密钥
cp .env.example .env
# 然后编辑 .env，把 SILICONFLOW_API_KEY 换成你自己的
```

`.env` 内容：

```ini
SILICONFLOW_API_KEY=sk-你的key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
MODEL_NAME=Qwen/Qwen3-8B

# 思考（思维链）参数，见下面「生成速度」一节
ENABLE_THINKING=true
THINKING_BUDGET=100
```

启动后端：

```bash
python run.py
# 服务跑在 http://localhost:3000，接口文档 http://localhost:3000/docs
```

**创建演示账号**（可选，data/ 目录被 git 忽略，clone 下来是空的）：

```bash
python seed_demo.py     # 会创建 alice / bob / charlie 三个账号
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

前端通过 Vite 代理把 `/api` 转发到 `http://localhost:3000`，所以后端必须先起来。

### 3. 用起来

1. 首页输入用户名（如 `alice`）→ 不存在会提示创建
2. 进「偏好设置」填关键词和话题
3. 进入新闻页后**当天没有简报会自动生成**，右侧 AI 面板逐字打出；
   想重新生成也可以点「✨ 生成今日简报」
4. 历史简报在右侧下方，点开可查看

---

## 功能

- **用户管理**：创建用户、读写订阅偏好
- **新闻聚合**：`/api/news` 并发拉取 6 个 RSS 源，按源轮流交错合并去重后返回（带 10 分钟缓存）
- **AI 简报生成**：
  - 同步接口 `POST .../generate`（阻塞）
  - **SSE 流式接口** `POST .../generate-stream`（打字机效果，前端主用）
- **历史简报**：按日期存档，可回看
- **自动生成**：进入新闻页时若当天还没有简报，自动生成一份（不重复消耗模型调用）
- **前端**：登录 → 偏好设置 → 新闻流 + AI 面板三页

---

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/` | 健康检查 |
| `POST` | `/api/users` | 创建用户 |
| `GET` | `/api/users/{username}/preferences` | 读偏好 |
| `PUT` | `/api/users/{username}/preferences` | 更新偏好 |
| `GET` | `/api/users/{username}/briefs` | 列出历史简报 |
| `GET` | `/api/users/{username}/briefs/{date}` | 读某份简报 |
| `POST` | `/api/users/{username}/generate` | 同步生成简报 |
| `POST` | `/api/users/{username}/generate-stream` | **SSE 流式生成** |
| `GET` | `/api/news` | 拉取合并后的新闻列表 |

交互式文档：启动后访问 http://localhost:3000/docs

---

## Agent 是怎么工作的

`backend/app/agent/` 下四个文件：

```
prompts.py   系统提示词（角色定义 + 工作流程 + RSS 源清单）
llm.py       封装硅基流动的 LLM 调用（普通 / 流式）
react.py     ReAct 循环（run_react 一次性 / run_react_stream_realtime 真流式）
tools.py     6 个工具 + JSON Schema + 沙箱
```

ReAct 循环：

1. 把 system prompt + 用户消息 + 工具 schema 发给模型
2. 模型决定：直接回答，还是返回 `tool_calls`
3. 后端执行工具，结果作为 `tool` 消息追加进历史
4. 带着新历史再问模型
5. 重复直到模型不再调工具，或达到 `MAX_ITERATIONS`（默认 10）

**6 个工具**（题目要求至少 5 个）：

| 工具 | 作用 |
|---|---|
| `list_dir(path)` | 列出目录内容 |
| `read_file(path)` | 读取文件 |
| `search_content(keyword, dir)` | 按关键词搜索文件内容 |
| `write_file(path, content)` | 写入文件 |
| `bash(command)` | 执行 shell 命令（白名单） |
| `fetch_rss(url, limit)` | 拉取 RSS 新闻源（白名单） |

### 工具调用顺序由 LLM 决定

提示词里**不写**「第一步调 A、第二步调 B」，也不规定每个工具调几次。只给目标和约束，
顺序、数量、何时停，全部交给模型判断。

这带来两个直接后果，都能观察到：

- **每次跑的轨迹都不一样**。同一句任务连跑 6 次，实测出现过：
  `read_file → fetch_rss×3 → write_file`（4 轮）、
  `read_file → fetch_rss×3 → search_content → write_file`（5 轮）、
  `read_file → fetch_rss → fetch_rss → fetch_rss → fetch_rss → fetch_rss → write_file`（8 轮）。
  **拉几个源、分几轮拉、要不要查历史简报，都是模型当场决定的**，代价是耗时在 49~88 秒之间浮动。
- **不是每个工具都会被用到**。`search_content` 只在模型判断"该看看历史简报、避免和昨天重复"
  时才出现；`list_dir` / `bash` 在这次任务里没必要，模型就没调。工具是**被场景需要**的，不是凑数。

提示词里只有一条预算提示（"3 个源左右通常够了"）用来控成本——那是**约束**，不是**顺序**。

### 生成速度：187 秒 → 约 65 秒

一次完整生成原本要 **187 秒**。加计时打点后发现时间几乎全花在模型上
（`llm_seconds_total` 186.6s / `wall_total` 187.7s），RSS 抓取和工具执行加起来不到 1 秒。
逐项改下来：

| 改动 | 效果 |
|---|---|
| `THINKING_BUDGET=100` 给思考设上限 | 单轮从约 37 秒降到 5~8 秒 |
| 最后一条回复不复述简报，正文只写进文件 | 省掉一整轮（约 30 秒） |
| 提示词要求多个 `fetch_rss` 同轮一起发出 | 拉源从 4~5 轮压到 1 轮 |
| RSS 结果只把 `title/link/summary/source` 给模型 | 写简报那轮 prompt token 从 4896 降到约 3200 |

最终实测 6 次：**49 / 58 / 67 / 78 / 79 / 88 秒，平均约 65 秒**。

**为什么不是简单关掉思考**：Qwen3 是混合推理模型，思考占了输出 token 的 95%
（一轮只调个 `read_file`，却能生成 716 个 token）。但实测直接 `enable_thinking=false`
会让模型**失去规划能力**——10 轮全在拉新闻、一次 `write_file` 都不调，任务直接失败。
所以改成保留思考、只给预算上限。

剩下三分之一的时间是写简报那一轮本身（要生成 600 多个 token），
这是模型的输出速度（约 20 token/s），调提示词解决不了，只能换模型——这里刻意不换。

**耗时波动（49~88 秒）来自模型自己的决策**：拉几个源、要不要查历史简报，
都由它判断，不是代码写死的。这不是不稳定，正是①「顺序由 LLM 决定」的直接体现。

### 跟着这个改动一起暴露出来的坑

提速过程中撞到两个**静默错误**，都补了兜底和用例：

- **模型偶尔不调 `write_file`**（实测 6 次出现 1 次），直接把简报当成对话回复吐出来。
  原本要用 `_find_saved_path` 找文件落库，这时它会捞到**上一次**生成的简报，
  前端于是弹出一份旧简报、还显示成刚生成的。→ 现在按本次生成的开始时间过滤
  （`since` 参数），并且模型真忘了写时由后端 `_persist_fallback` 替它落盘。
- **前端原本显示的是模型的复述，不是文件内容**。所以"让模型别复述"一开始只是省时间，
  差点变成"弹窗变空白"。→ 改成 `done` 事件带 `brief_id`，前端拿它
  调 `GET /api/users/{u}/briefs/{id}` 读文件。简报只写一次，展示直接读盘。

### 安全设计

- **沙箱**：所有文件操作限制在 `data/users/<username>/` 内，`_safe_path()` 用 `resolve()` + `relative_to()` 双重校验防目录穿越
- **沙箱靠显式传参，不靠全局状态**：`execute_tool(name, args, sandbox_dir=...)` 逐次传入，
  底层仍用 `contextvars` 兜住 `_safe_path()`，但 `set` 和工具调用在同一个同步块里，
  中间没有线程池跳转。**这里踩过一个大坑**：早先是「进生成器时 `set_sandbox()` 设一次」，
  而 Starlette 消费同步生成器走 `iterate_in_threadpool`——每 `next()` 一次就是一次新的
  线程池调度，`anyio` 每次都从事件循环线程重新拷一份上下文。于是生成器里设的沙箱
  下一次恢复就没了，静默退回 `data/`：表现为 **Agent 读不到本用户的 `preferences.json`**，
  却照样硬写一份简报（不报错，只是内容不对）；更糟的是隔离失效，A 用户能读到 B 用户的文件。
  回归用例见 `tests/test_react.py::test_sandbox_survives_starlette_threadpool`——
  它必须用和 Starlette **一样的方式**消费生成器，用 `list()` 直接消费是抓不到的
- **命令白名单**：`bash` 只允许 `ls/cat/echo/pwd/date/wc/head/tail/grep/find`（Windows 下自动映射成 `dir/type`，并把 GNU 短选项翻成 cmd 的写法，如 `grep -i` → `findstr /i`）
- **参数也要过沙箱**：白名单只管得住命令名。`cat ../../.env` 的命令名是合法的 `cat`，但参数能读到沙箱外的 API Key——所以每个路径参数都要再走一遍 `_safe_path`
- **禁止管道 / 重定向 / 命令连接符**：`echo hi; rm -rf /` 的命令名同样是合法的 `echo`，所以 `; | & > <` 和变量展开一律拒绝
- **SSRF 防护**：`fetch_rss` 只允许 `app/rss.py` 里 `RSS_SOURCES` 白名单内的源（校验的是完整 URL 相等，不是包含关系）
- **密钥**：走环境变量，`.env` 已被 `.gitignore` 忽略

上面这几条都有对应的 pytest 用例，不是只写在文档里。

---

## 简报什么时候生成

题目要求「每天自动为用户整理」，实现方式是**进入页面时按需生成**：

1. 前端进入新闻页 → 拉取该用户当天已有的简报
2. 当天还没有 → 自动调 SSE 流式接口生成一份（右侧面板看到实时进度）
3. 当天已有 → 直接展示，不重复生成

这样用户不需要手动点按钮，也不会重复消耗模型调用。

生成过程中右侧面板不是干等的，会逐条显示 Agent 正在做什么
（`📖 正在读取偏好…` → `📰 正在拉取新闻源…` → `拿到 5 条新闻` → `💾 正在保存简报…`），
这些事件后端一直在推，前端早先直接丢掉了，后来才接上。

生成完成后弹窗里的正文是**从保存的文件读回来的**（`done` 事件带 `brief_id`），
不是模型在对话里复述的——模型只输出一句「简报已生成」。理由见上面「生成速度」一节。

---

## 测试

### 自动化测试（pytest）

```bash
cd backend
python -m pytest        # 96 个用例，约 1 秒
```

全部**不联网、不调模型**，所以可以随便跑、不花钱：

| 文件 | 覆盖什么 |
|---|---|
| `tests/test_sandbox.py` | 目录穿越（相对路径、绝对路径、`a/../` 绕回）全部被拦，并且验证越界文件**确实没有被创建出来** |
| `tests/test_tools.py` | bash 白名单 + 参数沙箱 + 管道拦截、`fetch_rss` 白名单（防 SSRF）、schema 与实现一一对应、缺参数时的兜底、显式沙箱与全局沙箱的优先级 |
| `tests/test_users.py` | 用户名与简报文件名两条正则（用户可控字符串直接拼进路径的地方）、偏好字段白名单、简报排序 |
| `tests/test_rss.py` | 多源合并必须**按源轮流交错**（否则后面的源会被 `max_total` 整段切掉）、单源失败不影响整体、按 link 去重 |
| `tests/test_react.py` | ReAct 循环的三个出口（直接回答 / 调完工具回答 / 撞到 `MAX_ITERATIONS`）、`tool_call_id` 配对、沙箱跨线程池仍然有效（回归） |

`test_react.py` 把 `react.chat` 换成一个按脚本应答的假 LLM，循环就退化成一个普通状态机，
每条分支都能单独断言——测 LLM 应用不等于必须真的调 API。
`test_users.py` 则把用户根目录指到 `tmp_path`，不碰真实的 `data/`。

### 排查脚本

`backend/` 下有两个**需要联网 / 调模型**的脚本，用来排查环境问题——
它们不是自动化测试，所以命名是 `check_*` 而不是 `test_*`：

```bash
cd backend
python check_llm.py           # .env 里的 key / base_url / 模型名配对了没有
python check_rss_sources.py   # 探测一批候选 RSS 源，看哪些当前能通
```

`check_rss_sources.py` 的候选列表里也有**没进白名单**的源，所以它同时用来挑选和替换新闻源。

---

## 目录结构

```
ai-news-agent/
├── backend/
│   ├── app/
│   │   ├── agent/            # Agent 核心
│   │   │   ├── prompts.py    # 系统提示词
│   │   │   ├── llm.py        # LLM 调用封装
│   │   │   ├── react.py      # ReAct 循环
│   │   │   ├── tools.py      # 工具定义与执行
│   │   │   └── service.py    # 业务封装（生成简报）
│   │   ├── routes/
│   │   │   ├── users.py      # 用户 / 简报接口
│   │   │   └── news.py       # 新闻接口
│   │   ├── rss.py            # RSS 抓取解析（工具和接口共用）
│   │   ├── users.py          # 用户数据管理
│   │   ├── config.py         # 配置
│   │   └── main.py           # FastAPI 入口
│   ├── tests/                # pytest 用例（不联网、不调模型）
│   │   ├── conftest.py
│   │   ├── test_sandbox.py   # 沙箱隔离
│   │   ├── test_tools.py     # 工具白名单 / schema 一致性
│   │   ├── test_users.py     # 用户名校验 / 偏好读写
│   │   ├── test_rss.py       # 多源交错合并
│   │   └── test_react.py     # ReAct 循环（用假 LLM）
│   ├── pytest.ini            # testpaths 限定为 tests/
│   ├── check_llm.py          # 排查：API 通不通
│   ├── check_rss_sources.py  # 排查：哪些 RSS 源能通
│   ├── data/users/           # 用户数据（git 忽略）
│   ├── seed_demo.py          # 演示账号种子脚本
│   └── run.py                # 启动脚本
├── frontend/
│   └── src/
│       ├── views/            # Home / Preferences / NewsFeed
│       ├── api/request.ts    # axios 封装
│       ├── utils/markdown.ts # 简报 Markdown 渲染
│       └── router/
└── requirements.txt
```

---

## 已知取舍

- 存储用文件系统而非数据库：题目没要求，且「每个用户一个目录」本身就是一个清晰的
  沙箱边界，配合 Agent 的文件工具更自然
- 未引入 LangChain / LangGraph：手写循环更能体现对 ReAct 和 function calling 的理解
- `/api/news` 的缓存是进程内存缓存，多进程部署时应换成 Redis
