<!--
  超级管理员面板（rootroot）
  功能从简：
  1. 重置管理员 root 密码为初始值 123456
  2. 查看普通用户的智能聊天剩余次数，支持加 100 次 / 删除用户
  首次登录强制修改密码（仅允许修改一次，由后端强制约束）
-->
<template>
  <div class="superadmin-page">
    <el-card class="panel" shadow="hover">
      <template #header>
        <div class="panel-header">
          <el-icon :size="22"><Key /></el-icon>
          <span>超级管理员面板</span>
          <el-button class="logout-link" link type="primary" @click="handleLogout">退出登录</el-button>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="当管理员 root 的密码遗忘或被修改后，可在此将其重置为初始值 123456。重置后 root 下次登录会被要求修改密码。"
        class="tip"
      />

      <el-button
        type="danger"
        :loading="resetting"
        class="reset-btn"
        @click="handleReset"
      >
        重置 root 密码为 123456
      </el-button>

      <el-divider content-position="left">用户智能聊天次数管理</el-divider>

      <el-table :data="userQuotas" v-loading="quotaLoading" size="small" max-height="420">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="chat_quota" label="剩余聊天次数" width="110" align="center" />
        <el-table-column label="操作" min-width="200">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :loading="row._operating"
              @click="handleRecharge(row)"
            >
              加100聊天次数
            </el-button>
            <el-button
              size="small"
              type="danger"
              :loading="row._operating"
              @click="handleDeleteUser(row)"
            >
              删除用户
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无普通用户</template>
      </el-table>
    </el-card>

    <!-- 首次登录强制修改密码（仅允许修改一次） -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="首次登录请修改密码"
      width="400px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="超级管理员密码仅允许修改一次，请妥善保管新密码。"
        class="pwd-tip"
      />
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top">
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="passwordForm.new_password"
            type="password"
            placeholder="请输入新密码（至少 6 位）"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input
            v-model="passwordForm.confirm_password"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="changingPassword" @click="submitChangePassword">
          确认修改
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { Key } from "@element-plus/icons-vue";
import { useAuthStore } from "@/features/auth/stores/auth.store";
import { changePassword } from "@/features/auth/api/auth.api";
import {
  resetRootPassword,
  fetchUserQuotas,
  rechargeUserQuota,
  deleteUser,
} from "@/modules/admin/api/admin.api";
import type { UserQuota } from "@/modules/admin/api/admin.api";

type UserQuotaRow = UserQuota & { _operating?: boolean };

const router = useRouter();
const authStore = useAuthStore();
const resetting = ref(false);

// ==================== 重置 root 密码 ====================
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

// ==================== 用户聊天次数管理 ====================
const userQuotas = ref<UserQuotaRow[]>([]);
const quotaLoading = ref(false);

async function loadQuotas() {
  quotaLoading.value = true;
  try {
    const res = await fetchUserQuotas();
    userQuotas.value = res.data;
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "加载用户列表失败");
  } finally {
    quotaLoading.value = false;
  }
}

async function handleRecharge(row: UserQuotaRow) {
  row._operating = true;
  try {
    const res = await rechargeUserQuota(row.id);
    row.chat_quota = res.data.chat_quota;
    ElMessage.success(res.data.message);
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "充值失败");
  } finally {
    row._operating = false;
  }
}

async function handleDeleteUser(row: UserQuotaRow) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户「${row.username}」吗？其订单与聊天记录将一并删除，不可恢复。`,
      "删除确认",
      { confirmButtonText: "确定删除", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return; // 用户取消
  }
  row._operating = true;
  try {
    const res = await deleteUser(row.id);
    ElMessage.success(res.data.message);
    await loadQuotas();
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || "删除失败");
  } finally {
    row._operating = false;
  }
}

// ==================== 首次登录强制修改密码 ====================
const passwordDialogVisible = ref(false);
const changingPassword = ref(false);
const passwordFormRef = ref<FormInstance>();
const passwordForm = reactive({ new_password: "", confirm_password: "" });

const passwordRules: FormRules = {
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, message: "密码长度至少 6 位", trigger: "blur" },
  ],
  confirm_password: [
    { required: true, message: "请再次输入新密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== passwordForm.new_password) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

async function submitChangePassword() {
  if (!passwordFormRef.value) return;
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return;
    changingPassword.value = true;
    try {
      await changePassword({ new_password: passwordForm.new_password });
      authStore.clearNeedChangePassword();
      passwordDialogVisible.value = false;
      ElMessage.success("密码修改成功，请牢记新密码");
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || "密码修改失败");
    } finally {
      changingPassword.value = false;
    }
  });
}

function handleLogout() {
  authStore.logout();
  router.push("/login");
}

onMounted(() => {
  loadQuotas();
  if (authStore.needChangePassword) {
    passwordDialogVisible.value = true;
  }
});
</script>

<style scoped>
.superadmin-page {
  min-height: 100vh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  background: #f5f7fa;
  padding: 40px 20px;
}

.panel {
  width: 100%;
  max-width: 640px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.logout-link {
  margin-left: auto;
}

.tip {
  margin-bottom: 16px;
}

.reset-btn {
  width: 100%;
}

.pwd-tip {
  margin-bottom: 16px;
}
</style>
