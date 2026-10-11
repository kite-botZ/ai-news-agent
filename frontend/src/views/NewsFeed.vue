<template>
  <div class="feed-page">
    <!-- 顶部栏 -->
    <header class="topbar">
      <div class="brand">
        <span class="brand-icon">📰</span>
        <span class="brand-name">AI 新闻助手</span>
      </div>
      <div class="user-area">
        <span class="username">👤 {{ username }}</span>
        <button class="top-btn" @click="goPreferences">偏好设置</button>
        <button class="top-btn" @click="goHome">切换用户</button>
      </div>
    </header>

    <!-- 主体：左新闻右AI -->
    <div class="main">
      <!-- 左：新闻列表 -->
      <div class="news-column">
        <div class="news-heading">
          <h2>今日新闻</h2>
          <button class="refresh-btn" :disabled="loading" @click="loadNews(true)">
            {{ loading ? '加载中…' : '🔄 刷新' }}
          </button>
        </div>

        <div v-if="loading" class="loading">加载新闻中…</div>
        <div v-else-if="news.length === 0" class="empty">暂无新闻</div>
        <div v-else class="news-grid">
          <a
            v-for="(item, idx) in news"
            :key="idx"
            :href="item.link"
            target="_blank"
            class="news-card"
          >
            <div class="news-img-wrap">
              <img
                v-if="item.image"
                :src="item.image"
                class="news-img"
                loading="lazy"
                referrerpolicy="no-referrer"
                @error="onImgError"
              />
              <div v-else class="news-img-placeholder">📄</div>
            </div>
            <div class="news-body">
              <span class="news-source">{{ sourceName(item) }}</span>
              <h3 class="news-title">{{ item.title }}</h3>
              <p class="news-summary">{{ item.summary }}</p>
            </div>
          </a>
        </div>
      </div>

      <!-- 右：AI 助手面板 -->
      <aside class="ai-panel">
        <div class="ai-header">
          <span class="ai-avatar">🤖</span>
          <div>
            <div class="ai-title">AI 新闻助手</div>
            <div class="ai-sub">
              {{ generating ? '正在生成…' : '专属简报' }}
            </div>
          </div>
        </div>

        <div class="ai-body">
          <!-- 生成按钮 -->
          <button
            v-if="!generating"
            class="ai-btn"
            @click="generateBrief"
          >
            ✨ 生成今日简报
          </button>
          <button
            v-else
            class="ai-btn stop-btn"
            @click="stopGenerate"
          >
            ⏹ 停止生成
          </button>

          <!-- 生成中：工具调用进度；生成完：从文件读回的简报正文 -->
          <div v-if="generating || progressLog.length || briefContent" class="brief-panel">
            <div class="brief-head">
              <span>{{ generating ? '📝 正在生成简报…' : '📄 简报内容' }}</span>
              <span v-if="generating" class="typing-cursor">▌</span>
            </div>

            <ul v-if="generating" class="progress-list">
              <li v-for="(line, i) in progressLog" :key="i">{{ line }}</li>
              <li v-if="streamText.trim()" class="progress-done">{{ streamText.trim() }}</li>
            </ul>

            <div
              v-else-if="briefContent"
              class="brief-text markdown"
              v-html="renderedBrief"
            ></div>

            <ul v-else class="progress-list">
              <li v-for="(line, i) in progressLog" :key="i">{{ line }}</li>
            </ul>
          </div>

          <!-- 历史简报 -->
          <div class="history">
            <h4>📚 历史简报</h4>
            <div v-if="briefs.length === 0" class="history-empty">
              暂无简报
            </div>
            <ul v-else class="history-list">
              <li
                v-for="b in briefs"
                :key="b.date"
                @click="viewBrief(b.date)"
              >
                <span class="history-date">{{ formatDate(b.date) }}</span>
                <span class="history-size">{{ formatSize(b.size) }}</span>
              </li>
            </ul>
          </div>
        </div>
      </aside>
    </div>

    <!-- 简报弹窗（生成完成后弹出） -->
    <div v-if="showModal" class="modal-backdrop" @click.self="showModal = false">
      <div class="modal">
        <div class="modal-head">
          <div>
            <h2>{{ modalDate }}</h2>
            <p class="modal-subtitle">AI 每日新闻简报</p>
          </div>
          <button class="modal-close" @click="showModal = false">✕</button>
        </div>
        <div class="modal-content markdown" v-html="renderedModal"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const username = String(route.params.username || '')

// ==================== 新闻列表 ====================
const loading = ref(true)
const news = ref<any[]>([])

