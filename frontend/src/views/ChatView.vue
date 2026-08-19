<!--
  ============================================================
  文件名：ChatView.vue
  位置：frontend/src/views/ChatView.vue
  作用：智能聊天页面
  功能：
    - 显示用户和机器人的聊天消息
    - 支持 Markdown 格式渲染机器人回复
    - 支持快捷操作按钮（推荐菜品、查看菜单等）
    - 支持图片搜菜（上传图片识别菜品）
    - 支持购物车抽屉和悬浮购物车按钮
    - 支持机器人头像和语音播报开关（浏览器 speechSynthesis 分句播报）
    - 支持麦克风语音输入（浏览器 SpeechRecognition，识别结果填入输入框）
    - 发送消息后自动滚动到底部
  ============================================================
-->

<template>
  <div class="chat-container">
    <!-- 左栏：页面标题 + 数字人头像 + 语音播报开关 -->
    <div class="avatar-area">
      <div class="chat-title">智能点餐助手</div>
      <DigitalAvatar :status="avatarStatus" style="margin-top: 15px" />

      <el-button
        circle
        :type="speechEnabled ? 'success' : 'info'"
        :title="speechEnabled ? '点击关闭语音播报' : '点击开启语音播报'"
        @click="toggleSpeech"
        class="speech-toggle"
      >
        <el-icon size="16">
          <!-- 扬声器开 -->
          <svg v-if="speechEnabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 5 6 9H2v6h4l5 4V5z" fill="currentColor" stroke="none" />
            <path d="M15.5 8.5a5 5 0 0 1 0 7" />
            <path d="M18.5 5.5a9.5 9.5 0 0 1 0 13" />
          </svg>
          <!-- 扬声器关 -->
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 5 6 9H2v6h4l5 4V5z" fill="currentColor" stroke="none" />
            <line x1="16" y1="9" x2="22" y2="15" />
            <line x1="22" y1="9" x2="16" y2="15" />
          </svg>
        </el-icon>
      </el-button>
    </div>

    <!-- 右栏：消息列表 + 快捷按钮 + 输入框 -->
    <div class="chat-main">
    <div class="chat-messages" ref="messageBox">
      <template
        v-for="(msg, index) in messages"
        :key="msg.id || `${msg.role}-${index}-${msg.content?.slice(0, 20)}`"
      >
      <!-- 预插入的空 assistant 占位消息不渲染（由“思考中”指示器顶替） -->
      <div
        v-if="msg.role === 'user' || msg.content"
        :class="['message-row', msg.role === 'user' ? 'user' : 'bot']"
      >
        <el-avatar
          :size="40"
          :icon="msg.role === 'user' ? 'UserFilled' : 'Food'"
          :class="msg.role === 'user' ? 'user-avatar' : 'bot-avatar'"
        />

        <div class="message-bubble">
          <div v-if="msg.imageUrl" class="message-image">
            <el-image :src="msg.imageUrl" fit="cover" class="message-image-thumb" :preview-src-list="[msg.imageUrl]" />
          </div>

          <div
            v-if="msg.content && msg.content !== '[图片]'"
            class="message-text"
            v-html="msg.role === 'assistant' ? renderMarkdown(msg.content) : formatText(msg.content)"
            @click="handleLinkClick"
          ></div>
        </div>
      </div>
      </template>

      <div v-if="loading" class="message-row bot">
        <el-avatar :size="40" icon="Food" class="bot-avatar" />
        <div class="message-bubble">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span style="margin-left: 6px">思考中...</span>
        </div>
      </div>
    </div>

    <div class="quick-actions">
      <el-button size="small" @click="sendQuick('有什么推荐的菜品？')">推荐菜品</el-button>
      <el-button size="small" @click="router.push('/menu')">查看菜单</el-button>
      <el-button size="small" @click="sendQuick('查询我的订单')">查询订单</el-button>

      <el-button size="small" type="success" @click="triggerImageUpload">
        <el-icon><Camera /></el-icon>
        图片搜菜
      </el-button>

      <el-button size="small" type="primary" @click="confirmOrder" :disabled="cartStore.totalCount === 0">
        确认下单 ({{ cartStore.totalCount }})
      </el-button>

      <el-button size="small" type="danger" plain @click="handleClearChat">
        <el-icon><Delete /></el-icon>
        清空对话
      </el-button>

      <input
        ref="imageInput"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        style="display: none"
        @change="handleImageChange"
      />
    </div>

    <div class="chat-input-area">
      <div v-if="imagePreviewUrl" class="image-preview-bar">
        <el-image :src="imagePreviewUrl" fit="cover" class="preview-thumb" />
        <el-button link size="small" @click="clearImage">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>

      <el-input
        v-model="inputMessage"
        :placeholder="isRecording ? '正在聆听，请说话…' : (imagePreviewUrl ? '可以补充描述，或直接发送图片' : '告诉我你想吃什么，例如：来一份宫保鸡丁')"
        @keyup.enter="sendMessage"
        size="large"
      >
        <template #prepend>
          <el-button
            circle
            :type="isRecording ? 'danger' : 'default'"
            :class="{ 'recording-pulse': isRecording }"
            :title="isRecording ? '点击停止语音输入' : '点击切换为语音输入'"
            @click="toggleVoiceInput"
          >
            <el-icon><Microphone /></el-icon>
          </el-button>
        </template>
        <template #append>
          <el-button type="primary" @click="sendMessage" :loading="loading">
            发送
          </el-button>
        </template>
      </el-input>
    </div>
    </div>

    <el-drawer v-model="cartVisible" title="购物车" size="360px">
      <div v-if="cartStore.items.length === 0" class="empty-cart">
        <el-empty description="购物车是空的" />
      </div>

      <div v-else>
        <el-table :data="cartStore.items" size="small">
          <el-table-column prop="name" label="菜品" />
          <el-table-column prop="quantity" label="数量" width="80" />

          <el-table-column label="单价" width="80">
            <template #default="scope">¥{{ scope.row.unit_price }}</template>
          </el-table-column>
        </el-table>

        <div class="cart-footer">
          <div class="cart-total">合计：¥{{ cartStore.totalPrice.toFixed(2) }}</div>
          <el-button type="primary" @click="confirmOrderFromDrawer">确认下单</el-button>
        </div>
      </div>
    </el-drawer>

    <el-badge :value="cartStore.totalCount" class="cart-fab" v-if="cartStore.totalCount > 0">
      <el-button circle size="large" type="warning" @click="cartVisible = true">
        <el-icon><ShoppingCart /></el-icon>
      </el-button>
    </el-badge>
  </div>
