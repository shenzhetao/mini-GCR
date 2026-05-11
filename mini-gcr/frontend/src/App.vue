<script setup>
import { computed, onMounted, ref } from 'vue'
import { Activity, Boxes, Play, RefreshCw, ShoppingCart, Sparkles } from 'lucide-vue-next'

const apiBase = ref('/api')
const health = ref(null)
const items = ref([])
const selectedItems = ref([])
const manualInput = ref('')
const topK = ref(5)
const useConstraint = ref(true)
const useModel = ref(false)
const recommendations = ref([])
const scene = ref('露营')
const sceneResult = ref(null)
const loading = ref(false)
const error = ref('')

const itemSeqText = computed(() => selectedItems.value.join(', '))

async function request(path, options = {}) {
  error.value = ''
  const response = await fetch(`${apiBase.value}${path}`, options)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

async function loadHealth() {
  try {
    health.value = await request('/health')
  } catch (err) {
    error.value = `健康检查失败：${err.message}`
  }
}

async function loadItems() {
  try {
    const data = await request('/items?limit=36')
    items.value = data.items || []
    if (!selectedItems.value.length && items.value.length >= 2) {
      selectedItems.value = [items.value[0].item_id, items.value[1].item_id]
    }
  } catch (err) {
    error.value = `商品样例加载失败：${err.message}`
  }
}

function toggleItem(itemId) {
  const id = Number(itemId)
  if (selectedItems.value.includes(id)) {
    selectedItems.value = selectedItems.value.filter(item => item !== id)
  } else {
    selectedItems.value = [...selectedItems.value, id].slice(-8)
  }
  manualInput.value = selectedItems.value.join(',')
}

function applyManualInput() {
  selectedItems.value = manualInput.value
    .split(',')
    .map(item => Number(item.trim()))
    .filter(item => Number.isInteger(item) && item > 0)
}

async function recommend() {
  applyManualInput()
  if (!selectedItems.value.length) {
    error.value = '请至少选择或输入一个商品 ID'
    return
  }
  loading.value = true
  try {
    const data = await request('/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_ids: selectedItems.value,
        top_k: Number(topK.value),
        use_constraint: useConstraint.value,
        use_model: useModel.value
      })
    })
    recommendations.value = data.recommendations || []
    health.value = { ok: true, status: data.status }
  } catch (err) {
    error.value = `推荐请求失败：${err.message}`
  } finally {
    loading.value = false
  }
}

async function loadScene() {
  loading.value = true
  try {
    sceneResult.value = await request('/scene', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene: scene.value })
    })
  } catch (err) {
    error.value = `场景接口失败：${err.message}`
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadHealth()
  await loadItems()
  manualInput.value = selectedItems.value.join(',')
})
</script>

<template>
  <main class="page">
    <section class="hero">
      <div>
        <p class="eyebrow">mini-GCR Demo</p>
        <h1>生成式互补品推荐系统</h1>
        <p class="subtitle">选择购物车商品，测试 FastAPI 推荐接口、互补约束解码与理由生成效果。</p>
      </div>
      <div class="hero-card">
        <Activity :size="28" />
        <span>API 状态</span>
        <strong>{{ health?.ok ? '在线' : '未连接' }}</strong>
      </div>
    </section>

    <section v-if="error" class="alert">{{ error }}</section>

    <section class="grid">
      <div class="panel wide">
        <div class="panel-title">
          <Boxes :size="20" />
          <h2>商品样例</h2>
          <button class="ghost" @click="loadItems"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="item-list">
          <button
            v-for="item in items"
            :key="item.item_id"
            class="item-chip"
            :class="{ active: selectedItems.includes(item.item_id) }"
            @click="toggleItem(item.item_id)"
          >
            <span>#{{ item.item_id }}</span>
            <strong>{{ item.title }}</strong>
            <small>{{ item.category }}</small>
          </button>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <ShoppingCart :size="20" />
          <h2>推荐测试</h2>
        </div>
        <label>购物车商品 ID 序列</label>
        <input v-model="manualInput" placeholder="例如：101,205" />
        <p class="hint">当前序列：{{ itemSeqText || '空' }}</p>
        <div class="form-row">
          <label>Top K</label>
          <input v-model="topK" type="number" min="1" max="10" />
        </div>
        <label class="checkbox">
          <input v-model="useConstraint" type="checkbox" />
          开启互补约束
        </label>
        <label class="checkbox">
          <input v-model="useModel" type="checkbox" />
          优先使用已训练 minGPT 权重
        </label>
        <button class="primary" :disabled="loading" @click="recommend">
          <Play :size="18" />{{ loading ? '请求中...' : '调用 /recommend' }}
        </button>
      </div>

      <div class="panel">
        <div class="panel-title">
          <Sparkles :size="20" />
          <h2>场景接口</h2>
        </div>
        <label>场景标签</label>
        <input v-model="scene" placeholder="露营" />
        <button class="secondary" :disabled="loading" @click="loadScene">调用 /scene</button>
        <pre v-if="sceneResult">{{ sceneResult }}</pre>
      </div>
    </section>

    <section class="panel results">
      <div class="panel-title">
        <Sparkles :size="20" />
        <h2>推荐结果</h2>
      </div>
      <div v-if="recommendations.length" class="result-list">
        <article v-for="rec in recommendations" :key="rec.item_id" class="result-card">
          <div>
            <span class="badge">#{{ rec.item_id }}</span>
            <h3>{{ rec.title }}</h3>
            <p>{{ rec.reason }}</p>
          </div>
          <strong>{{ Math.round(rec.confidence * 100) }}%</strong>
        </article>
      </div>
      <p v-else class="empty">暂无推荐结果，请先调用推荐接口。</p>
    </section>
  </main>
</template>