/**
 * 拉取新闻列表。
 * refresh=true 时绕过后端 10 分钟缓存，只有「刷新」按钮会传 true——
 * 不传的话点刷新在缓存窗口内看不到任何变化。
 */
async function loadNews(refresh = false) {
  loading.value = true
  try {
    news.value = await request.get('/news', {
      params: { limit: 30, refresh },
    }) as any
  } catch (e: any) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

function sourceName(item: any) {
  // 后端已经给了中文源名，优先用它
  if (item?.source_name) return item.source_name
  const url: string = item?.source || ''
  if (!url) return ''
  if (url.includes('ithome')) return 'IT 之家'
  if (url.includes('ifanr')) return '爱范儿'
  if (url.includes('qbitai')) return '量子位'
  if (url.includes('sspai')) return '少数派'
  if (url.includes('leiphone')) return '雷锋网'
  if (url.includes('infoq')) return 'InfoQ'
  if (url.includes('hnrss')) return 'Hacker News'
  if (url.includes('techcrunch')) return 'TechCrunch'
  if (url.includes('theverge')) return 'The Verge'
  return '新闻'
}

// ==================== AI 简报生成 ====================
const generating = ref(false)
const progressLog = ref<string[]>([])   // 工具调用进度（人话），生成过程中实时显示
const streamText = ref('')              // 模型输出的文字（正常情况下只有一句总结）
const briefContent = ref('')            // 简报正文——生成完从后端文件读回来
let abortController: AbortController | null = null

async function generateBrief() {
  if (generating.value) return

  generating.value = true
  progressLog.value = []
  streamText.value = ''
  briefContent.value = ''

  abortController = new AbortController()
  let doneEvent: any = null

  try {
    const response = await fetch(
      `/api/users/${username}/generate-stream`,
      {
        method: 'POST',
        signal: abortController.signal,
      }
    )

    if (!response.body) throw new Error('无法读取响应流')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data:')) continue

        const jsonStr = line.slice(5).trim()
        if (!jsonStr) continue

        try {
          const event = JSON.parse(jsonStr)
          if (event.type === 'done') doneEvent = event
          else handleEvent(event)
        } catch (e) {
          console.warn('解析事件失败：', jsonStr)
        }
      }
    }
  } catch (e: any) {
    if (e.name === 'AbortError') {
      progressLog.value.push('⏹ 已停止生成')
    } else {
      progressLog.value.push(`❌ ${e.message || '生成失败'}`)
    }
  } finally {
    abortController = null
    await loadBriefs()
    if (doneEvent) await showGeneratedBrief(doneEvent)
    generating.value = false
  }
}

function handleEvent(event: any) {
  if (event.type === 'status' || event.type === 'progress') {
    // 后端一直在推这些进度事件，以前前端直接丢掉了，面板只能干等
    if (event.content) progressLog.value.push(event.content)
  } else if (event.type === 'text') {
    streamText.value += event.content
  } else if (event.type === 'error') {
    progressLog.value.push(`❌ ${event.content}`)
  }
}

/**
 * 生成完成：正文从后端存好的文件里读回来。
 *
 * 以前这里是拿模型最后一条回复当正文显示的，代价是模型要把整份简报复述一遍
 * （实测 957 字、约 32 秒）。简报本来就写进文件了，直接读文件既准又省。
 */
async function showGeneratedBrief(event: any) {
  if (event.brief_id) {
    try {
      const data = await request.get(
        `/users/${username}/briefs/${event.brief_id}`
      ) as any
      // 必须 trim 后再存：只有空白的字符串是非空的，会让下面所有判空失效
      briefContent.value = (data.content || '').trim()
      if (briefContent.value) {
        modalDate.value = formatDate(event.brief_id)
      }
    } catch (e) {
      console.error('读取简报文件失败：', e)
    }
  }

  // 兜底：文件没读到（模型写到了回复里而不是文件里）就用模型自己输出的文字。
  // 注意这里每一步都要 trim —— 模型在调工具的轮次会推 "\n\n" 这类纯空白，
  // 攒起来是个"非空但看不见"的字符串，不 trim 的话会把后面的提示全挡掉，
  // 用户看到的就是一个什么内容都没有的空白弹窗。
  if (!briefContent.value) {
    briefContent.value =
      streamText.value.trim() || (event.content || '').trim()
    if (briefContent.value) {
      modalDate.value = formatDate(localToday())
    }
  }

  if (!briefContent.value) {
    // 真的什么都没有，就不要弹一个空窗 —— 那比报错更让人困惑
    return
  }

  modalContent.value = briefContent.value
  showModal.value = true
}

