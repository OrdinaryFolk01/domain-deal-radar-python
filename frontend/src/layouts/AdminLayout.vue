<script setup lang="ts">
import { Compass, Database, ListChecks, Menu, RefreshCw, Settings } from '@lucide/vue';
import { computed, reactive, ref } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';
import DataTools from '../components/DataTools.vue';

type ToastTone = 'success' | 'error' | 'info';
type PageExpose = {
  refresh?: () => Promise<void> | void;
};

const route = useRoute();
const currentPage = ref<PageExpose | null>(null);
const loading = ref(false);
const toast = reactive<{ message: string; tone: ToastTone; visible: boolean }>({
  message: '',
  tone: 'info',
  visible: false,
});
let toastTimer: number | undefined;

const navItems = [
  { to: '/', name: 'radar', label: '雷达发现', icon: Compass },
  { to: '/leads', name: 'leads', label: '线索库', icon: Database },
  { to: '/tasks', name: 'tasks', label: '任务中心', icon: ListChecks },
  { to: '/settings', name: 'settings', label: '系统设置', icon: Settings },
];

const pageTitle = computed(() => String(route.meta.title || '域名交易雷达'));
const pageDescription = computed(() => String(route.meta.description || ''));

function showToast(message: string, tone: ToastTone = 'info') {
  toast.message = message;
  toast.tone = tone;
  toast.visible = true;
  if (toastTimer) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toast.visible = false;
  }, 2800);
}

function setLoading(value: boolean) {
  loading.value = value;
}

async function refreshCurrentPage() {
  await currentPage.value?.refresh?.();
}
</script>

<template>
  <div class="drawer lg:drawer-open">
    <input id="admin-sidebar" type="checkbox" class="drawer-toggle" />

    <div class="drawer-content min-h-dvh bg-base-200">
      <header class="sticky top-0 z-30 border-b border-base-300 bg-base-100/95 backdrop-blur">
        <div class="flex flex-col gap-3 px-4 py-3 lg:px-6 xl:flex-row xl:items-center xl:justify-between">
          <div class="flex min-w-0 items-center gap-3">
            <label for="admin-sidebar" class="btn btn-ghost btn-square btn-sm lg:hidden" aria-label="打开菜单">
              <Menu class="h-5 w-5" />
            </label>
            <div class="min-w-0">
              <h1 class="truncate text-xl font-semibold tracking-normal">{{ pageTitle }}</h1>
              <p v-if="pageDescription" class="truncate text-sm text-base-content/60">{{ pageDescription }}</p>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button class="btn btn-outline btn-sm" :disabled="loading" @click="refreshCurrentPage">
              <RefreshCw class="h-4 w-4" />
              刷新
            </button>
            <DataTools @refresh="refreshCurrentPage" @toast="showToast" />
          </div>
        </div>
      </header>

      <main class="px-4 py-4 lg:px-6 lg:py-6">
        <div class="mx-auto flex w-full max-w-[1680px] flex-col gap-4">
          <RouterView v-slot="{ Component }">
            <component
              :is="Component"
              ref="currentPage"
              @loading="setLoading"
              @toast="showToast"
            />
          </RouterView>
        </div>
      </main>

      <div v-if="loading" class="fixed bottom-4 left-4 z-50 alert w-auto border border-base-300 bg-base-100 shadow-lg">
        <span class="loading loading-spinner loading-sm"></span>
        <span>处理中...</span>
      </div>

      <div v-if="toast.visible" class="toast toast-end toast-bottom z-50" aria-live="polite">
        <div class="alert" :class="toast.tone === 'success' ? 'alert-success' : toast.tone === 'error' ? 'alert-error' : 'alert-info'">
          <span>{{ toast.message }}</span>
        </div>
      </div>
    </div>

    <div class="drawer-side z-40">
      <label for="admin-sidebar" class="drawer-overlay" aria-label="关闭菜单"></label>
      <aside class="flex min-h-full w-64 flex-col border-r border-base-300 bg-base-100 px-3 py-4">
        <div class="mb-5 px-2">
          <div class="text-lg font-semibold tracking-normal">域名交易雷达</div>
          <div class="mt-1 text-xs text-base-content/55">Domain Deal Radar</div>
        </div>

        <nav class="menu gap-1 p-0 w-full">
          <li v-for="item in navItems" :key="item.name">
            <RouterLink
              :to="item.to"
              class="gap-3 rounded-btn font-medium"
              :class="
                route.name === item.name
                  ? 'bg-primary text-primary-content shadow-sm'
                  : 'text-base-content/70 hover:bg-base-200 hover:text-base-content'
              "
            >
              <component :is="item.icon" class="h-4 w-4" />
              <span>{{ item.label }}</span>
            </RouterLink>
          </li>
        </nav>
      </aside>
    </div>
  </div>
</template>
