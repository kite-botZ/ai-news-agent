<template>
  <div class="page">
    <div class="card">
      <header class="header">
        <div class="avatar">{{ initial }}</div>
        <div>
          <h1>{{ username }} 的订阅偏好</h1>
          <p class="subtitle">设置你关注的关键词和话题，AI 会据此筛选新闻</p>
        </div>
      </header>

      <div v-if="loading" class="loading">加载中…</div>

      <div v-else>
        <!-- 关键词 -->
        <div class="section">
          <label>关注关键词</label>
          <p class="tip">输入后按回车添加，比如：AI、大模型、LLM、OpenAI</p>

          <div class="tags">
            <span v-for="(kw, i) in keywords" :key="i" class="tag">
              {{ kw }}
              <button class="tag-remove" type="button" @click="removeKeyword(i)">✕</button>
            </span>
          </div>

          <input
            v-model="keywordInput"
            placeholder="输入关键词，回车添加"
            @keydown.enter.prevent="addKeyword"
          />
        </div>

        <!-- 话题 -->
        <div class="section">
          <label>关注话题</label>
          <p class="tip">输入后按回车添加，比如：人工智能、后端开发</p>

          <div class="tags">
            <span v-for="(t, i) in topics" :key="i" class="tag topic-tag">
              {{ t }}
              <button class="tag-remove" type="button" @click="removeTopic(i)">✕</button>
            </span>
          </div>

          <input
            v-model="topicInput"
            placeholder="输入话题，回车添加"
            @keydown.enter.prevent="addTopic"
          />
        </div>

        <!-- 操作 -->
        <div class="actions">
          <button class="secondary-btn" type="button" @click="goBack">返回</button>
          <button class="primary-btn" type="button" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存偏好' }}
          </button>
        </div>

        <p v-if="message" :class="['message', messageType]">{{ message }}</p>

        <div class="tips">
          <p>💡 保存偏好后，回到用户首页点击"生成今日简报"触发 AI</p>
        </div>
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
const saving = ref(false)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')

const keywords = ref<string[]>([])
const topics = ref<string[]>([])
const keywordInput = ref('')
const topicInput = ref('')

async function loadPreferences() {
  loading.value = true
  try {
    const data = await request.get(`/users/${username}/preferences`) as any
    keywords.value = data.keywords || []
    topics.value = data.topics || []
  } catch (e: any) {
    message.value = e.message
    messageType.value = 'error'
  } finally {
    loading.value = false
  }
}

function addKeyword() {
  const kw = keywordInput.value.trim()
  if (!kw) return
  if (!keywords.value.includes(kw)) {
    keywords.value.push(kw)
  }
  keywordInput.value = ''
}

function removeKeyword(i: number) {
  keywords.value.splice(i, 1)
}

function addTopic() {
  const t = topicInput.value.trim()
  if (!t) return
  if (!topics.value.includes(t)) {
    topics.value.push(t)
  }
  topicInput.value = ''
}

function removeTopic(i: number) {
  topics.value.splice(i, 1)
}

async function save() {
  message.value = ''
  saving.value = true
  try {
    await request.put(`/users/${username}/preferences`, {
      keywords: keywords.value,
      topics: topics.value,
    })
    message.value = '偏好已保存！'
    messageType.value = 'success'

    // 1 秒后跳到简报页
    setTimeout(() => {
      router.push(`/users/${username}/briefs`)
    }, 800)
  } catch (e: any) {
    message.value = e.message || '保存失败'
    messageType.value = 'error'
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push('/')
}

onMounted(loadPreferences)
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef3ff, #f5f7fc);
  padding: 40px 20px;
}
.card {
  width: 640px;
  background: #fff;
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(31, 45, 61, 0.08);
}
.header {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 36px;
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
.loading { text-align: center; padding: 60px 0; color: #9aa8b8; }
.section { margin-bottom: 28px; }
.section label { display: block; font-size: 14px; font-weight: 600; color: #2d4238; margin-bottom: 6px; }
.tip { margin: 0 0 12px; font-size: 12px; color: #9aa8b8; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; min-height: 28px; }
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #eef3ff;
  color: #4f7cff;
  font-size: 13px;
  padding: 6px 10px;
  border-radius: 6px;
}
.topic-tag { background: #f0faf5; color: #22a06b; }
.tag-remove {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 11px;
  opacity: 0.6;
  padding: 0 2px;
}
.tag-remove:hover { opacity: 1; }
input {
  width: 100%;
  height: 44px;
  border: 1.5px solid #e6ecf3;
  border-radius: 10px;
  padding: 0 14px;
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
  background: #f9fbfd;
  transition: all .2s;
}
input:focus { border-color: #4f7cff; background: #fff; box-shadow: 0 0 0 4px rgba(79, 124, 255, .1); }
.actions { display: flex; gap: 12px; margin-top: 32px; }
.primary-btn, .secondary-btn {
  flex: 1;
  height: 48px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}
.primary-btn {
  border: none;
  background: linear-gradient(135deg, #4f7cff, #6a9cff);
  color: #fff;
}
.primary-btn:disabled { opacity: .7; cursor: not-allowed; }
.secondary-btn {
  background: #fff;
  border: 1.5px solid #e6ecf3;
  color: #5a6b7c;
}
.message { margin-top: 20px; padding: 12px 16px; border-radius: 10px; font-size: 14px; }
.message.success { background: #f0faf5; color: #22a06b; border-left: 3px solid #22a06b; }
.message.error { background: #fff5f5; color: #e04f4f; border-left: 3px solid #e04f4f; }
.tips { margin-top: 16px; padding: 10px 14px; background: #fff9ee; border-radius: 8px; font-size: 12px; color: #a67c33; }
.tips p { margin: 0; }
</style>