</template>

<script setup lang="ts">
// ============================================================
// 第 1 步：导入需要的工具、组件和函数
// ============================================================

import { ref, nextTick, onMounted, watch } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import { ElMessage, ElMessageBox } from 'element-plus'

import { Microphone, Camera, Close } from '@element-plus/icons-vue'

import { marked } from 'marked'

import { storeToRefs } from 'pinia'

import { useCartStore } from '@/features/cart/stores/cart.store'
import { useChatStore } from '@/features/chat/stores/chat.store'
import { useAuthStore } from '@/features/auth/stores/auth.store'

import { sendChatMessageStream, clearChatHistory } from '@/features/chat/api/chat.api'

import DigitalAvatar from '@/components/DigitalAvatar.vue'

import { sanitizeHtml, sanitizeTextHtml } from '@/shared/utils/sanitize'

import type { ChatRequest, CartItem } from '@/shared/types'

import { STORAGE_KEY_SPEECH, IMAGE_UPLOAD_MAX_SIZE } from '@/shared/constants'

// ============================================================
// 第 2 步：定义类型
// ============================================================

type AvatarStatus = 'idle' | 'listening' | 'thinking' | 'speaking'

// ============================================================
// 第 3 步：定义变量（数据）
// ============================================================

const route = useRoute()

