<!-- 用户设置页面：查看和修改个人信息 -->
<template>
  <div class="settings-page">
    <div class="settings-container">
      <el-card class="settings-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <div class="header-title">
              <el-icon :size="22"><User /></el-icon>
              <span>个人资料</span>
            </div>
            <el-button v-if="!isEditing" type="primary" :icon="Edit" @click="startEdit">
              编辑资料
            </el-button>
          </div>
        </template>

        <!-- 编辑模式 -->
        <el-form v-if="isEditing" ref="formRef" :model="form" :rules="rules" label-width="90px" class="edit-form">
          <el-form-item label="用户名">
            <el-input v-model="form.username" disabled />
          </el-form-item>
          <el-form-item label="角色">
            <el-input :model-value="form.role === 'admin' ? '商家' : '顾客'" disabled />
          </el-form-item>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="form.phone" placeholder="请输入手机号（选填）" maxlength="20" />
          </el-form-item>
          <el-form-item label="性别" prop="gender">
            <el-select v-model="form.gender" placeholder="请选择性别" style="width: 100%">
              <el-option label="未知" value="unknown" />
              <el-option label="男" value="male" />
              <el-option label="女" value="female" />
            </el-select>
          </el-form-item>
          <el-form-item label="出生日期" prop="birth_date">
            <el-date-picker
              v-model="form.birth_date"
              type="date"
              placeholder="选择出生日期"
              style="width: 100%"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
          <el-form-item class="form-actions">
            <el-button @click="cancelEdit">取消</el-button>
            <el-button type="primary" @click="submitUpdate" :loading="saving">保存</el-button>
          </el-form-item>
        </el-form>

        <!-- 展示模式 -->
        <div v-else class="profile-body">
          <div class="profile-hero">
            <div class="avatar-circle">
              {{ displayName.charAt(0).toUpperCase() }}
            </div>
            <div class="hero-info">
              <h3 class="hero-name">{{ displayName }}</h3>
              <el-tag :type="userInfo.role === 'admin' ? 'danger' : 'info'" size="small" effect="light">
                {{ userInfo.role === 'admin' ? '商家' : '顾客' }}
              </el-tag>
            </div>
          </div>

          <el-divider class="section-divider" />

          <div class="info-grid">
            <div class="info-card">
              <div class="info-icon"><el-icon><Iphone /></el-icon></div>
              <div class="info-content">
                <span class="info-label">手机号</span>
                <span class="info-value" :class="{ empty: !userInfo.phone }">
                  {{ userInfo.phone || '未填写' }}
                </span>
              </div>
            </div>

            <div class="info-card">
              <div class="info-icon"><el-icon><Male /></el-icon></div>
              <div class="info-content">
                <span class="info-label">性别</span>
                <span class="info-value">{{ genderText(userInfo.gender) }}</span>
              </div>
            </div>

            <div class="info-card">
              <div class="info-icon"><el-icon><Calendar /></el-icon></div>
              <div class="info-content">
                <span class="info-label">出生日期</span>
                <span class="info-value" :class="{ empty: !userInfo.birth_date }">
                  {{ userInfo.birth_date || '未填写' }}
                </span>
              </div>
            </div>

            <div class="info-card">
              <div class="info-icon"><el-icon><VideoCamera /></el-icon></div>
              <div class="info-content">
                <span class="info-label">人脸登录</span>
                <div class="info-row">
                  <el-tag :type="userInfo.has_face ? 'success' : 'warning'" size="small" effect="light">
                    {{ userInfo.has_face ? '已录入' : '未录入' }}
                  </el-tag>
                  <el-button link type="primary" size="small" :icon="userInfo.has_face ? RefreshRight : Plus" @click="openFaceRegister">
                    {{ userInfo.has_face ? '重新录入' : '录入人脸' }}
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 人脸录入弹窗 -->
    <el-dialog
      v-model="showFaceRegister"
      title="录入人脸"
      width="420px"
      align-center
      :close-on-click-modal="false"
      @close="stopCamera"
    >
      <div class="face-register-body">
        <el-radio-group v-model="faceInputMode" class="mode-switch">
          <el-radio-button label="camera">摄像头拍摄</el-radio-button>
          <el-radio-button label="file">上传照片</el-radio-button>
        </el-radio-group>

        <div class="camera-wrapper">
          <video
            v-show="faceInputMode === 'camera'"
            ref="videoRef"
            class="camera-video"
            autoplay
            playsinline
            muted
          ></video>
          <img
            v-show="faceInputMode === 'file' && filePreviewUrl"
            :src="filePreviewUrl"
            class="preview-image"
            alt="人脸预览"
          />
          <div v-if="faceInputMode === 'file' && !filePreviewUrl" class="preview-placeholder">
            <el-icon><Picture /></el-icon>
            <span>请选择一张清晰的人脸照片</span>
          </div>
          <div v-if="faceRegisterLoading" class="camera-overlay">
            <el-icon class="scan-icon"><Loading /></el-icon>
            <span>处理中…</span>
          </div>
        </div>

        <input
          v-if="faceInputMode === 'file'"
          ref="fileInputRef"
          type="file"
          accept="image/*"
          style="display: none"
          @change="handleFileChange"
        />
        <el-button
          v-if="faceInputMode === 'file'"
          size="large"
          style="width: 100%"
          @click="fileInputRef?.click()"
        >
          选择照片
        </el-button>

        <p class="face-tip">
          {{ faceInputMode === 'camera' ? '请将面部正对摄像头，点击“拍照并保存”按钮' : '请上传一张正面、清晰、光线充足的人脸照片' }}
        </p>
        <el-button
          type="primary"
          size="large"
          style="width: 100%"
          :loading="faceRegisterLoading"
          @click="submitFaceRegister"
        >
          {{ faceInputMode === 'camera' ? '拍照并保存' : '保存人脸' }}
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { getProfile, updateProfile, registerFace } from '@/features/auth/api/auth.api'
import {
  VideoCamera,
  Loading,
  Picture,
  User,
  Edit,
  Iphone,
  Male,
  Calendar,
  RefreshRight,
  Plus,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/features/auth/stores/auth.store'
import type { User as UserType } from '@/shared/types'

const authStore = useAuthStore()

const userInfo = ref<Partial<UserType>>({})
const isEditing = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()
const showFaceRegister = ref(false)
const faceRegisterLoading = ref(false)
const faceInputMode = ref<'camera' | 'file'>('camera')
const filePreviewUrl = ref('')
const fileBase64 = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const videoRef = ref<HTMLVideoElement | null>(null)
let stream: MediaStream | null = null

const displayName = computed(() => userInfo.value.username || '用户')

watch(faceInputMode, async (mode) => {
  if (mode === 'camera') {
    filePreviewUrl.value = ''
    fileBase64.value = ''
    await startCamera()
  } else {
    stopCamera()
  }
})

const form = reactive({
  username: '',
  role: 'customer' as 'customer' | 'admin' | 'superadmin',
  phone: '',
  gender: undefined as 'unknown' | 'male' | 'female' | undefined,
  birth_date: '',
})

const rules: FormRules = {
  phone: [
    { pattern: /^1[3-9]\d{9}$|^$/, message: '手机号格式不正确', trigger: 'blur' },
  ],
}

function genderText(gender?: 'unknown' | 'male' | 'female' | null | string) {
  if (gender === 'male') return '男'
  if (gender === 'female') return '女'
  if (gender === 'unknown') return '未知'
  return '未填写'
}

function syncFormFromUser(user: Partial<UserType>) {
  form.username = user.username || ''
  form.role = user.role || 'customer'
  form.phone = user.phone || ''
  form.gender = user.gender || undefined
  form.birth_date = user.birth_date || ''
}

async function loadProfile() {
  try {
    const res = await getProfile()
    userInfo.value = res.data
    syncFormFromUser(res.data)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取个人信息失败')
  }
}

function startEdit() {
  syncFormFromUser(userInfo.value)
  isEditing.value = true
}

function cancelEdit() {
  isEditing.value = false
}

async function submitUpdate() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    saving.value = true
    try {
      const payload: {
        phone?: string
        gender?: 'unknown' | 'male' | 'female'
        birth_date?: string
      } = {}
      if (form.phone) payload.phone = form.phone
      if (form.gender) payload.gender = form.gender
      if (form.birth_date) payload.birth_date = form.birth_date

      const res = await updateProfile(payload)
      userInfo.value = res.data
      // 同步更新全局 auth store 中的用户信息
      if (authStore.auth) {
        authStore.auth.phone = res.data.phone
        authStore.auth.gender = res.data.gender
        authStore.auth.birth_date = res.data.birth_date
      }
      ElMessage.success('资料更新成功')
      isEditing.value = false
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '更新失败')
    } finally {
      saving.value = false
    }
  })
}

