<template>
  <div class="min-h-screen bg-xhs-bg">
    <Head>
      <meta name="referrer" content="no-referrer" />
    </Head>
    
    <!-- 顶部导航 -->
    <header class="sticky top-0 bg-white shadow-sm z-50">
      <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <button 
            @click="$router.push('/')"
            class="flex items-center gap-2 text-gray-600 hover:text-xhs-red transition"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/>
            </svg>
            <span>返回首页</span>
          </button>
        </div>
        
        <!-- Tab 切换 -->
        <div class="flex gap-2">
          <button
            @click="activeTab = 'keywords'"
            :class="activeTab === 'keywords' ? 'bg-xhs-red text-white' : 'bg-gray-100 text-gray-600'"
            class="px-4 py-2 rounded-lg transition"
          >
            搜索词
          </button>
          <button
            @click="activeTab = 'logs'; refreshLogs()"
            :class="activeTab === 'logs' ? 'bg-xhs-red text-white' : 'bg-gray-100 text-gray-600'"
            class="px-4 py-2 rounded-lg transition"
          >
            执行日志
          </button>
        </div>
        
        <button 
          v-show="activeTab === 'keywords'"
          @click="showAddModal = true"
          class="px-4 py-2 bg-xhs-red text-white rounded-lg hover:bg-red-600 transition flex items-center gap-2"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
          </svg>
          添加关键词
        </button>
      </div>
    </header>

    <!-- 内容区域 -->
    <main class="max-w-7xl mx-auto px-4 py-6">
      <!-- 搜索词 Tab -->
      <div v-show="activeTab === 'keywords'">
        <!-- 加载状态 -->
        <div v-if="pending" class="flex justify-center py-20">
          <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-xhs-red"></div>
        </div>

        <!-- 错误状态 -->
        <div v-else-if="error" class="text-center py-20 text-gray-500">
          加载失败，请刷新页面重试
        </div>

        <!-- 空状态 -->
        <div v-else-if="keywords.length === 0" class="text-center py-20">
          <div class="text-gray-400 mb-4">
            <svg class="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
            </svg>
          </div>
          <p class="text-gray-500 mb-4">暂无配置的搜索词</p>
          <button 
            @click="showAddModal = true"
            class="px-4 py-2 bg-xhs-red text-white rounded-lg hover:bg-red-600 transition"
          >
            添加第一个关键词
          </button>
        </div>

        <!-- 搜索词列表 -->
        <div v-else class="grid gap-4">
        <div 
          v-for="kw in keywords" 
          :key="kw.id"
          class="bg-white rounded-lg shadow-sm p-4 flex items-center justify-between hover:shadow-md transition"
        >
          <!-- 关键词信息 -->
          <div class="flex items-center gap-4">
            <!-- 状态标识 -->
            <div 
              class="w-3 h-3 rounded-full"
              :class="kw.status === 'active' ? 'bg-green-500' : 'bg-gray-300'"
            ></div>
            
            <!-- 关键词文本 -->
            <div>
              <h3 class="text-lg font-medium text-gray-800">{{ kw.keyword }}</h3>
              <p class="text-sm text-gray-500 mt-1">
                <span v-if="kw.auto_search">
                  自动搜索 · 每 {{ formatInterval(kw.search_interval) }}
                  <span v-if="kw.last_search_time" class="text-gray-400">
                    · 上次: {{ formatTime(kw.last_search_time) }}
                  </span>
                </span>
                <span v-else class="text-gray-400">手动搜索</span>
              </p>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex items-center gap-2">
            <!-- 自动搜索开关 -->
            <button 
              @click="toggleAutoSearch(kw)"
              :class="kw.auto_search 
                ? 'bg-green-100 text-green-700 hover:bg-green-200' 
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
              class="px-3 py-1.5 rounded-lg text-sm transition flex items-center gap-1"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
              {{ kw.auto_search ? '已开启' : '开启自动' }}
            </button>

            <!-- 手动搜索 -->
            <button 
              @click="triggerSearch(kw)"
              :disabled="searchingKeywords.includes(kw.keyword)"
              class="px-3 py-1.5 bg-xhs-red text-white rounded-lg text-sm hover:bg-red-600 transition disabled:opacity-50 flex items-center gap-1"
            >
              <svg 
                :class="searchingKeywords.includes(kw.keyword) ? 'animate-spin' : ''"
                class="w-4 h-4" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
              </svg>
              {{ searchingKeywords.includes(kw.keyword) ? '搜索中...' : '立即搜索' }}
            </button>

            <!-- 删除 -->
            <button 
              @click="confirmDelete(kw)"
              class="px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-sm hover:bg-red-100 transition flex items-center gap-1"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
              </svg>
              删除
            </button>
          </div>
        </div>
      </div>
      </div>

      <!-- 日志 Tab -->
      <div v-show="activeTab === 'logs'">
        <!-- 加载状态 -->
        <div v-if="logsPending" class="flex justify-center py-20">
          <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-xhs-red"></div>
        </div>

        <!-- 错误状态 -->
        <div v-else-if="logsError" class="text-center py-20 text-gray-500">
          加载日志失败，请刷新重试
        </div>

        <!-- 空状态 -->
        <div v-else-if="logs.length === 0" class="text-center py-20">
          <div class="text-gray-400 mb-4">
            <svg class="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
            </svg>
          </div>
          <p class="text-gray-500 mb-4">暂无搜索日志</p>
          <p class="text-sm text-gray-400">执行搜索后会自动记录日志</p>
        </div>

        <!-- 日志列表 -->
        <div v-else class="space-y-4">
          <!-- 日志卡片 -->
          <div 
            v-for="log in logs" 
            :key="log.id"
            class="bg-white rounded-lg shadow-sm p-4 hover:shadow-md transition"
          >
            <!-- 头部：关键词和时间 -->
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <span class="px-2 py-1 bg-xhs-red/10 text-xhs-red rounded text-sm font-medium">
                  {{ log.keyword }}
                </span>
                <span 
                  v-if="log.error_message"
                  class="px-2 py-1 bg-red-100 text-red-600 rounded text-sm"
                >
                  错误
                </span>
              </div>
              <span class="text-sm text-gray-400">
                {{ formatLogTime(log.created_at) }}
              </span>
            </div>

            <!-- 统计数据 -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
              <!-- 帖子统计 -->
              <div class="bg-gray-50 rounded-lg p-3">
                <div class="text-2xl font-bold text-gray-800">{{ log.posts_found }}</div>
                <div class="text-xs text-gray-500">发现帖子</div>
              </div>
              <!-- 入库统计 -->
              <div class="bg-green-50 rounded-lg p-3">
                <div class="text-2xl font-bold text-green-600">{{ log.posts_inserted }}</div>
                <div class="text-xs text-gray-500">成功入库</div>
              </div>
              <!-- 图片上传 -->
              <div class="bg-blue-50 rounded-lg p-3">
                <div class="text-2xl font-bold text-blue-600">{{ log.images_uploaded }}</div>
                <div class="text-xs text-gray-500">图片上传</div>
              </div>
              <!-- 耗时 -->
              <div class="bg-orange-50 rounded-lg p-3">
                <div class="text-2xl font-bold text-orange-600">{{ log.duration_seconds }}s</div>
                <div class="text-xs text-gray-500">执行耗时</div>
              </div>
            </div>

            <!-- 详细信息（可展开） -->
            <div class="mt-3 text-sm text-gray-500 flex gap-4">
              <span v-if="log.posts_skipped > 0">
                跳过重复: {{ log.posts_skipped }}
              </span>
              <span v-if="log.images_found > 0">
                发现图片: {{ log.images_found }}
              </span>
              <span v-if="log.images_failed > 0">
                上传失败: {{ log.images_failed }}
              </span>
            </div>

            <!-- 错误信息 -->
            <div v-if="log.error_message" class="mt-3 p-2 bg-red-50 rounded text-red-600 text-sm">
              {{ log.error_message }}
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 添加关键词模态框 -->
    <div 
      v-if="showAddModal"
      class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center"
      @click.self="showAddModal = false"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-bold text-gray-800 mb-4">添加搜索关键词</h2>
        
        <div class="space-y-4">
          <!-- 关键词输入 -->
          <div>
            <label class="block text-sm text-gray-600 mb-1">关键词</label>
            <input 
              v-model="newKeyword"
              type="text"
              placeholder="输入搜索关键词..."
              class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-xhs-red"
            />
          </div>
          
          <!-- 自动搜索开关 -->
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-sm text-gray-600">启用自动搜索</label>
              <p class="text-xs text-gray-400">开启后将按设定间隔自动搜索</p>
            </div>
            <button 
              @click="newAutoSearch = !newAutoSearch"
              :class="newAutoSearch ? 'bg-xhs-red' : 'bg-gray-300'"
              class="w-12 h-6 rounded-full transition relative"
            >
              <div 
                :class="newAutoSearch ? 'right-1' : 'left-1'"
                class="w-4 h-4 bg-white rounded-full absolute top-1 transition-all"
              ></div>
            </button>
          </div>
          
          <!-- 搜索间隔 -->
          <div v-if="newAutoSearch">
            <label class="block text-sm text-gray-600 mb-1">搜索间隔（小时）</label>
            <select 
              v-model="newInterval"
              class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-xhs-red"
            >
              <option value="0.1">每 6 分钟 (0.1 小时)</option>
              <option value="0.25">每 15 分钟 (0.25 小时)</option>
              <option value="0.5">每 30 分钟 (0.5 小时)</option>
              <option value="1">每 1 小时</option>
              <option value="2">每 2 小时</option>
              <option value="6">每 6 小时</option>
              <option value="12">每 12 小时</option>
              <option value="24">每 24 小时</option>
              <option value="48">每 48 小时</option>
            </select>
          </div>
        </div>
        
        <!-- 操作按钮 -->
        <div class="flex justify-end gap-3 mt-6">
          <button 
            @click="showAddModal = false"
            class="px-4 py-2 text-gray-600 hover:text-gray-800 transition"
          >
            取消
          </button>
          <button 
            @click="addKeyword"
            :disabled="!newKeyword.trim() || adding"
            class="px-4 py-2 bg-xhs-red text-white rounded-lg hover:bg-red-600 transition disabled:opacity-50"
          >
            {{ adding ? '添加中...' : '添加' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认模态框 -->
    <div 
      v-if="deleteTarget"
      class="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center"
      @click.self="deleteTarget = null"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-sm p-6 text-center">
        <div class="text-red-500 mb-4">
          <svg class="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.542 0 2.282-1.284 1.636-2.286l-6.8-10.284c-.774-1.036-2.698-1.036-3.472 0l-6.8 10.284c-.646 1.002.094 2.286 1.636 2.286z"/>
          </svg>
        </div>
        <h2 class="text-lg font-bold text-gray-800 mb-2">确认删除</h2>
        <p class="text-gray-600 mb-4">
          确定要删除关键词 "{{ deleteTarget.keyword }}" 吗？
        </p>
        <div class="flex justify-center gap-3">
          <button 
            @click="deleteTarget = null"
            class="px-4 py-2 text-gray-600 hover:text-gray-800 transition"
          >
            取消
          </button>
          <button 
            @click="deleteKeyword"
            class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition"
          >
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 提示消息 -->
    <div 
      v-if="toast.show"
      class="fixed top-4 left-1/2 -translate-x-1/2 z-[200] px-4 py-2 rounded-lg shadow-lg transition-all"
      :class="toast.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'"
    >
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
interface Keyword {
  id: number
  keyword: string
  status: string
  auto_search: boolean
  search_interval: number
  last_search_time: string | null
  created_at: string
  updated_at: string
}

const router = useRouter()

// Tab 切换
const activeTab = ref<'keywords' | 'logs'>('keywords')

// 获取搜索词列表
const { data, pending, error, refresh } = await useFetch('/api/keywords')
const keywords = computed(() => data.value?.keywords || [])

// 获取搜索日志
const { data: logsData, pending: logsPending, error: logsError, refresh: refreshLogs } = await useFetch('/api/logs', { lazy: true })
const logs = computed(() => logsData.value?.logs || [])

// 添加关键词
const showAddModal = ref(false)
const newKeyword = ref('')
const newAutoSearch = ref(false)
const newInterval = ref(1)
const adding = ref(false)

const addKeyword = async () => {
  if (!newKeyword.value.trim()) return
  
  adding.value = true
  try {
    const res = await $fetch('/api/keywords', {
      method: 'POST',
      body: {
        keyword: newKeyword.value.trim(),
        auto_search: newAutoSearch.value,
        search_interval: newInterval.value
      }
    })
    
    if (res.success) {
      showToast('添加成功', 'success')
      showAddModal.value = false
      newKeyword.value = ''
      newAutoSearch.value = false
      newInterval.value = 1
      refresh()
    } else {
      showToast(res.error || '添加失败', 'error')
    }
  } catch (e: any) {
    showToast(e.message || '添加失败', 'error')
  }
  adding.value = false
}

// 删除关键词
const deleteTarget = ref<Keyword | null>(null)

const confirmDelete = (kw: Keyword) => {
  deleteTarget.value = kw
}

const deleteKeyword = async () => {
  if (!deleteTarget.value) return
  
  try {
    const res = await $fetch('/api/keywords', {
      method: 'DELETE',
      body: { keyword: deleteTarget.value.keyword }
    })
    
    if (res.success) {
      showToast('删除成功', 'success')
      deleteTarget.value = null
      refresh()
    } else {
      showToast(res.error || '删除失败', 'error')
    }
  } catch (e: any) {
    showToast(e.message || '删除失败', 'error')
  }
}

// 切换自动搜索
const toggleAutoSearch = async (kw: Keyword) => {
  try {
    const res = await $fetch('/api/keywords', {
      method: 'PATCH',
      body: {
        keyword: kw.keyword,
        auto_search: !kw.auto_search,
        search_interval: kw.search_interval
      }
    })
    
    if (res.success) {
      showToast(kw.auto_search ? '已关闭自动搜索' : '已开启自动搜索', 'success')
      refresh()
    } else {
      showToast(res.error || '操作失败', 'error')
    }
  } catch (e: any) {
    showToast(e.message || '操作失败', 'error')
  }
}

// 手动触发搜索
const searchingKeywords = ref<string[]>([])

const triggerSearch = async (kw: Keyword) => {
  if (searchingKeywords.value.includes(kw.keyword)) return
  
  searchingKeywords.value.push(kw.keyword)
  
  try {
    const res = await $fetch('/api/search/trigger', {
      method: 'POST',
      body: {
        keyword: kw.keyword,
        limit: 10
      }
    })
    
    if (res.success) {
      showToast('搜索任务已启动', 'success')
      // 延迟刷新以更新上次搜索时间
      setTimeout(() => refresh(), 2000)
    } else {
      showToast(res.error || '触发失败', 'error')
    }
  } catch (e: any) {
    showToast(e.message || '触发失败', 'error')
  }
  
  // 5秒后移除搜索状态
  setTimeout(() => {
    searchingKeywords.value = searchingKeywords.value.filter(k => k !== kw.keyword)
  }, 5000)
}

// 格式化搜索间隔
const formatInterval = (hours: number) => {
  if (hours < 1) {
    const minutes = Math.round(hours * 60)
    return `${minutes} 分钟`
  } else if (hours === 1) {
    return '1 小时'
  } else {
    return `${hours} 小时`
  }
}

// 格式化时间
const formatTime = (time: string | null) => {
  if (!time) return ''
  const d = new Date(time)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${Math.floor(diff / 86400000)} 天前`
}

// 格式化日志时间
const formatLogTime = (time: string) => {
  if (!time) return ''
  const d = new Date(time)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  
  // 详细时间格式
  const dateStr = `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  
  if (diff < 60000) return `刚刚 (${dateStr})`
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前 (${dateStr})`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前 (${dateStr})`
  return `${Math.floor(diff / 86400000)} 天前 (${dateStr})`
}

// Toast 提示
const toast = ref({ show: false, message: '', type: 'success' as 'success' | 'error' })

const showToast = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = { show: true, message, type }
  setTimeout(() => {
    toast.value.show = false
  }, 3000)
}
</script>

<style scoped>
/* 添加一些自定义样式 */
</style>