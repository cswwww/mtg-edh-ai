<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { state, search } from '../store'

const modes = [
  { v: 'vector', t: '语义' },
  { v: 'fts', t: '卡名' },
]
const sorts = [
  { v: 'rel', t: '按相关度' },
  { v: 'edhrec', t: '按 EDHREC 热度' },
  { v: 'cmc_asc', t: '法术力值 ↑' },
  { v: 'cmc_desc', t: '法术力值 ↓' },
  { v: 'name', t: '按名称' },
]

// 命中标签 chip 行:debounce 请求 /api/tags/semantic,把结果写到 state.semanticTags
let semanticTimer = null
let semanticSeq = 0
function cancelSemantic() {
  if (semanticTimer) { clearTimeout(semanticTimer); semanticTimer = null }
}

// 单向同步:state.q → state.semanticQuery(用户输入时驱动 chip 行刷新)
// 这样 chip 行有自己的"语义快照",不会因为点 chip 临时清 q 而消失
watch(() => state.q, (v) => {
  state.semanticQuery = v || ''
})

// 切走"语义"模式时清掉快照(防止在卡名模式下还显示旧 chip)
watch(() => state.mode, () => {
  state.semanticQuery = ''
  state.semanticTags = []
  state.semanticExpanded = ''
})

// chip 行真正依赖的是 semanticQuery(用户清空 q 时行也会跟着消失)
watch(() => state.semanticQuery, (q) => {
  cancelSemantic()
  const trimmed = (q || '').trim()
  if (!trimmed || state.mode !== 'vector') {
    state.semanticTags = []
    state.semanticExpanded = ''
    state.semanticLoading = false
    return
  }
  state.semanticLoading = true
  const my = ++semanticSeq
  semanticTimer = setTimeout(async () => {
    try {
      const r = await fetch('/api/tags/semantic?q=' + encodeURIComponent(trimmed) + '&limit=8')
      if (my !== semanticSeq) return
      if (!r.ok) {
        state.semanticTags = []
        return
      }
      const d = await r.json()
      state.semanticTags = d.items || []
      state.semanticExpanded = d.expanded || trimmed
    } catch {
      if (my === semanticSeq) state.semanticTags = []
    } finally {
      if (my === semanticSeq) state.semanticLoading = false
    }
  }, 220)
})

onUnmounted(cancelSemantic)

const tagZh = computed(() => state.meta?.tagdict || {})
function label(t) { return t.zh || tagZh.value[t.tag] || t.tag }

function toggleTag(tag) {
  const i = state.tags.indexOf(tag)
  if (i >= 0) {
    state.tags.splice(i, 1)
  } else {
    state.tags.push(tag)
    // 语义文本只用来"发现标签",已经选上后就不该再去打 /api/search 的 q:
    // 设 omitQNext 让本次 search 不带 q,搜索框保留内容方便继续编辑/再挑 chip
    state.omitQNext = true
  }
  search()
}
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex overflow-hidden rounded-sm border border-line">
        <button
          v-for="m in modes"
          :key="m.v"
          class="px-3 py-2 text-xs tracking-widest transition-colors"
          :class="state.mode === m.v ? 'bg-gold text-ink font-bold' : 'bg-panel2 text-mute hover:text-parch'"
          @click="state.mode = m.v; search()"
        >{{ m.t }}</button>
      </div>
      <input
        v-model="state.q"
        class="min-w-56 flex-1 rounded-sm border border-line bg-panel2 px-3 py-2 text-sm text-parch placeholder-faint outline-none focus:border-golddim"
        placeholder="中文 / 拼音首字母(如 ygj)/ 卡名,或描述效果:每当有生物死去时抓牌"
        @keyup.enter="search()"
      />
      <button
        class="rounded-sm bg-gold px-4 py-2 text-xs font-bold tracking-widest text-ink hover:opacity-85"
        @click="search()"
      >搜索</button>
      <select
        v-model="state.sort"
        class="rounded-sm border border-line bg-panel2 px-2 py-2 text-xs text-mute outline-none"
        @change="search()"
      >
        <option v-for="s in sorts" :key="s.v" :value="s.v">{{ s.t }}</option>
      </select>
      <button
        class="rounded-sm border border-line bg-panel2 px-3 py-2 text-xs tracking-widest text-mute transition-colors hover:border-golddim hover:text-gold"
        title="查看/编辑语义搜索黑话词典"
        @click="state.slangOpen = true"
      >词典</button>
    </div>

    <!-- 语义命中标签:实时挂在搜索栏下,点 chip 加入筛选 -->
    <div
      v-if="state.mode === 'vector' && state.semanticQuery.trim()"
      class="flex min-h-[1.75rem] flex-wrap items-center gap-1.5 text-[11px]"
    >
      <span class="shrink-0 tracking-[0.2em] text-faint">命中标签</span>
      <template v-if="state.semanticLoading && !state.semanticTags.length">
        <span class="text-faint">搜索中…</span>
      </template>
      <template v-else-if="!state.semanticTags.length">
        <span class="text-faint">无相关标签,试试更具体的描述</span>
      </template>
      <template v-else>
        <button
          v-for="t in state.semanticTags"
          :key="t.tag"
          class="rounded-sm border px-2 py-0.5 transition-colors"
          :class="state.tags.includes(t.tag)
            ? 'border-golddim bg-golddim/40 font-bold text-gold'
            : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
          :title="`${t.tag} · ${t.n} 张卡 · score=${t.score.toFixed(3)}`"
          @click="toggleTag(t.tag)"
        >{{ label(t) }}<span class="ml-1 font-num text-[9px] opacity-60">{{ t.n }}</span></button>
        <span
          v-if="state.semanticExpanded && state.semanticExpanded !== state.semanticQuery.trim()"
          class="ml-1 text-[10px] text-faint"
          :title="`语义展开:${state.semanticExpanded}`"
        >·已展开黑话</span>
      </template>
    </div>
  </div>
</template>