onMounted(() => {
  loadProfile()
})

async function openFaceRegister() {
  showFaceRegister.value = true
  faceInputMode.value = 'camera'
  filePreviewUrl.value = ''
  fileBase64.value = ''
  await startCamera()
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true })
    if (videoRef.value) {
      videoRef.value.srcObject = stream
    }
  } catch (err) {
    ElMessage.error('无法访问摄像头，请检查权限设置')
    console.error(err)
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
  if (videoRef.value) {
    videoRef.value.srcObject = null
  }
}

function captureImage(): string | null {
  if (!videoRef.value || !videoRef.value.videoWidth) {
    return null
  }
  const canvas = document.createElement('canvas')
  canvas.width = videoRef.value.videoWidth
  canvas.height = videoRef.value.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(videoRef.value, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.9)
}

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    const result = e.target?.result as string
    fileBase64.value = result
    filePreviewUrl.value = result
  }
  reader.readAsDataURL(file)
}

async function submitFaceRegister() {
  let imageBase64 = ''
  if (faceInputMode.value === 'camera') {
    imageBase64 = captureImage() || ''
    if (!imageBase64) {
      ElMessage.warning('未获取到摄像头画面，请重试')
      return
    }
  } else {
    imageBase64 = fileBase64.value
    if (!imageBase64) {
      ElMessage.warning('请先选择一张照片')
      return
    }
  }

  faceRegisterLoading.value = true
  try {
    const res = await registerFace({ face_image_base64: imageBase64 })
    userInfo.value = res.data
    if (authStore.auth) {
      authStore.auth.has_face = res.data.has_face
    }
    ElMessage.success('人脸录入成功')
    showFaceRegister.value = false
    stopCamera()
    filePreviewUrl.value = ''
    fileBase64.value = ''
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '人脸录入失败')
  } finally {
    faceRegisterLoading.value = false
  }
}
</script>