const router = useRouter()

const chatStore = useChatStore()

const authStore = useAuthStore()

const { messages } = storeToRefs(chatStore)

const inputMessage = ref('')

const loading = ref(false)

const cartVisible = ref(false)

const messageBox = ref<HTMLElement | null>(null)

const cartStore = useCartStore()

const avatarStatus = ref<AvatarStatus>('idle')

const speechEnabled = ref(localStorage.getItem(STORAGE_KEY_SPEECH) !== 'false')

// ============================================================
// 第 3.5 步：语音输入（浏览器内置 SpeechRecognition）
// ============================================================

const isRecording = ref(false)

// 静音自动停止：4 秒内无任何声音活动则停止录音（说话/识别结果会重置计时）
const SILENCE_TIMEOUT = 4000

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let recognition: any = null
let silenceTimer: number | null = null

function clearSilenceTimer() {
  if (silenceTimer !== null) {
    clearTimeout(silenceTimer)
    silenceTimer = null
  }
}

function stopVoiceInput() {
  clearSilenceTimer()
  if (recognition) {
    try {
      recognition.stop()
    } catch {
      // 已停止时忽略
    }
  }
}

function toggleVoiceInput() {
  if (isRecording.value) {
    stopVoiceInput()
    return
  }

  const Ctor = (window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any })
    .SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition?: new () => any }).webkitSpeechRecognition

  if (!Ctor) {
    ElMessage.warning('当前浏览器不支持语音输入，请使用 Chrome / Edge')
    return
  }

  const rec = new Ctor()
  recognition = rec
  rec.lang = 'zh-CN'
  rec.interimResults = true // 边说边出字
  rec.continuous = true     // 持续聆听，由静音定时器决定何时停止

  let gotSpeech = false
  const armSilenceTimer = () => {
    clearSilenceTimer()
    silenceTimer = window.setTimeout(() => {
      stopVoiceInput()
      if (!gotSpeech) {
        ElMessage.info('未检测到说话声音，已停止语音输入')
      }
    }, SILENCE_TIMEOUT)
  }

  rec.onresult = (e: any) => {
    gotSpeech = true
    armSilenceTimer() // 识别到说话内容，重置静音计时
    let transcript = ''
    for (let i = 0; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript
    }
    inputMessage.value = transcript
  }
  // 检测到声音（含未识别出内容的声音）也重置静音计时
  rec.onsoundstart = armSilenceTimer
  rec.onspeechstart = armSilenceTimer
  rec.onend = () => {
    clearSilenceTimer()
    isRecording.value = false
  }
  rec.onerror = () => {
    clearSilenceTimer()
    isRecording.value = false
    ElMessage.warning('语音识别失败，请检查麦克风权限后重试')
  }

  try {
    rec.start()
    isRecording.value = true
    armSilenceTimer() // 启动后 4 秒无声音则自动停止
    stopSpeaking() // 开始语音输入时，打断正在播报的内容（用户要说话了）
  } catch {
    ElMessage.warning('语音识别启动失败，请重试')
  }
}

// ============================================================
// 第 4 步：图片搜菜相关状态
// ============================================================

const imageInput = ref<HTMLInputElement | null>(null)

const imageBase64 = ref<string>('')

const imagePreviewUrl = ref<string>('')

// ============================================================
// 第 5 步：监听变量变化
// ============================================================

watch(speechEnabled, (val) => {
  localStorage.setItem(STORAGE_KEY_SPEECH, val ? 'true' : 'false')
})

// 监听消息变化，自动滚动到底部（兼容流式输出和快速追加）
watch(messages, async () => {
  await scrollToBottom()
}, { deep: true })

// ============================================================
// 第 6 步：Markdown 渲染缓存
// ============================================================

const markdownCache = new Map<string, string>()

// ============================================================
// 第 7 步：生命周期钩子
// ============================================================

onMounted(async () => {
  await scrollToBottom()

  const preset = route.query.preset
  if (preset) {
    inputMessage.value = String(preset)
    await sendMessage()
  }
})

