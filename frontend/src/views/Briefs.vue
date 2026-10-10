<template>
  <div class="page">
    <div class="card">
      <header class="header">
        <div class="avatar">{{ initial }}</div>
        <div>
          <h1>{{ username }} 的 AI 简报</h1>
          <p class="subtitle">查看历史简报，或生成今天的</p>
        </div>
        <div class="header-actions">
          <button class="secondary-btn" type="button" @click="goPreferences">偏好设置</button>
          <button class="secondary-btn" type="button" @click="goHome">切换用户</button>
        </div>
      </header>

      <!-- 生成按钮 -->
      <div class="generate-section">
        <button class="primary-btn" type="button" :disabled="generating" @click="generateBrief">
          {{ generating ? '正在生成，请稍等…' : '生成今日简报' }}
        </button>
        <p v-if="generateMsg" :class="['msg', generateMsgType]">{{ generateMsg }}</p>
      </div>

      <!-- 简报列表 -->
      <div class="list-section">
        <h2>历史简报</h2>

        <div v-if="loading" class="loading">加载中…</div>
        <div v-else-if="briefs.length === 0" class="empty">
          暂无简报，点上方按钮生成第一条
        </div>
        <div v-else class="brief-list">
          <div
            v-for="b in briefs"
            :key="b.date"
            class="brief-item"
            :class="{ active: selectedDate === b.date }"
            @click="viewBrief(b.date)"
          >
            <div class="brief-date">{{ formatDate(b.date) }}</div>
            <div class="brief-meta">{{ formatSize(b.size) }}</div>
          </div>
        </div>
      </div>

      <!-- 简报详情 -->
      <div v-if="selectedDate && briefContent" class="detail-section">
        <div class="detail-head">
          <h2>{{ selectedDate }} 的简报</h2>
          <button class="text-btn" type="button" @click="selectedDate = ''; briefContent = ''">关闭</button>
        </div>
        <pre class="brief-content">{{ briefContent }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'

const route = useRoute()
const router = useRouter()
const username = String(route.params.username || '')

const initial = computed(() => username.charAt(0).toUpperCase())

const loading = ref(true)
const generating = ref(false)
const generateMsg = ref('')
const generateMsgType = ref<'success' | 'error'>('success')

const briefs = ref<Array<{ date: string; filename: string; size: number }>>([])
const selectedDate = ref('')
const briefContent = ref('')

async function loadBriefs() {
  loading.value = true
  try {
    const data = await request.get(`/users/${username}/briefs`) as any
    briefs.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    generateMsg.value = e.message
    generateMsgType.value = 'error'
  } finally {
    loading.value = false
  }
}

async function generateBrief() {
  generateMsg.value = ''
  generating.value = true
  try {
    await request.post(`/users/${username}/generate`)
    generateMsg.value = '简报生成成功！'
    generateMsgType.value = 'success'
    await loadBriefs()
  } catch (e: any) {
    generateMsg.value = e.message || '生成失败'
    generateMsgType.value = 'error'
  } finally {
    generating.value = false
  }
}

async function viewBrief(date: string) {
  try {
    const data = await request.get(`/users/${username}/briefs/${date}`) as any
    selectedDate.value = date
    briefContent.value = data.content || ''
  } catch (e: any) {
    generateMsg.value = e.message
    generateMsgType.value = 'error'
  }
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

function formatDate(dateStr: string) {
  // 如果包含时间戳：2026-10-10_14-30-25 → 2026-10-10 14:30:25
  if (dateStr.includes('_')) {
    const [d, t] = dateStr.split('_')
    return `${d} ${t.replace(/-/g, ':')}`
  }
  return dateStr
}

function goPreferences() {
  router.push(`/users/${username}/preferences`)
}

function goHome() {
  router.push('/')
}

onMounted(async () => {
  await loadBriefs()

  // 检查今天是否已生成
  const today = new Date().toISOString().split('T')[0]  // 2026-10-10
  const hasToday = briefs.value.some(b => b.date.startsWith(today))

  // 用 localStorage 防止同一天重复触发
  const triggerKey = `brief_triggered_${username}_${today}`
  const alreadyTriggered = localStorage.getItem(triggerKey)

  if (!hasToday && !alreadyTriggered) {
    localStorage.setItem(triggerKey, '1')
    // 延迟 1 秒再触发，让页面先渲染出来
    setTimeout(() => {
      generateBrief()
    }, 1000)
  }
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  background: linear-gradient(135deg, #eef3ff, #f5f7fc);
  padding: 40px 20px;
}
.card {
  width: 720px;
  background: #fff;
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(31, 45, 61, 0.08);
}
.header {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 32px;
}
.avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4f7cff, #6a9cff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
}
h1 { margin: 0; font-size: 22px; color: #1f2d3d; }
.subtitle { margin: 6px 0 0; font-size: 13px; color: #9aa8b8; }
.header-actions { margin-left: auto; display: flex; gap: 8px; }
.generate-section { margin-bottom: 32px; }
.primary-btn {
  width: 100%;
  height: 52px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #4f7cff, #6a9cff);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}
.primary-btn:disabled { opacity: .7; cursor: not-allowed; }
.secondary-btn {
  height: 40px;
  padding: 0 16px;
  border-radius: 10px;
  background: #fff;
  border: 1.5px solid #e6ecf3;
  color: #5a6b7c;
  font-size: 14px;
  cursor: pointer;
}
.msg { margin: 12px 0 0; padding: 10px 14px; border-radius: 8px; font-size: 13px; }
.msg.success { background: #f0faf5; color: #22a06b; }
.msg.error { background: #fff5f5; color: #e04f4f; }
.list-section { margin-bottom: 24px; }
.list-section h2 { font-size: 16px; color: #1f2d3d; margin: 0 0 16px; }
.loading, .empty { text-align: center; padding: 40px 0; color: #9aa8b8; font-size: 14px; }
.brief-list { display: grid; gap: 8px; }
.brief-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border: 1.5px solid #e6ecf3;
  border-radius: 10px;
  cursor: pointer;
  transition: all .2s;
}
.brief-item:hover { border-color: #4f7cff; background: #f9fbff; }
.brief-item.active { border-color: #4f7cff; background: #eef3ff; }
.brief-date { font-weight: 600; color: #1f2d3d; }
.brief-meta { font-size: 12px; color: #9aa8b8; }
.detail-section { margin-top: 24px; border-top: 1px solid #e6ecf3; padding-top: 24px; }
.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.detail-head h2 { font-size: 15px; color: #1f2d3d; margin: 0; }
.text-btn { border: none; background: transparent; color: #4f7cff; cursor: pointer; font-size: 13px; }
.brief-content {
  background: #f9fbfd;
  border-radius: 10px;
  padding: 20px;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 13px;
  line-height: 1.8;
  color: #2d4238;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 500px;
  overflow-y: auto;
}
</style>