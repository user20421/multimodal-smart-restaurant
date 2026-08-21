<!-- 根布局组件：侧边栏导航 + 主内容区，根据角色渲染不同菜单 -->
<template>
  <el-container v-if="!isLoginPage" class="layout-container">
    <el-aside width="180px" class="sidebar">
      <div class="logo">
        <el-icon size="32" color="#fff"><Food /></el-icon>
        <span class="title">{{ isAdmin ? '商家后台' : '美味餐厅' }}</span>
      </div>
      <div v-if="authStore.user" class="welcome">
        欢迎您，{{ isAdmin ? '管理员' : authStore.user.username }}！
      </div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <!-- 用户端菜单 -->
        <template v-if="isCustomer">
          <el-menu-item index="/chat">
            <el-icon><ChatDotRound /></el-icon>
            <span>智能点餐</span>
          </el-menu-item>
          <el-menu-item index="/menu">
            <el-icon><Dish /></el-icon>
            <span>菜单浏览</span>
          </el-menu-item>
          <el-menu-item index="/cart">
            <el-icon><ShoppingCart /></el-icon>
            <span>购物车</span>
            <el-badge v-if="cartStore.totalCount > 0" :value="cartStore.totalCount" style="margin-left: 8px;" />
          </el-menu-item>
          <el-menu-item index="/orders">
            <el-icon><List /></el-icon>
            <span>我的订单</span>
          </el-menu-item>
          <el-menu-item index="/order-status">
            <el-icon><Timer /></el-icon>
            <span>订单状态</span>
          </el-menu-item>
          <el-menu-item index="/settings">
            <el-icon><User /></el-icon>
            <span>用户设置</span>
          </el-menu-item>
        </template>

        <!-- 商家端菜单 -->
        <template v-if="isAdmin">
          <el-menu-item index="/admin/dashboard">
            <el-icon><Histogram /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="/admin/menu">
            <el-icon><Dish /></el-icon>
            <span>商品管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/pending-orders">
            <el-icon><Bell /></el-icon>
            <span>待处理订单</span>
          </el-menu-item>
          <el-menu-item index="/admin/orders">
            <el-icon><List /></el-icon>
            <span>订单管理</span>
          </el-menu-item>
        </template>
      </el-menu>

      <!-- 退出登录（自定义元素：需先弹确认框，不能用 el-menu-item 的自动跳转） -->
      <div class="logout-item" @click="handleLogout">
        <el-icon><SwitchButton /></el-icon>
        <span>退出登录</span>
      </div>
    </el-aside>

    <el-container>
      <!-- 聊天页标题移入左栏，不显示全局顶栏 -->
      <el-header v-if="route.path !== '/chat'" class="header">
        <div class="header-title">{{ pageTitle }}</div>
      </el-header>
      <!-- 聊天页去除内边距，让右侧聊天区顶到页面边缘 -->
      <el-main class="main-content" :class="{ 'main-content--flush': route.path === '/chat' }">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 登录页不需要侧边栏 -->
  <router-view v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/features/auth/stores/auth.store'
import { useCartStore } from '@/features/cart/stores/cart.store'
import { useChatStore } from '@/features/chat/stores/chat.store'
import { clearChatHistory } from '@/features/chat/api/chat.api'
import { User, SwitchButton } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const cartStore = useCartStore()
const chatStore = useChatStore()

const isLoginPage = computed(() => route.path === '/login')
const isAdmin = computed(() => authStore.isAdmin)
const isCustomer = computed(() => authStore.isCustomer)

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    '/chat': '智能点餐助手',
    '/menu': '本店菜单',
    '/cart': '购物车',
    '/orders': '我的订单',
    '/order-status': '订单状态',
    '/settings': '用户设置',
    '/admin/dashboard': '商家概览',
    '/admin/menu': '商品管理',
    '/admin/pending-orders': '待处理订单',
    '/admin/orders': '订单管理',
  }
  return titles[route.path] || '美味餐厅'
})

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return // 用户点击取消，不退出
  }
  // 退出登录时清除该用户的 AI 聊天历史（顺序敏感，均需在 logout 清空 token/auth 之前）：
  // 1) 服务端 MongoDB 聊天记录（接口需携带 token）；失败不阻塞退出，仅记录日志
  // 2) 本地聊天记录（此时 localStorage 中仍是该用户的存储 key）
  try {
    await clearChatHistory()
  } catch (e) {
    console.error('清除服务端聊天历史失败', e)
  }
  chatStore.clearMessages()
  // 清空购物车：内存 + 该用户的 localStorage（save 依赖 auth 记录定位用户 key，需在 logout 前调用）
  cartStore.clearCart()
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  height: 100%;
}

.sidebar {
  background-color: #304156;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-bottom: 1px solid #1f2d3d;
}

.title {
  color: #fff;
  font-size: 18px;
  font-weight: bold;
}

.welcome {
  color: #bfcbd9;
  font-size: 13px;
  text-align: center;
  padding: 10px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 10;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.main-content {
  background-color: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}

.main-content--flush {
  padding: 0;
  overflow: hidden;
}

/* 退出登录：精确复刻 el-menu-item 的尺寸参数保证对齐 */
.logout-item {
  display: flex;
  align-items: center;
  height: 56px;
  padding: 0 20px;
  box-sizing: border-box;
  color: #bfcbd9;
  font-size: 14px;
  cursor: pointer;
}

.logout-item .el-icon {
  margin-right: 5px;
  width: 24px;
  text-align: center;
  font-size: 18px;
}

.logout-item:hover {
  background-color: #263445;
  color: #fff;
}
</style>
