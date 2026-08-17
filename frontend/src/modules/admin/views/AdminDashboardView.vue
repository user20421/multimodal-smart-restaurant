<!-- 商家后台：概览仪表盘 -->
<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card>
          <div class="stat-title">今日订单</div>
          <div class="stat-value">{{ stats.today_orders }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-title">今日销售额</div>
          <div class="stat-value">¥{{ stats.today_revenue.toFixed(2) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-title">商品总数</div>
          <div class="stat-value">{{ stats.total_items }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-title">待处理订单</div>
          <div class="stat-value">{{ stats.pending_orders }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt-16">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>快捷入口</span>
            </div>
          </template>
          <div class="quick-entry">
            <el-button type="primary" @click="router.push('/admin/menu')">商品管理</el-button>
            <el-button type="success" @click="router.push('/admin/orders')">订单管理</el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近订单</span>
            </div>
          </template>
          <el-table :data="recentOrders" size="small" v-loading="loading">
            <el-table-column prop="id" label="订单号" width="80" />
            <el-table-column prop="total_price" label="总价" width="90">
              <template #default="scope">¥{{ scope.row.total_price.toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90">
              <template #default="scope">
                <el-tag :type="statusType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间">
              <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 强制修改密码对话框 -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="安全提示：请修改默认管理员密码"
      width="420px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
      destroy-on-close
    >
      <p class="password-tips">
        当前使用的是系统默认管理员账号（root / 123456），为了账号安全，请立即修改密码。
      </p>
      <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="100px">
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="请输入新密码" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password placeholder="请再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="submitChangePassword" :loading="changingPassword">
          确认修改
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { fetchDashboardStats, fetchAdminOrders } from '@/modules/admin/api/admin.api'
import { changePassword } from '@/features/auth/api/auth.api'
import { useAuthStore } from '@/features/auth/stores/auth.store'
import { formatDate } from '@/shared/utils/date'
import { statusType, statusText } from '@/features/orders/utils/status'
import type { Order } from '@/shared/types'

interface DashboardStats {
  today_orders: number
  today_revenue: number
  total_items: number
  pending_orders: number
}

const router = useRouter()
const authStore = useAuthStore()
const stats = ref<DashboardStats>({
  today_orders: 0,
  today_revenue: 0,
  total_items: 0,
  pending_orders: 0,
})
const recentOrders = ref<Order[]>([])
const loading = ref(false)

const passwordDialogVisible = ref(false)
const changingPassword = ref(false)
const passwordFormRef = ref<FormInstance>()
const passwordForm = reactive({
  new_password: '',
  confirm_password: '',
})

const validateConfirmPassword = (_rule: any, value: string, callback: any) => {
  if (value !== passwordForm.new_password) {
    callback(new Error('两次输入的新密码不一致'))
  } else {
    callback()
  }
}

const passwordRules: FormRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '新密码长度不能少于6位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

async function loadDashboard() {
  loading.value = true
  try {
    const [statsRes, ordersRes] = await Promise.all([
      fetchDashboardStats(),
      fetchAdminOrders({ page: 1, page_size: 5 }),
    ])
    stats.value = statsRes.data
    recentOrders.value = ordersRes.data.items.slice(0, 5)
  } catch (e) {
    ElMessage.error('加载仪表盘数据失败')
  } finally {
    loading.value = false
  }
}

async function submitChangePassword() {
  if (!passwordFormRef.value) return

  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return

    changingPassword.value = true
    try {
      await changePassword({
        new_password: passwordForm.new_password,
      })
      authStore.clearNeedChangePassword()
      passwordDialogVisible.value = false
      ElMessage.success('密码修改成功，请牢记新密码')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.detail || '密码修改失败')
    } finally {
      changingPassword.value = false
    }
  })
}

onMounted(() => {
  loadDashboard()
  if (authStore.needChangePassword) {
    passwordDialogVisible.value = true
  }
})
</script>

<style scoped>
.stat-title {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #333;
}

.mt-16 {
  margin-top: 16px;
}

.card-header {
  font-weight: 600;
}

.quick-entry {
  display: flex;
  gap: 12px;
}

.password-tips {
  color: #f56c6c;
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.6;
}
</style>