// ============================================================
// 第 8 步：工具函数
// ============================================================

function formatText(text: string) {
  const html = text.replace(/\n/g, '<br>')
  return sanitizeTextHtml(html)
}

// 舞台指示/语气动作标注（如“（微笑）”“(点头)”）：括号内只含此类词时整体移除
// （后端出口已净化，这里兜底 SSE 分块把一个标注拆到两个 chunk 的漏网情况）
const STAGE_DIR_RE = /\s*[（(](?:微笑|轻笑|大笑|笑|点头|摇头|眨眼|叹气|皱眉|鼓掌|挥手|害羞|调皮|得意|温柔|开心|难过|生气|语气轻快|停顿|思考|认真)(?:[，、,~～\s]*(?:微笑|轻笑|大笑|笑|点头|摇头|眨眼|叹气|皱眉|鼓掌|挥手|害羞|调皮|得意|温柔|开心|难过|生气|语气轻快|停顿|思考|认真))*[）)]/g

function renderMarkdown(text: string) {
  const cleaned = text.replace(STAGE_DIR_RE, '')
  if (markdownCache.has(cleaned)) {
    return markdownCache.get(cleaned)!
  }

  const rawHtml = marked.parse(cleaned, { breaks: true, gfm: true }) as string

  const html = sanitizeHtml(rawHtml)

  markdownCache.set(cleaned, html)

  return html
}

function handleLinkClick(event: MouseEvent) {
  const anchor = (event.target as HTMLElement).closest('a')
  if (anchor) {
    const href = anchor.getAttribute('href')
    if (href && href.startsWith('/') && !href.startsWith('//')) {
      event.preventDefault()
      router.push(href)
    }
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageBox.value) {
    messageBox.value.scrollTop = messageBox.value.scrollHeight
  }
}

async function sendQuick(text: string) {
  inputMessage.value = text
  await sendMessage()
}

function triggerImageUpload() {
  imageInput.value?.click()
}

function handleImageChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  if (file.size > IMAGE_UPLOAD_MAX_SIZE) {
    ElMessage.error('图片大小不能超过5MB')
    target.value = ''
    return
  }

  const reader = new FileReader()

  reader.onload = () => {
    const result = reader.result as string
    imageBase64.value = result
    imagePreviewUrl.value = result
    sendMessage()
  }

  reader.onerror = () => {
    ElMessage.error('图片读取失败')
  }

  reader.readAsDataURL(file)

  target.value = ''
}

function clearImage() {
  imageBase64.value = ''
  imagePreviewUrl.value = ''
}

// ============================================================
// 第 9 步：发送消息主函数（核心逻辑）
// ============================================================

function appendCartSummary(responseText: string, cart: CartItem[]): string {
  if (!Array.isArray(cart)) return responseText

  if (cart.length > 0) {
    const total = cart.reduce((sum, item) => sum + (item.unit_price || 0) * (item.quantity || 1), 0)
    const cartLines = cart.map(item => `• ${item.name} x${item.quantity} = ¥${((item.unit_price || 0) * item.quantity).toFixed(0)}`)
    const cartSummary = `\n\n────────────\n🛒 当前购物车（合计 ¥${total.toFixed(0)}）\n${cartLines.join('\n')}`
    if (!responseText.includes('购物车')) {
      responseText += cartSummary
    }
    cartStore.setCart(cart)
  } else if (cart.length === 0 && cartStore.items.length > 0) {
    cartStore.clearCart()
    if (!responseText.includes('购物车')) {
      responseText += '\n\n────────────\n🛒 购物车已清空'
    }
  }

  return responseText
}

