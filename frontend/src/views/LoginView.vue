<!-- 登录/注册页面：支持顾客和商家角色切换 -->
<template>
  <div class="login-container">
    <el-card class="login-card" shadow="hover">
      <template #header>
        <div class="login-header">
          <el-icon :size="40" color="#409eff"><Food /></el-icon>
          <h2>美味餐厅</h2>
        </div>
      </template>

      <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            size="large"
          />
        </el-form-item>

        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            show-password
          />
        </el-form-item>

        <el-form-item label="验证码">
          <div class="captcha-row">
            <el-input
              v-model="form.captcha_code"
              placeholder="请输入验证码"
              size="large"
              maxlength="4"
              style="flex: 1"
              @keyup.enter="handleLogin"
            />
            <img
              v-if="captchaImage"
              :src="captchaImage"
              alt="验证码"
              class="captcha-image"
              @click="loadCaptcha"
              title="点击刷新"
            />
            <div v-else class="captcha-placeholder" @click="loadCaptcha">点击获取</div>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            @click="handleLogin"
            :loading="loading"
          >
            登录
          </el-button>
        </el-form-item>

        <el-form-item>
          <div class="extra-actions">
            <el-button
              size="large"
              class="extra-btn"
              @click="openFaceLogin"
            >
              <el-icon><VideoCamera /></el-icon>
              人脸登录
            </el-button>
            <el-button
              size="large"
              class="extra-btn"
              @click="showRegister = true"
            >
              注册新账号
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 人脸登录弹窗 -->
    <el-dialog
      v-model="showFaceLogin"
      title="人脸登录"
      width="420px"
      align-center
      :close-on-click-modal="false"
      :show-close="!faceLoginSuccess"
      @close="stopCamera"
    >
      <div class="face-login-body">
        <div class="camera-wrapper">
          <video
            ref="videoRef"
            class="camera-video"
            autoplay
            playsinline
            muted
          ></video>
          <div v-if="faceLoginLoading" class="camera-overlay">
            <el-icon class="scan-icon"><Loading /></el-icon>
            <span>识别中…</span>
          </div>
          <div v-if="faceLoginSuccess" class="camera-overlay success-overlay">
            <el-icon class="success-icon"><CircleCheck /></el-icon>
            <span class="success-text">识别到用户：{{ recognizedUserName }}</span>
            <span class="success-sub">相似度：{{ faceSimilarity }}%</span>
            <span class="success-sub">正在登录…</span>
          </div>
        </div>
        <p v-if="!faceLoginSuccess" class="face-tip">请将面部正对摄像头，点击“开始识别”按钮</p>
        <el-button
          v-if="!faceLoginSuccess"
          type="primary"
          size="large"
          style="width: 100%"
          :loading="faceLoginLoading"
          @click="captureAndLogin"
        >
          开始识别
        </el-button>
      </div>
    </el-dialog>

    <!-- 注册弹窗 -->
    <el-dialog v-model="showRegister" title="用户注册" width="400px">
      <el-form :model="registerForm" label-position="top">
        <el-form-item label="用户名">
          <el-input
            v-model="registerForm.username"
            placeholder="请输入用户名"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="registerForm.password"
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            show-password
          />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input
            v-model="registerForm.phone"
            placeholder="请输入手机号（选填）"
            maxlength="20"
          />
        </el-form-item>
        <el-form-item label="性别" required>
          <el-select v-model="registerForm.gender" placeholder="请选择性别" style="width: 100%">
            <el-option label="未知" value="unknown" />
            <el-option label="男" value="male" />
            <el-option label="女" value="female" />
          </el-select>
        </el-form-item>
        <el-form-item label="出生日期">
          <el-date-picker
            v-model="registerForm.birth_date"
            type="date"
            placeholder="选择出生日期"
            style="width: 100%"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRegister = false">取消</el-button>
        <el-button
          type="primary"
          @click="handleRegister"
          :loading="registerLoading"
          >注册</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Food, VideoCamera, Loading, CircleCheck } from "@element-plus/icons-vue";
import { login, register, getCaptcha, faceLogin } from "@/features/auth/api/auth.api";
import { useAuthStore } from "@/features/auth/stores/auth.store";
import { useChatStore } from "@/features/chat/stores/chat.store";
import { useCartStore } from "@/features/cart/stores/cart.store";
import type { ApiErrorDetail } from "@/shared/types";
import type { AxiosError } from "axios";

const router = useRouter();
const authStore = useAuthStore();
const chatStore = useChatStore();
const cartStore = useCartStore();

const form = reactive({
  username: "",
  password: "",
  captcha_id: "",
  captcha_code: "",
});

const captchaImage = ref("");

const loading = ref(false);
const showRegister = ref(false);
const registerLoading = ref(false);
const showFaceLogin = ref(false);
const faceLoginLoading = ref(false);
const faceLoginSuccess = ref(false);
const recognizedUserName = ref("");
const faceSimilarity = ref(0);
const videoRef = ref<HTMLVideoElement | null>(null);
let stream: MediaStream | null = null;
const LOGIN_DELAY_MS = 1500;
const registerForm = reactive({
  username: "",
  password: "",
  confirmPassword: "",
  phone: "",
  gender: "" as 'unknown' | 'male' | 'female' | '',
  birth_date: "",
});