/** 手动停止生成（中断 SSE 连接） */
function stopGenerate() {
  abortController?.abort()
}

// 简报正文的 Markdown 渲染结果
const renderedBrief = computed(() => renderMarkdown(briefContent.value))

// ==================== 历史简报 ====================
const briefs = ref<Array<{ date: string; size: number }>>([])

async function loadBriefs(): Promise<boolean> {
  try {
    const data = await request.get(`/users/${username}/briefs`) as any
    briefs.value = Array.isArray(data) ? data : []
    return true
  } catch {
    return false
  }
}

async function viewBrief(date: string) {
  try {
    const data = await request.get(`/users/${username}/briefs/${date}`) as any
    modalDate.value = formatDate(date)
    modalContent.value = data.content || ''
    showModal.value = true
  } catch (e: any) {
    alert(e.message)
  }
}

// ==================== 弹窗 ====================
const showModal = ref(false)
const modalDate = ref('')
const modalContent = ref('')

// 弹窗内容的 Markdown 渲染结果
const renderedModal = computed(() => renderMarkdown(modalContent.value))

/** 本地时区的今天（YYYY-MM-DD）。不能用 toISOString()，那是 UTC，会差一天 */
function localToday(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function formatDate(s: string) {
  if (s.includes('_')) {
    const [d, t] = s.split('_')
    return `${d} ${t.replace(/-/g, ':')}`
  }
  return s
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

// ==================== 跳转 ====================
function goPreferences() {
  router.push(`/users/${username}/preferences`)
}

function goHome() {
  router.push('/')
}

onMounted(async () => {
  loadNews()

  // 简报列表加载成功、且今天还没有简报 → 自动生成一份
  // （走 SSE 流式，右侧面板能实时看到进度，不会干等）
  const loaded = await loadBriefs()
  if (loaded) {
    const today = localToday()
    const hasToday = briefs.value.some((b) => b.date.startsWith(today))
    if (!hasToday) {
      generateBrief()
    }
  }
})
</script>

<style scoped>
/* ==================== 页面骨架 ==================== */
.feed-page {
  min-height: 100vh;
  background: #f5f7fa;
}

/* ==================== 顶部栏 ==================== */
.topbar {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e6ecf3;
  display: flex;
  align-items: center;
  padding: 0 40px;
  position: sticky;
  top: 0;
  z-index: 10;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 16px;
  color: #1f2d3d;
}
.brand-icon { font-size: 22px; }
.user-area {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}
.username { font-size: 14px; color: #5a6b7c; }
.top-btn {
  height: 34px;
  padding: 0 14px;
  border-radius: 8px;
  background: #fff;
  border: 1.5px solid #e6ecf3;
  color: #5a6b7c;
  font-size: 13px;
  cursor: pointer;
  transition: all .2s;
}
.top-btn:hover {
  border-color: #4f7cff;
  color: #4f7cff;
}

/* ==================== 主体 ==================== */
.main {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  padding: 24px 40px 60px;
  max-width: 1600px;
  margin: 0 auto;
}

/* ==================== 新闻列表 ==================== */
.news-column { min-width: 0; }
.news-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.news-heading h2 {
  margin: 0;
  font-size: 20px;
  color: #1f2d3d;
}
.refresh-btn {
  height: 36px;
  padding: 0 16px;
  border-radius: 10px;
  background: #fff;
  border: 1.5px solid #e6ecf3;
  color: #5a6b7c;
  font-size: 13px;
  cursor: pointer;
}
.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}
.news-card {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 14px;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.05);
  transition: transform 0.2s, box-shadow 0.2s;
}
.news-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 28px rgba(31, 45, 61, 0.1);
}
.news-img-wrap {
  height: 160px;
  background: #f0f2f5;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.news-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.news-img-placeholder {
  font-size: 40px;
  color: #b0bcc9;
}
.news-body { padding: 14px 16px 18px; }
.news-source {
  display: inline-block;
  font-size: 11px;
  color: #4f7cff;
  background: #eef3ff;
  padding: 2px 8px;
  border-radius: 4px;
  margin-bottom: 8px;
}
.news-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1f2d3d;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.news-summary {
  margin: 0;
  font-size: 12.5px;
  color: #7a8b9b;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.loading, .empty {
  text-align: center;
  padding: 80px 0;
  color: #9aa8b8;
  font-size: 14px;
  background: #fff;
  border-radius: 14px;
}

