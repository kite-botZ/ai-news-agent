import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 180000,
})

request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

export default request