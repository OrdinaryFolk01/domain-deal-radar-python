<script setup lang="ts">
import { Inbox, Mail, Save, Send } from '@lucide/vue';
import { onMounted, reactive, ref } from 'vue';
import { getEmailSettings, saveEmailSettings } from '../api/radar';
import type { EmailSettings } from '../api/types';

type ToastTone = 'success' | 'error' | 'info';
type ReceiveProtocol = EmailSettings['receive_protocol'];

const emit = defineEmits<{
  loading: [value: boolean];
  toast: [message: string, tone?: ToastTone];
}>();

const emailSettings = ref<EmailSettings | null>(null);
const form = reactive({
  receive_protocol: 'imap' as ReceiveProtocol,
  receive_host: '',
  receive_port: 993,
  receive_use_ssl: true,
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  smtp_from: '',
  smtp_use_tls: true,
  smtp_use_ssl: false,
});

function syncForm(settings: EmailSettings) {
  emailSettings.value = settings;
  form.receive_protocol = settings.receive_protocol || 'imap';
  form.receive_host = settings.receive_host || '';
  form.receive_port = settings.receive_port || 993;
  form.receive_use_ssl = settings.receive_use_ssl;
  form.smtp_host = settings.smtp_host || '';
  form.smtp_port = settings.smtp_port || 587;
  form.smtp_user = settings.smtp_user || '';
  form.smtp_password = '';
  form.smtp_from = settings.smtp_from || '';
  form.smtp_use_tls = settings.smtp_use_tls;
  form.smtp_use_ssl = settings.smtp_use_ssl;
}

async function refresh() {
  emit('loading', true);
  try {
    syncForm(await getEmailSettings());
  } catch (error) {
    emit('toast', error instanceof Error ? error.message : '读取邮件配置失败', 'error');
  } finally {
    emit('loading', false);
  }
}

function applyQqPreset(protocol: ReceiveProtocol) {
  form.receive_protocol = protocol;
  form.receive_host = protocol === 'imap' ? 'imap.qq.com' : 'pop.qq.com';
  form.receive_port = protocol === 'imap' ? 993 : 995;
  form.receive_use_ssl = true;
  form.smtp_host = 'smtp.qq.com';
  form.smtp_port = 465;
  form.smtp_use_tls = false;
  form.smtp_use_ssl = true;
}

async function save() {
  emit('loading', true);
  try {
    const settings = await saveEmailSettings({
      receive_protocol: form.receive_protocol,
      receive_host: form.receive_host,
      receive_port: form.receive_port || 993,
      receive_use_ssl: form.receive_use_ssl,
      smtp_host: form.smtp_host,
      smtp_port: form.smtp_port || 587,
      smtp_user: form.smtp_user,
      smtp_password: form.smtp_password,
      smtp_from: form.smtp_from,
      smtp_use_tls: form.smtp_use_tls,
      smtp_use_ssl: form.smtp_use_ssl,
    });
    syncForm(settings);
    emit('toast', '邮件配置已保存', 'success');
  } catch (error) {
    emit('toast', error instanceof Error ? error.message : '邮件配置保存失败', 'error');
  } finally {
    emit('loading', false);
  }
}

onMounted(refresh);
defineExpose({ refresh });
</script>

<template>
  <section class="rounded-box border border-base-300 bg-base-100 p-4 shadow-sm">
    <div class="flex flex-col gap-3 border-b border-base-300 pb-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h2 class="flex items-center gap-2 text-base font-semibold">
          <Mail class="h-4 w-4 text-primary" />
          邮件收发配置
        </h2>
        <p class="mt-1 text-sm text-base-content/60">
          当前来源：{{ emailSettings?.source === 'dynamic' ? '页面配置' : '.env / 默认配置' }}
          <span v-if="emailSettings?.has_password"> · 已保存密码/授权码</span>
        </p>
      </div>
      <button class="btn btn-primary btn-sm" type="button" @click="save">
        <Save class="h-4 w-4" />
        保存邮件配置
      </button>
    </div>

    <div class="mt-4 space-y-6">
      <div class="flex flex-wrap gap-2">
        <button class="btn btn-outline btn-sm" type="button" @click="applyQqPreset('imap')">QQ IMAP</button>
        <button class="btn btn-outline btn-sm" type="button" @click="applyQqPreset('pop3')">QQ POP3</button>
      </div>

      <div>
        <h3 class="flex items-center gap-2 border-b border-base-300 pb-2 text-sm font-semibold">
          <Inbox class="h-4 w-4 text-primary" />
          收件服务器
        </h3>
        <div class="mt-3 grid gap-4 md:grid-cols-4">
          <label class="flex flex-col gap-2">
            <span class="label-text">协议</span>
            <select v-model="form.receive_protocol" class="select select-bordered">
              <option value="imap">IMAP</option>
              <option value="pop3">POP3</option>
            </select>
          </label>
          <label class="flex flex-col gap-2 md:col-span-2">
            <span class="label-text">收件服务器</span>
            <input v-model.trim="form.receive_host" class="input input-bordered" placeholder="imap.example.com" />
          </label>
          <label class="flex flex-col gap-2">
            <span class="label-text">端口</span>
            <input v-model.number="form.receive_port" class="input input-bordered" type="number" min="1" max="65535" />
          </label>
          <div class="flex flex-wrap gap-4 md:col-span-4">
            <label class="label cursor-pointer gap-2">
              <input v-model="form.receive_use_ssl" type="checkbox" class="checkbox checkbox-primary checkbox-sm" />
              <span class="label-text">SSL</span>
            </label>
          </div>
        </div>
      </div>

      <div>
        <h3 class="flex items-center gap-2 border-b border-base-300 pb-2 text-sm font-semibold">
          <Send class="h-4 w-4 text-primary" />
          发送服务器
        </h3>
        <div class="mt-3 grid gap-4 md:grid-cols-2">
          <label class="flex flex-col gap-2">
            <span class="label-text">SMTP 主机</span>
            <input v-model.trim="form.smtp_host" class="input input-bordered" placeholder="smtp.example.com" />
          </label>
          <label class="flex flex-col gap-2">
            <span class="label-text">端口</span>
            <input v-model.number="form.smtp_port" class="input input-bordered" type="number" min="1" max="65535" />
          </label>
          <label class="flex flex-col gap-2">
            <span class="label-text">账号</span>
            <input v-model.trim="form.smtp_user" class="input input-bordered" autocomplete="username" />
          </label>
          <label class="flex flex-col gap-2">
            <span class="label-text">密码 / 授权码</span>
            <input
              v-model="form.smtp_password"
              class="input input-bordered"
              type="password"
              autocomplete="new-password"
              :placeholder="emailSettings?.has_password ? '已保存，留空不修改' : '未保存'"
            />
          </label>
          <label class="flex flex-col gap-2 md:col-span-2">
            <span class="label-text">发件人</span>
            <input v-model.trim="form.smtp_from" class="input input-bordered" placeholder="sender@example.com" />
          </label>
          <div class="flex flex-wrap gap-4 md:col-span-2">
            <label class="label cursor-pointer gap-2">
              <input v-model="form.smtp_use_tls" type="checkbox" class="checkbox checkbox-primary checkbox-sm" />
              <span class="label-text">STARTTLS</span>
            </label>
            <label class="label cursor-pointer gap-2">
              <input v-model="form.smtp_use_ssl" type="checkbox" class="checkbox checkbox-primary checkbox-sm" />
              <span class="label-text">SSL</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
