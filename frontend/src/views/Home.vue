<template>
  <div class="page">
    <div class="card">
      <div class="logo">📰</div>
      <h1>AI 新闻助手</h1>
      <p class="subtitle">输入用户名，开始定制你的每日 AI 简报</p>

      <div class="form-item">
        <input
          v-model.trim="username"
          placeholder="请输入用户名（3~20 位字母/数字/下划线）"
          @keyup.enter="handleEnter"
        />
      </div>

      <button class="primary-btn" :disabled="loading" @click="handleEnter">
        {{ loading ? '处理中…' : '进 入' }}
      </button>

      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import request from '@/api/request'

const router = useRouter()
const username = ref('')
const loading = ref(false)
const error = ref('')

async function handleEnter() {
  error.value = ''

  // 校验用户名
  if (!username.value) {
    error.value = '请输入用户名'
    return
  }
  if (!/^[a-zA-Z0-9_]{3,20}$/.test(username.value)) {
    error.value = '用户名只能包含字母、数字、下划线，长度 3~20 位'
    return
  }

  loading.value = true
  try {
    // 先试着读用户偏好
    try {
      await request.get(`/users/${username.value}/preferences`)
      // 成功 → 用户存在
      router.push(`/users/${username.value}/briefs`)
    } catch (e: any) {
      // 404 → 用户不存在，询问是否创建
      if (e.message.includes('不存在') || e.message.includes('404')) {
        const ok = confirm(`用户 ${username.value} 不存在，是否创建？`)
        if (!ok) return

        // 创建用户
        await request.post('/users', { username: username.value })
        // 创建成功 → 跳到偏好设置
        router.push(`/users/${username.value}/preferences`)
      } else {
        throw e
      }
    }
  } catch (e: any) {
    error.value = e.message || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef3ff, #f5f7fc);
}
.card {
  width: 400px;
  background: #fff;
  border-radius: 20px;
  padding: 48px 36px;
  box-shadow: 0 20px 60px rgba(31, 45, 61, 0.08);
  text-align: center;
}
.logo { font-size: 48px; margin-bottom: 8px; }
h1 { margin: 0; font-size: 26px; color: #1f2d3d; }
.subtitle { margin: 10px 0 32px; font-size: 14px; color: #9aa8b8; }
.form-item { margin-bottom: 16px; }
input {
  width: 100%;
  height: 48px;
  border: 1.5px solid #e6ecf3;
  border-radius: 12px;
  padding: 0 16px;
  font-size: 15px;
  outline: none;
  box-sizing: border-box;
  background: #f9fbfd;
  transition: all .2s;
}
input:focus { border-color: #4f7cff; background: #fff; box-shadow: 0 0 0 4px rgba(79, 124, 255, .1); }
.primary-btn {
  width: 100%;
  height: 48px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #4f7cff, #6a9cff);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 8px;
  transition: transform .15s;
}
.primary-btn:hover:not(:disabled) { transform: translateY(-1px); }
.primary-btn:disabled { opacity: .7; cursor: not-allowed; }
.error { color: #e04f4f; font-size: 13px; margin-top: 12px; }
</style>