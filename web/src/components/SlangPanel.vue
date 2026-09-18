<script setup>
import { ref, watch } from 'vue'
import { state } from '../store'

const TABS = [
  { v: 'slang', t: '黑话词典', api: '/api/slang',
    desc: '语义搜索时,查询里的黑话会自动展开成右侧描述再匹配。保存后立即生效,无需重启。' },
  { v: 'tagdict', t: '标签对照', api: '/api/tagdict',
    desc: 'Scryfall Tagger 社区标签的中英对照,界面优先显示中文;未收录的标签原样显示英文。保存后立即生效。' },
]

const tab = ref('slang')
const items = ref([])
const loaded = ref({})
const loading = ref(false)
const saving = ref(false)
const savedMsg = ref('')
const errorMsg = ref('')

async function load(force = false) {
  if (loaded.value[tab.value] && !force) return
  loading.value = true
  errorMsg.value = ''
  try {
    const api = TABS.find(t => t.v === tab.value).api
    const r = await fetch(api)
    const d = await r.json()
    items.value = d.items
    loaded.value = { ...loaded.value, [tab.value]: true }
  } catch {
    errorMsg.value = '加载失败,请确认后端已启动'
  } finally {
    loading.value = false
  }
}

watch(() => state.slangOpen, (v) => {
  if (v) load()
})

function switchTab(v) {
  tab.value = v
  savedMsg.value = ''
  load()
}

function addItem() {
  items.value.push({ key: '', value: '' })
  savedMsg.value = ''
}

function removeItem(i) {
  items.value.splice(i, 1)
  savedMsg.value = ''
}

async function save() {
  saving.value = true
  savedMsg.value = ''
  errorMsg.value = ''
  try {
    const api = TABS.find(t => t.v === tab.value).api
    const r = await fetch(api, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: items.value }),
    })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    savedMsg.value = `已保存 ${d.count} 条,立即生效`
    loaded.value = { ...loaded.value, [tab.value]: false }
    load(true)
  } catch (e) {
    errorMsg.value = '保存失败:' + e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="state.slangOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/60" @click="state.slangOpen = false"></div>
    <div class="relative flex max-h-[85vh] w-[40rem] max-w-full flex-col rounded-sm border border-line bg-panel shadow-2xl">
      <div class="flex items-start justify-between border-b border-line p-4">
        <div>
          <div class="flex gap-1">
            <button
              v-for="t in TABS"
              :key="t.v"
              class="rounded-sm px-3 py-1 text-xs tracking-widest transition-colors"
              :class="tab === t.v ? 'bg-gold font-bold text-ink' : 'bg-panel2 text-mute hover:text-parch'"
              @click="switchTab(t.v)"
            >{{ t.t }}</button>
          </div>
          <p class="mt-1.5 text-xs text-faint">{{ TABS.find(t => t.v === tab).desc }}</p>
        </div>
        <button class="px-2 text-lg text-mute hover:text-gold" @click="state.slangOpen = false">✕</button>
      </div>

      <div class="flex-1 overflow-y-auto p-4">
        <p v-if="loading" class="text-xs text-faint">加载中…</p>
        <div v-else class="space-y-2">
          <div
            v-for="(it, i) in items"
            :key="i"
            class="flex items-center gap-2"
          >
            <input
              v-model="it.key"
              class="w-44 shrink-0 rounded-sm border border-line bg-panel2 px-2 py-1.5 text-xs text-gold outline-none focus:border-golddim"
              placeholder="黑话 / 英文标签"
              @input="savedMsg = ''"
            />
            <span class="shrink-0 text-faint">=</span>
            <input
              v-model="it.value"
              class="min-w-0 flex-1 rounded-sm border border-line bg-panel2 px-2 py-1.5 text-xs text-parch outline-none focus:border-golddim"
              placeholder="展开描述 / 中文翻译"
              @input="savedMsg = ''"
            />
            <button
              class="shrink-0 px-1.5 text-mute transition-colors hover:text-gold"
              title="删除"
              @click="removeItem(i)"
            >✕</button>
          </div>
          <button
            class="mt-1 rounded-sm border border-dashed border-line px-3 py-1.5 text-xs text-mute transition-colors hover:border-golddim hover:text-gold"
            @click="addItem"
          >+ 添加条目</button>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-line p-4">
        <p class="text-xs">
          <span v-if="savedMsg" class="text-gold">{{ savedMsg }}</span>
          <span v-else-if="errorMsg" class="text-[#d95f4e]">{{ errorMsg }}</span>
          <span v-else class="text-faint">共 {{ items.length }} 条</span>
        </p>
        <div class="flex gap-2">
          <button
            class="rounded-sm border border-line px-4 py-1.5 text-xs text-mute transition-colors hover:text-parch"
            @click="state.slangOpen = false"
          >关闭</button>
          <button
            class="rounded-sm bg-gold px-4 py-1.5 text-xs font-bold text-ink transition-opacity hover:opacity-85 disabled:opacity-50"
            :disabled="saving"
            @click="save"
          >{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
