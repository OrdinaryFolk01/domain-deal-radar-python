import { createRouter, createWebHashHistory } from 'vue-router';
import AdminLayout from '../layouts/AdminLayout.vue';
import LeadsPage from '../pages/LeadsPage.vue';
import RadarPage from '../pages/RadarPage.vue';
import SettingsPage from '../pages/SettingsPage.vue';
import TasksPage from '../pages/TasksPage.vue';

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      component: AdminLayout,
      children: [
        {
          path: '',
          name: 'radar',
          component: RadarPage,
          meta: {
            title: '雷达发现',
            description: '候选域名搜索、预筛和转入线索库。',
          },
        },
        {
          path: 'leads',
          name: 'leads',
          component: LeadsPage,
          meta: {
            title: '线索库',
            description: '正式域名线索、尽调结果和跟进记录。',
          },
        },
        {
          path: 'tasks',
          name: 'tasks',
          component: TasksPage,
          meta: {
            title: '任务中心',
            description: '抓取任务和发现任务的执行记录。',
          },
        },
        {
          path: 'settings',
          name: 'settings',
          component: SettingsPage,
          meta: {
            title: '系统设置',
            description: '全局邮件收发配置。',
          },
        },
      ],
    },
  ],
});
