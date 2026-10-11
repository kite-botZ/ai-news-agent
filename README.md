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
| 定时任务 | APScheduler（每天自动为所有用户生成简报） |
| 存储 | 文件系统（每用户一个目录），无数据库 |

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
3. 回到新闻页，点「✨ 生成今日简报」→ 右侧 AI 面板逐字打出简报
4. 历史简报在右侧下方，点开可查看

---

## 功能

- **用户管理**：创建用户、读写订阅偏好
- **新闻聚合**：`/api/news` 并发拉取 9 个 RSS 源，合并去重后返回（带 10 分钟缓存）
- **AI 简报生成**：
  - 同步接口 `POST .../generate`（阻塞）
  - **SSE 流式接口** `POST .../generate-stream`（打字机效果，前端主用）
- **历史简报**：按日期存档，可回看
- **定时任务**：每天固定时间自动为所有用户生成简报
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

### 安全设计

- **沙箱**：所有文件操作限制在 `data/users/<username>/` 内，`_safe_path()` 用 `resolve()` + `relative_to()` 双重校验防目录穿越
- **并发隔离**：当前沙箱用 `contextvars` 保存，多个请求互不干扰
- **命令白名单**：`bash` 只允许 `ls/cat/echo/pwd/date/wc/head/tail/grep/find`（Windows 下自动映射成 `dir/type` 等）
- **SSRF 防护**：`fetch_rss` 只允许 `app/rss.py` 里 `RSS_SOURCES` 白名单内的源
- **密钥**：走环境变量，`.env` 已被 `.gitignore` 忽略

---

## 定时任务

`backend/app/scheduler.py` 用 APScheduler 起一个后台线程，每天固定时间遍历所有用户、
各生成一份简报（对应题目「每天自动整理」的要求）。

环境变量控制：

```ini
SCHEDULER_ENABLED=true      # 是否开启，默认 true
BRIEF_SCHEDULE_HOUR=8       # 每天几点，默认 8
BRIEF_SCHEDULE_MINUTE=0     # 分钟，默认 0
```

> 本地调试时如果不想让它自动跑，设 `SCHEDULER_ENABLED=false`。

---

## 手工测试脚本

`backend/` 下有几个可直接运行的脚本（都带 `if __name__ == "__main__"` 守卫，
不会被 pytest 误收集）：

```bash
cd backend
python test_llm.py          # 测 LLM 通不通
python test_tools.py        # 测 6 个工具
python test_react.py        # 测 ReAct 循环
python test_news_agent.py   # 完整跑一次简报生成
python test_users.py        # 测用户管理
python test_fetch_rss.py    # 测 RSS 抓取
python test_rss_probe.py    # 探测哪些 RSS 源可用
```

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
│   │   ├── scheduler.py      # 定时任务
│   │   ├── users.py          # 用户数据管理
│   │   ├── config.py         # 配置
│   │   └── main.py           # FastAPI 入口
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
