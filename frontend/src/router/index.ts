import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'
import Preferences from '@/views/Preferences.vue'
import Briefs from '@/views/Briefs.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', component: Home },
    { path: '/users/:username/preferences', component: Preferences },
    { path: '/users/:username/briefs', component: Briefs },
  ],
})

export default router