<!-- 购物车页面：数量调整、删除、合计、确认下单 -->
<template>
  <div>
    <el-card>
      <template #header>
        <div class="card-header">
          <span>购物车</span>
          <el-button type="danger" size="small" @click="handleClearCart" :disabled="cartStore.items.length === 0">
            清空
          </el-button>
        </div>
      </template>

      <el-empty v-if="cartStore.items.length === 0" description="购物车是空的，去菜单看看吧～" />

      <el-table v-else :data="cartStore.items" stripe>
        <el-table-column prop="name" label="菜品" />
        <el-table-column prop="unit_price" label="单价" width="120">
          <template #default="scope">¥{{ scope.row.unit_price.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="数量" width="180">
          <template #default="scope">
            <el-input-number
              :model-value="scope.row.quantity"
              :min="1"
              :max="999"
              size="small"
              @update:model-value="(val: number) => cartStore.updateQuantity(scope.row.menu_item_id, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="小计" width="120">
          <template #default="scope">¥{{ (scope.row.unit_price * scope.row.quantity).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="scope">
            <el-button size="small" type="danger" @click="cartStore.removeItem(scope.row.menu_item_id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="cartStore.items.length > 0" class="cart-summary">
        <div class="total">合计：¥{{ cartStore.totalPrice.toFixed(2) }}</div>
        <el-button type="primary" size="large" @click="confirmOrder" :loading="ordering">
          确认下单
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCartStore } from '@/features/cart/stores/cart.store'
import { createOrder } from '@/features/orders/api/order.api'
import type { CartItem } from '@/shared/types'

const router = useRouter()
const cartStore = useCartStore()
const ordering = ref(false)

function handleClearCart() {
  ElMessageBox.confirm('确定清空购物车吗？', '提示', { type: 'warning' })
    .then(() => {
      cartStore.clearCart()
      ElMessage.success('购物车已清空')
    })
    .catch(() => {})
}

async function confirmOrder() {
  if (cartStore.items.length === 0) {
    ElMessage.warning('购物车是空的')
    return
  }
  ordering.value = true
  try {
    // 直接调用传统订单接口创建订单（不再经过聊天接口）
    const items: CartItem[] = JSON.parse(JSON.stringify(cartStore.items))
    await createOrder(items)
    cartStore.clearCart()
    ElMessage.success('下单成功！')
    router.push('/orders')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '下单失败')
    console.error(err)
  } finally {
    ordering.value = false
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.cart-summary {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 20px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.total {
  font-size: 20px;
  font-weight: bold;
  color: #f56c6c;
}
</style>