async function loadCaptcha() {
  try {
    const res = await getCaptcha();
    form.captcha_id = res.data.captcha_id;
    captchaImage.value = res.data.image_base64;
    form.captcha_code = "";
  } catch (err) {
    const error = err as AxiosError<ApiErrorDetail>;
    ElMessage.error(error.response?.data?.detail || "验证码加载失败");
  }
}

onMounted(() => {
  loadCaptcha();
});

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  if (!form.captcha_code) {
    ElMessage.warning("请输入验证码");
    return;
  }
  loading.value = true;
  try {
    const res = await login({
      username: form.username,
      password: form.password,
      captcha_id: form.captcha_id,
      captcha_code: form.captcha_code,
    });
    const data = res.data;

    authStore.setAuth({ user: data.user, token: data.token || "" });
    chatStore.reloadMessages();
    cartStore.reloadCart();

    ElMessage.success(data.message);

    if (data.user.role === "admin") {
      router.push("/admin");
    } else {
      router.push("/chat");
    }
  } catch (err) {
    const error = err as AxiosError<ApiErrorDetail>;
    ElMessage.error(error.response?.data?.detail || "登录失败");
    // 登录失败后刷新验证码
    await loadCaptcha();
  } finally {
    loading.value = false;
  }
}

async function handleRegister() {
  if (!registerForm.username || !registerForm.password) {
    ElMessage.warning("请填写完整信息");
    return;
  }
  if (!registerForm.gender) {
    ElMessage.warning("请选择性别");
    return;
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    ElMessage.warning("两次输入的密码不一致");
    return;
  }
  registerLoading.value = true;
  try {
    await register({
      username: registerForm.username,
      password: registerForm.password,
      phone: registerForm.phone || undefined,
      gender: registerForm.gender,
      birth_date: registerForm.birth_date || undefined,
    });
    ElMessage.success("注册成功，请登录");
    showRegister.value = false;
    form.username = registerForm.username;
    form.password = registerForm.password;
    registerForm.username = "";
    registerForm.password = "";
    registerForm.confirmPassword = "";
    registerForm.phone = "";
    registerForm.gender = "";
    registerForm.birth_date = "";
  } catch (err) {
    const error = err as AxiosError<ApiErrorDetail>;
    ElMessage.error(error.response?.data?.detail || "注册失败");
  } finally {
    registerLoading.value = false;
  }
}

async function openFaceLogin() {
  showFaceLogin.value = true;
  await startCamera();
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (videoRef.value) {
      videoRef.value.srcObject = stream;
    }
  } catch (err) {
    ElMessage.error("无法访问摄像头，请检查权限设置");
    console.error(err);
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  if (videoRef.value) {
    videoRef.value.srcObject = null;
  }
}

function captureImage(): string | null {
  if (!videoRef.value || !videoRef.value.videoWidth) {
    return null;
  }
  const canvas = document.createElement("canvas");
  canvas.width = videoRef.value.videoWidth;
  canvas.height = videoRef.value.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(videoRef.value, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.9);
}

async function captureAndLogin() {
  const imageBase64 = captureImage();
  if (!imageBase64) {
    ElMessage.warning("未获取到摄像头画面，请重试");
    return;
  }
  faceLoginLoading.value = true;
  try {
    const res = await faceLogin({ face_image_base64: imageBase64 });
    const data = res.data;

    recognizedUserName.value = data.user.username;
    faceSimilarity.value = data.similarity ?? 0;
    faceLoginSuccess.value = true;
    faceLoginLoading.value = false;

    setTimeout(() => {
      authStore.setAuth({ user: data.user, token: data.token || "" });
      chatStore.reloadMessages();
      cartStore.reloadCart();

      showFaceLogin.value = false;
      stopCamera();
      faceLoginSuccess.value = false;
      recognizedUserName.value = "";
      faceSimilarity.value = 0;

      if (data.user.role === "admin") {
        router.push("/admin");
      } else {
        router.push("/chat");
      }
    }, LOGIN_DELAY_MS);
  } catch (err) {
    const error = err as AxiosError<ApiErrorDetail>;
    ElMessage.error(error.response?.data?.detail || "人脸识别失败，请通过密码登录");
    faceLoginLoading.value = false;
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: #f5f7fa;
}

.login-card {
  width: 420px;
}

.login-header {
  text-align: center;
}

.login-header h2 {
  margin: 10px 0 0;
  color: #303133;
}

.captcha-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.captcha-image {
  width: 120px;
  height: 44px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid #dcdfe6;
  object-fit: cover;
}

.captcha-placeholder {
  width: 120px;
  height: 44px;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 14px;
  cursor: pointer;
  background: #f5f7fa;
}

.extra-actions {
  display: flex;
  gap: 12px;
  width: 100%;
}

.extra-btn {
  flex: 1;
}

.face-login-body {
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

.success-overlay {
  background: rgba(103, 194, 58, 0.85);
}

.success-icon {
  font-size: 48px;
  color: #fff;
  animation: popIn 0.4s ease-out;
}

.success-text {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  animation: fadeInUp 0.5s ease-out;
}

.success-sub {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.9);
  animation: fadeInUp 0.6s ease-out;
}

@keyframes popIn {
  0% {
    transform: scale(0);
    opacity: 0;
  }
  80% {
    transform: scale(1.1);
    opacity: 1;
  }
  100% {
    transform: scale(1);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
