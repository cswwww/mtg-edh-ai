<script setup>
import { ref, computed, watch } from 'vue'
import { state, search } from '../store'

const open = computed({
  get: () => state.tagPickerOpen,
  set: (v) => { state.tagPickerOpen = v },
})

const query = ref('')
const remoteTags = ref([])   // 全库搜索结果(/api/tags)
const remoteLoading = ref(false)
let timer = null

const allTags = computed(() => state.meta?.top_tags || [])
const searching = computed(() => query.value.trim().length > 0)

// 输入防抖 250ms 后请求全库标签搜索
watch(query, (v) => {
  clearTimeout(timer)
  if (!v.trim()) {
    remoteTags.value = []
    return
  }
  timer = setTimeout(async () => {
    remoteLoading.value = true
    try {
      const r = await fetch('/api/tags?q=' + encodeURIComponent(v.trim()))
      const d = await r.json()
      if (query.value.trim() === v.trim()) remoteTags.value = d.items
    } catch {
      /* 后端未启动时静默,退回 top100 前端匹配 */
    } finally {
      remoteLoading.value = false
    }
  }, 250)
})

// 有查询词时用全库搜索结果,否则展示 top100
const filtered = computed(() => searching.value ? remoteTags.value : allTags.value)

const selected = computed(() => {
  const map = Object.fromEntries(allTags.value.map((t) => [t.tag, t]))
  return state.tags.map((t) => map[t] || { tag: t, n: null, zh: state.meta?.tagdict?.[t] })
})

function toggle(tag) {
  const i = state.tags.indexOf(tag)
  if (i >= 0) state.tags.splice(i, 1)
  else state.tags.push(tag)
  search()
}

function clearAll() {
  state.tags = []
  search()
}

function setMode(m) {
  if (state.tagMode === m) return
  state.tagMode = m
  if (state.tags.length) search()
}

function label(t) {
  return t.zh || t.tag
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/60" @click="open = false"></div>
    <div class="relative flex max-h-[85vh] w-[42rem] max-w-full flex-col rounded-sm border border-line bg-panel shadow-2xl">
      <div class="flex items-start justify-between border-b border-line p-4">
        <div>
          <div class="flex items-center gap-2">
            <h2 class="font-display text-sm font-bold tracking-widest text-parch">标签筛选</h2>
            <div class="flex overflow-hidden rounded-sm border border-line text-[10px]">
              <button
                class="px-2.5 py-0.5 transition-colors"
                :class="state.tagMode === 'and' ? 'bg-gold font-bold text-ink' : 'bg-panel2 text-mute hover:text-parch'"
                @click="setMode('and')"
              >交集</button>
              <button
                class="px-2.5 py-0.5 transition-colors"
                :class="state.tagMode === 'or' ? 'bg-gold font-bold text-ink' : 'bg-panel2 text-mute hover:text-parch'"
                @click="setMode('or')"
              >并集</button>
            </div>
          </div>
          <p class="mt-1.5 text-xs text-faint">
            {{ state.tagMode === 'and' ? '交集:只显示同时带有所有选中标签的卡。' : '并集:显示带有任一选中标签的卡。' }}点击标签即选即生效。
          </p>
        </div>
        <button class="px-2 text-lg text-mute hover:text-gold" @click="open = false">✕</button>
      </div>

      <!-- 搜索框 -->
      <div class="border-b border-line p-3">
        <input
          v-model="query"
          class="w-full rounded-sm border border-line bg-panel2 px-3 py-2 text-sm text-parch outline-none focus:border-golddim"
          placeholder="搜索全部 2800+ 个标签,中英文均可,如:draw、扫场、tutor…"
        />
      </div>

      <!-- 已选 -->
      <div v-if="selected.length" class="flex flex-wrap items-center gap-1.5 border-b border-line bg-panel2/50 px-3 py-2">
        <span class="text-[10px] tracking-[0.2em] text-faint">已选</span>
        <button
          v-for="t in selected"
          :key="t.tag"
          class="rounded-sm border border-golddim bg-golddim/40 px-2 py-0.5 text-[11px] font-bold text-gold"
          :title="t.tag"
          @click="toggle(t.tag)"
        >{{ label(t) }} ✕</button>
        <button class="ml-auto px-2 text-[11px] text-faint hover:text-gold" @click="clearAll">清空 ×{{ selected.length }}</button>
      </div>

      <!-- 标签列表:空查询展示 top100,有查询词展示全库搜索结果 -->
      <div class="flex-1 overflow-y-auto p-3">
        <p v-if="!searching && !allTags.length" class="text-xs text-faint">加载中…</p>
        <p v-else-if="searching && remoteLoading" class="text-xs text-faint">全库搜索中…</p>
        <p v-else-if="!filtered.length" class="text-xs text-faint">{{ searching ? `没有匹配「${query}」的标签` : '暂无标签数据' }}</p>
        <div v-else class="flex flex-wrap gap-1.5">
          <button
            v-for="t in filtered"
            :key="t.tag"
            class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
            :class="state.tags.includes(t.tag)
              ? 'border-golddim bg-golddim/40 font-bold text-gold'
              : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
            :title="t.tag"
            @click="toggle(t.tag)"
          >{{ label(t) }}<span class="ml-1 font-num text-[9px] opacity-60">{{ t.n }}</span></button>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-line px-4 py-2.5">
        <p class="text-xs text-faint">
          <template v-if="searching">全库匹配 {{ filtered.length }} 个标签</template>
          <template v-else>常用 top {{ allTags.length }} · 输入可搜全库 2800+ 个</template>
        </p>
        <button
          class="rounded-sm bg-gold px-4 py-1.5 text-xs font-bold text-ink transition-opacity hover:opacity-85"
          @click="open = false"
        >完成</button>
      </div>
    </div>
  </div>
</template>