async function sendMessage() {
  const text = inputMessage.value.trim()

  const hasImage = !!imageBase64.value

  if (!text && !hasImage) return

  stopVoiceInput()
  interruptTypewriter?.()
  interruptTypewriter = null
  stopSpeaking()
  ttsFlushed = false

  const userMessage: { role: 'user'; content: string; imageUrl?: string } = {
    role: 'user',
    content: text || '[图片]',
  }

  if (hasImage) {
    userMessage.imageUrl = imagePreviewUrl.value
  }

  chatStore.addMessage(userMessage)

  inputMessage.value = ''

  const currentImageBase64 = imageBase64.value
  clearImage()

  loading.value = true

  avatarStatus.value = 'thinking'

  await scrollToBottom()

  let rawResponse = ''
  let assistantIndex = -1
  const mySeq = speakSeq

  // GPT 风格打字机：SSE 原文进入缓冲，前端匀速逐字渲染（积压越多走得越快，平滑追赶）
  let shownLen = 0
  let streamDone = false
  let finalText = ''
  let twTimer: number | null = null
  const interruptThis = () => {
    if (twTimer !== null) {
      clearInterval(twTimer)
      twTimer = null
    }
    if (interruptTypewriter === interruptThis) interruptTypewriter = null
    // 中断时把已收到的原文一次性落地，避免消息停在半截
    if (assistantIndex >= 0) {
      chatStore.updateMessage(assistantIndex, { role: 'assistant', content: streamDone ? finalText : rawResponse })
    }
  }
  interruptTypewriter = interruptThis

  try {
    const currentCart: CartItem[] = JSON.parse(JSON.stringify(cartStore.items || []))

    const payload: ChatRequest = {
      user_id: authStore.userId ?? 0,
      message: text,
      cart: currentCart,
    }

    if (currentImageBase64) {
      payload.image_base64 = currentImageBase64
    }

    // 先插入一条空 assistant 消息，用于流式逐字显示
    chatStore.addMessage({ role: 'assistant', content: '' })
    assistantIndex = messages.value.length - 1

    for await (const event of sendChatMessageStream(payload)) {
      // 首个事件（正文或过渡提示）到达即撤下“思考中”指示器
      if (loading.value) loading.value = false
      if (event.type === 'text' && event.content) {
        rawResponse += event.content
        feedTts(event.content, mySeq)
        if (twTimer === null) {
          twTimer = window.setInterval(() => {
            if (shownLen < rawResponse.length) {
              const backlog = rawResponse.length - shownLen
              shownLen += Math.max(1, Math.ceil(backlog / 12))
              chatStore.updateMessage(assistantIndex, { role: 'assistant', content: rawResponse.slice(0, shownLen) })
              void scrollToBottom()
            } else if (streamDone) {
              interruptThis()
            }
          }, 24)
        }
      } else if (event.type === 'status' && event.content) {
        // 工具执行中的过渡提示（如“正在查询订单…”），正文到达后即被覆盖
        if (!rawResponse) {
          chatStore.updateMessage(assistantIndex, { role: 'assistant', content: event.content })
          await scrollToBottom()
        }
      } else if (event.type === 'done') {
        finalText = appendCartSummary(rawResponse, event.cart || [])
        streamDone = true
        flushTts(mySeq)
        if (twTimer === null) interruptThis() // 无正文时直接落地最终文本
      } else if (event.type === 'error') {
        interruptThis()
        chatStore.updateMessage(assistantIndex, { role: 'assistant', content: '抱歉，服务暂时异常，请稍后重试。' })
        stopSpeaking()
        avatarStatus.value = 'idle'
        console.error(event.message)
      }
    }
  } catch (err) {
    interruptThis()
    if (assistantIndex >= 0) {
      chatStore.updateMessage(assistantIndex, { role: 'assistant', content: '抱歉，服务暂时异常，请稍后重试。' })
    } else {
      chatStore.addMessage({ role: 'assistant', content: '抱歉，服务暂时异常，请稍后重试。' })
    }
    stopSpeaking()
    avatarStatus.value = 'idle'
    console.error(err)
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

// ============================================================
// 第 10 步：语音相关函数
// ============================================================

// 语音播报：浏览器内置 speechSynthesis，分句流水线——SSE 每凑满一个完整句子
// 立即推入浏览器语音队列（原生按序播报、句间无停顿），第一句出现时即可出声。
const TTS_END_RE = /[^。！？!?；;\n]+[。！？!?；;\n]+/g
const TTS_SOFT_RE = /[，、：,]/
const TTS_LONG = 30 // 缓冲区超过该长度且无句末标点时，按次级标点软切分
const TTS_SOFT_MIN = 16 // 软切分点之前至少保留的字符数

let speakSeq = 0 // 发送新消息时递增，使进行中的播放流程失效
let ttsBuffer = ''
let ttsPending = 0 // 已推入浏览器队列但尚未播完的句子数
let ttsFlushed = false // 流式文本是否已全部进入播报队列

// 进行中的打字机中断函数（新消息发送时打断上一轮的逐字渲染）
let interruptTypewriter: (() => void) | null = null

/** TTS 输入净化：去掉 markdown/emoji 符号，数量/金额/编号转为自然口语，避免被读出来 */
function cleanTtsText(s: string): string {
  return s
    .replace(/#(\d+)/g, '$1号')                                       // 订单 #28 -> 28号
    .replace(/\[(\d+)\]/g, '$1号')                                    // 订单 [28] -> 28号
    .replace(/[x×]\s*(\d+)/g, '$1份')                                // 宫保鸡丁 ×2 -> 宫保鸡丁 2份
    .replace(/¥\s*(\d+(?:\.\d+)?)/g, (_, n) => `${parseFloat(n)}元`) // ¥186.0 -> 186元
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/gu, '')
    .replace(/[*#>`•·─━~|]+/g, '')
    .replace(/-{3,}/g, '，')
    .replace(/\s+/g, ' ')
    .trim()
}

/** 从缓冲区切出完整句子；长句按次级标点软切分；flushAll 时把剩余文本一并切出 */
function drainTtsSentences(flushAll = false): string[] {
  const out: string[] = []
  TTS_END_RE.lastIndex = 0
  let m: RegExpExecArray | null
  let last = 0
  while ((m = TTS_END_RE.exec(ttsBuffer)) !== null) {
    out.push(m[0])
    last = TTS_END_RE.lastIndex
  }
  ttsBuffer = ttsBuffer.slice(last)

  // 长句软切分：降低首句等待
  if (!flushAll && ttsBuffer.length > TTS_LONG) {
    for (let i = TTS_SOFT_MIN; i < ttsBuffer.length; i++) {
      if (TTS_SOFT_RE.test(ttsBuffer[i])) {
        out.push(ttsBuffer.slice(0, i + 1))
        ttsBuffer = ttsBuffer.slice(i + 1)
        break
      }
    }
  }
  if (flushAll && ttsBuffer.trim()) {
    out.push(ttsBuffer)
    ttsBuffer = ''
  }
  return out
}

/** 把句子推入浏览器语音队列（speechSynthesis 原生按序连续播报） */
function enqueueTts(sentence: string) {
  if (!window.speechSynthesis) return
  const text = cleanTtsText(sentence)
  if (text.length < 2) return
  const seq = speakSeq
  ttsPending++
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 1.1
  utter.onstart = () => {
    if (seq === speakSeq) avatarStatus.value = 'speaking'
  }
  utter.onend = () => {
    ttsPending--
    if (seq === speakSeq && ttsPending <= 0 && ttsFlushed) {
      avatarStatus.value = 'idle'
    }
  }
  window.speechSynthesis.speak(utter)
}

/** 流式文本到达时喂入语音队列（seq 过期说明已有新消息，直接丢弃） */
function feedTts(chunk: string, seq: number) {
  if (!speechEnabled.value || seq !== speakSeq) return
  ttsBuffer += chunk
  for (const s of drainTtsSentences()) enqueueTts(s)
}

/** 流式输出结束：剩余文本送入播报并收尾 */
function flushTts(seq: number) {
  if (seq !== speakSeq) return
  ttsFlushed = true
  if (!speechEnabled.value) return
  for (const s of drainTtsSentences(true)) enqueueTts(s)
  if (ttsPending === 0) avatarStatus.value = 'idle'
}

function stopSpeaking() {
  speakSeq++
  ttsBuffer = ''
  ttsPending = 0
  if (window.speechSynthesis) window.speechSynthesis.cancel()
}

function toggleSpeech() {
  speechEnabled.value = !speechEnabled.value
  localStorage.setItem(STORAGE_KEY_SPEECH, speechEnabled.value ? 'true' : 'false')
  if (!speechEnabled.value) stopSpeaking()
}

// ============================================================
// 第 11 步：下单相关函数
// ============================================================

async function confirmOrder() {
  await sendQuick('确认下单')
}

async function confirmOrderFromDrawer() {
  cartVisible.value = false
  await sendQuick('确认下单')
}

// ============================================================
// 第 12 步：清空对话函数
// ============================================================

async function handleClearChat() {
  try {
    await ElMessageBox.confirm('确定要清空当前对话记录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })

    // 先删服务端 MongoDB 中该用户的聊天记录，失败则不清空并提示
    try {
      await clearChatHistory()
    } catch {
      ElMessage.error('服务端聊天记录删除失败，请稍后重试')
      return
    }

    chatStore.clearMessages()   // 清空聊天消息
    markdownCache.clear()       // 清空 Markdown 缓存
    await scrollToBottom()      // 滚动到底部
    ElMessage.success('对话已清空') // 显示成功提示
  } catch {
  }
}
</script>

<style scoped>

.chat-container {
  display: flex;
  flex-direction: row;
  height: 100%;
  background: #fff;
  position: relative;
}

.chat-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  padding: 16px 0 8px;
  text-align: center;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding-top: 6px;
}

.avatar-area {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: center;
  gap: 12px;
  width: 160px;
  flex-shrink: 0;
  padding: 0 8px 8px;
  border-right: 1px solid #f0f0f0;
}

.speech-toggle {
  margin-top: 4px;
}

/* 录音中的麦克风按钮呼吸光圈 */
.recording-pulse {
  animation: recording-pulse 1.2s infinite;
}

@keyframes recording-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.5);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(245, 108, 108, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(245, 108, 108, 0);
  }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px;
  margin-bottom: 10px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 16px;
  gap: 10px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.user-avatar {
  background-color: #409eff;
  flex-shrink: 0;
}

.bot-avatar {
  background-color: #67c23a;
  flex-shrink: 0;
}

.message-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.message-row.user .message-bubble {
  background-color: #dfebff;
  color: #333;
}

.message-row.bot .message-bubble {
  background-color: #f4f4f5;
  color: #333;
}

.message-text :deep(h1),
.message-text :deep(h2),
.message-text :deep(h3) {
  margin: 8px 0 4px;
  font-weight: 600;
}

.message-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}

.message-text :deep(th),
.message-text :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
}

.message-text :deep(th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

.message-text :deep(tr:nth-child(even)) {
  background-color: #fafafa;
}

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.message-text :deep(li) {
  margin: 2px 0;
}

.message-text :deep(code) {
  background-color: #f0f0f0;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
}

.message-text :deep(pre) {
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
}

.message-text :deep(blockquote) {
  border-left: 3px solid #409eff;
  margin: 8px 0;
  padding-left: 10px;
  color: #666;
}

.quick-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding: 0 4px;
}

.chat-input-area {
  padding: 0 4px;
}

.image-preview-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.preview-thumb {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  border: 1px solid #dcdfe6;
}

.message-image {
  margin-bottom: 8px;
}

.message-image-thumb {
  width: 120px;
  height: 120px;
  border-radius: 8px;
  cursor: pointer;
}

.cart-fab {
  position: absolute;
  right: 24px;
  bottom: 80px;
}

.cart-footer {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.cart-total {
  font-size: 16px;
  font-weight: bold;
  color: #f56c6c;
}
</style>
