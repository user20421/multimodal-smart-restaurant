<!--
  超级管理员面板（rootroot）
  功能从简：仅提供"重置管理员 root 密码为初始值 123456"和退出登录
-->
<template>
  <div class="superadmin-page">
    <el-card class="panel" shadow="hover">
      <template #header>
        <div class="panel-header">
          <el-icon :size="22"><Key /></el-icon>
          <span>超级管理员面板</span>
        </div>
      </template>

      <el-descriptions :column="1" border class="info">
        <el-descriptions-item label="当前账号">{{ authStore.user?.username }}</el-descriptions-item>
        <el-descriptions-item label="角色">超级管理员</el-descriptions-item>
      </el-descriptions>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="当管理员 root 的密码遗忘或被修改后，可在此将其重置为初始值 123456。重置后 root 下次登录会被要求修改密码。"
        class="tip"
      />

      <el-button
        type="danger"
        size="large"
        :loading="resetting"
        class="reset-btn"
        @click="handleReset"
      >
        重置 root 密码为 123456
      </el-button>

      <el-divider />

      <el-button class="logout-btn" @click="handleLogout">退出登录</el-button>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Key } from "@element-plus/icons-vue";
import { useAuthStore } from "@/features/auth/stores/auth.store";
import { resetRootPassword } from "@/modules/admin/api/admin.api";

const router = useRouter();
const authStore = useAuthStore();
const resetting = ref(false);

async function handleReset() {
  try {
    await ElMessageBox.confirm(
      "确定要将管理员 root 的密码重置为初始值 123456 吗？",
      "重置确认",
      { confirmButtonText: "确定重置", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return; // 用户取消
  }
  resetting.value = true;
  try {
    const res = await resetRootPassword();
    ElMessage.success(res.data.message || "重置成功");
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "重置失败，请稍后重试");
  } finally {
    resetting.value = false;
  }
}

function handleLogout() {
  authStore.logout();
  router.push("/login");
}
</script>

<style scoped>
.superadmin-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  padding: 20px;
}

.panel {
  width: 100%;
  max-width: 480px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.info {
  margin-bottom: 16px;
}

.tip {
  margin-bottom: 20px;
}

.reset-btn {
  width: 100%;
}

.logout-btn {
  width: 100%;
}
</style>