<style scoped>
.settings-page {
  min-height: 100%;
  padding: 24px;
  background: linear-gradient(180deg, #f0f7ff 0%, #f5f7fa 100%);
}

.settings-container {
  max-width: 720px;
  margin: 0 auto;
}

.settings-card {
  border-radius: 16px;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.profile-body {
  padding: 8px 8px 16px;
}

.profile-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 16px 0 8px;
}

.avatar-circle {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff 0%, #79bbff 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  font-weight: 600;
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.25);
}

.hero-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.hero-name {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.section-divider {
  margin: 16px 0 24px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.info-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px;
  background: #f7f8fa;
  border-radius: 12px;
  transition: background 0.2s ease;
}

.info-card:hover {
  background: #eef3fb;
}

.info-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #fff;
  color: #409eff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  flex-shrink: 0;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.info-label {
  font-size: 13px;
  color: #909399;
}

.info-value {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  word-break: break-all;
}

.info-value.empty {
  color: #c0c4cc;
  font-weight: 400;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.edit-form {
  padding: 8px 8px 0;
}

.form-actions {
  margin-top: 8px;
}

.face-register-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.camera-wrapper {
  position: relative;
  width: 320px;
  height: 240px;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.camera-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.camera-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  gap: 8px;
}

.scan-icon {
  font-size: 32px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.face-tip {
  color: #606266;
  font-size: 14px;
  margin: 0;
  text-align: center;
}

.mode-switch {
  display: flex;
  justify-content: center;
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}

.preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  gap: 8px;
  font-size: 14px;
}

.preview-placeholder .el-icon {
  font-size: 32px;
}

@media (max-width: 640px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
