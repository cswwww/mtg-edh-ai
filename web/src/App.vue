<script setup>
import { onMounted, computed } from 'vue'
import { state, search, loadMeta } from './store'
import SearchBar from './components/SearchBar.vue'
import FilterPanel from './components/FilterPanel.vue'
import CardGrid from './components/CardGrid.vue'
import CardDetail from './components/CardDetail.vue'
import SlangPanel from './components/SlangPanel.vue'
import TagPicker from './components/TagPicker.vue'
import TypePicker from './components/TypePicker.vue'

onMounted(() => {
  loadMeta()
  search()
})

const topTags = computed(() => state.meta?.top_tags || [])
const tagZh = computed(() => {
  const map = {}
  for (const t of topTags.value) map[t.tag] = t.zh
  return map
})
const selectedTags = computed(() =>
  state.tags.map((t) => tagZh.value[t] || state.meta?.tagdict?.[t] || t)
)

function toggleTag(t) {
  const i = state.tags.indexOf(t)
  if (i >= 0) state.tags.splice(i, 1)
  else state.tags.push(t)
  search()
}

function clearTags() {
  state.tags = []
  search()
}

function toggleMode() {
  state.tagMode = state.tagMode === 'and' ? 'or' : 'and'
  if (state.tags.length) search()
}
</script>

<template>
  <div class="flex h-screen flex-col">
    <header class="flex items-center gap-4 border-b border-line bg-panel px-4 py-3">
      <div class="shrink-0">
        <h1 class="font-display text-lg font-bold leading-none tracking-wide text-parch">
          早晚能找到卡
        </h1>
        <p class="mt-1 text-[10px] text-faint">中午就午休</p>
      </div>
      <div class="min-w-0 flex-1"><SearchBar /></div>
    </header>

    <!-- 标签筛选:点击打开标签选择弹窗 -->
    <div class="flex items-center gap-1.5 border-b border-line bg-panel px-4 py-1.5">
      <button
        class="shrink-0 rounded-sm border px-2.5 py-1 text-[11px] tracking-widest transition-colors"
        :class="state.tags.length
          ? 'border-golddim bg-golddim/40 font-bold text-gold'
          : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
        @click="state.tagPickerOpen = true"
      >标签筛选{{ state.tags.length ? ` · ${state.tags.length}` : '' }}</button>
      <button
        class="shrink-0 rounded-sm border px-1.5 py-1 font-num text-[11px] font-bold transition-colors"
        :class="state.tagMode === 'and'
          ? 'border-golddim bg-golddim/40 text-gold'
          : 'border-line bg-panel2 text-mute hover:text-parch'"
        :title="state.tagMode === 'and' ? '当前为交集(同时命中),点击切换为并集' : '当前为并集(命中任一),点击切换为交集'"
        @click="toggleMode()"
      >{{ state.tagMode === 'and' ? '∩' : '∪' }}</button>
      <div v-if="selectedTags.length" class="flex min-w-0 items-center gap-1.5 overflow-x-auto">
        <button
          v-for="(label, i) in selectedTags"
          :key="state.tags[i]"
          class="shrink-0 rounded-sm border border-golddim bg-golddim/40 px-2 py-0.5 text-[10px] font-bold text-gold"
          :title="state.tags[i]"
          @click="toggleTag(state.tags[i])"
        >{{ label }} ✕</button>
        <button
          class="shrink-0 px-2 py-0.5 text-[10px] text-faint transition-colors hover:text-gold"
          @click="clearTags()"
        >清空</button>
      </div>
      <span v-else class="text-[10px] text-faint">多选支持交集 / 并集,点击打开选择器</span>
    </div>

    <div class="flex min-h-0 flex-1">
      <FilterPanel />
      <CardGrid />
    </div>

    <CardDetail />
    <SlangPanel />
    <TagPicker />
    <TypePicker />
  </div>
</template>
