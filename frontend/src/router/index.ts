import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'
import Preferences from '@/views/Preferences.vue'
import NewsFeed from '@/views/NewsFeed.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', component: Home },
    { path: '/users/:username/preferences', component: Preferences },
    { path: '/users/:username/news', component: NewsFeed },
  ],
})

export default router