/* ==================== 右侧 AI 面板 ==================== */
.ai-panel {
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgba(31, 45, 61, 0.05);
  position: sticky;
  top: 84px;
  height: fit-content;
  max-height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ai-header {
  padding: 18px 20px;
  border-bottom: 1px solid #e6ecf3;
  display: flex;
  align-items: center;
  gap: 12px;
}
.ai-avatar {
  font-size: 24px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #eef3ff;
  border-radius: 10px;
}
.ai-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2d3d;
}
.ai-sub {
  font-size: 12px;
  color: #9aa8b8;
  margin-top: 2px;
}
.ai-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
.ai-btn {
  width: 100%;
  height: 46px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #4f7cff, #6a9cff);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all .2s;
}
.ai-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(79, 124, 255, 0.3);
}
.ai-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.stop-btn {
  background: linear-gradient(135deg, #ff7a7a, #ff9a6a);
}

/* ==================== 简报面板 ==================== */
.brief-panel {
  margin-top: 16px;
  background: #f9fbfd;
  border-radius: 10px;
  padding: 14px 16px;
  max-height: 500px;
  overflow-y: auto;
}
.brief-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #5a6b7c;
  font-weight: 600;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e6ecf3;
}
.typing-cursor {
  color: #4f7cff;
  animation: blink 0.8s infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
.brief-text {
  margin: 0;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 13px;
  line-height: 1.8;
  color: #2d4238;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 生成过程中的工具调用进度 */
.progress-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #5a6b7c;
}
.progress-list li {
  animation: fadeIn 0.3s;
}
.progress-list li:nth-child(even) {
  padding-left: 14px;
  color: #9aa8b8;
}
.progress-done {
  margin-top: 4px;
  color: #2d8f5b !important;
  font-weight: 600;
}

/* ==================== 历史简报 ==================== */
.history {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #e6ecf3;
}
.history h4 {
  margin: 0 0 12px;
  font-size: 13px;
  color: #5a6b7c;
  font-weight: 600;
}
.history-empty {
  font-size: 12px;
  color: #b0bcc9;
  text-align: center;
  padding: 8px 0;
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.history-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: #1f2d3d;
  cursor: pointer;
  transition: background 0.2s;
}
.history-list li:hover { background: #f5f7fa; }
.history-date { font-weight: 500; }
.history-size { font-size: 11px; color: #b0bcc9; }

/* ==================== 弹窗 ==================== */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(20, 30, 50, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  animation: fadeIn 0.2s;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
.modal {
  width: 100%;
  max-width: 720px;
  max-height: 85vh;
  background: #fff;
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideUp 0.25s;
}
@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
.modal-head {
  padding: 20px 28px;
  border-bottom: 1px solid #e6ecf3;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-head h2 {
  margin: 0;
  font-size: 17px;
  color: #1f2d3d;
}
.modal-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #9aa8b8;
}
.modal-close {
  width: 32px; height: 32px;
  border: none; border-radius: 50%;
  background: #f5f7fa; color: #5a6b7c;
  cursor: pointer;
  font-size: 14px;
}
.modal-close:hover { background: #e6ecf3; }
.modal-content {
  margin: 0;
  padding: 24px 28px;
  flex: 1;
  overflow-y: auto;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.8;
  color: #2d4238;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ==================== Markdown 渲染 ==================== */
.markdown { white-space: normal; }
.markdown :deep(p) { margin: 0 0 10px; }
.markdown :deep(p:last-child) { margin-bottom: 0; }
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: 16px 0 8px;
  color: #1f2d3d;
  line-height: 1.5;
}
.markdown :deep(h2) { font-size: 16px; }
.markdown :deep(h3) { font-size: 14.5px; }
.markdown :deep(h4) { font-size: 13.5px; }
.markdown :deep(ul),
.markdown :deep(ol) { margin: 6px 0 10px; padding-left: 20px; }
.markdown :deep(li) { margin: 3px 0; }
.markdown :deep(a) { color: #4f7cff; text-decoration: none; word-break: break-all; }
.markdown :deep(a:hover) { text-decoration: underline; }
.markdown :deep(code) {
  background: #eef1f5;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.92em;
  font-family: Consolas, Monaco, monospace;
}
.markdown :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid #d6e0ff;
  color: #5a6b7c;
}
.markdown :deep(hr) { border: none; border-top: 1px solid #e6ecf3; margin: 14px 0; }

@media (max-width: 900px) {
  .main { grid-template-columns: 1fr; padding: 16px; }
  .ai-panel { position: static; }
  .topbar { padding: 0 16px; }
}
</style>