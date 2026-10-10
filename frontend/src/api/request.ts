import axios from 'axios'

// axios 实例
const request = axios.create({
  baseURL: '/api',
  timeout: 30000,   // 30 秒（AI 生成简报比较慢）
})

// 请求拦截器
request.interceptors.request.use((config) => {
  return config
})

// 响应拦截器
request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

export default request