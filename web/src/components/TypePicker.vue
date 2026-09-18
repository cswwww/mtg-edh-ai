<script setup>
import { ref, computed, watch } from 'vue'
import { state, search } from '../store'

const open = computed({
  get: () => state.typeModalOpen,
  set: (v) => { state.typeModalOpen = v },
})

const query = ref('')
const subtypeData = ref(null)

const EVERGREEN = [
  { t: 'Artifact', zh: '神器' }, { t: 'Creature', zh: '生物' },
  { t: 'Enchantment', zh: '结界' }, { t: 'Instant', zh: '瞬间' },
  { t: 'Land', zh: '地' }, { t: 'Planeswalker', zh: '鹏洛客' },
  { t: 'Sorcery', zh: '法术' },
]
const OTHER = [
  { t: 'Battle', zh: '战役' }, { t: 'Kindred', zh: '亲缘' },
  { t: 'Conspiracy', zh: '诡局' }, { t: 'Dungeon', zh: '地城' },
  { t: 'Phenomenon', zh: '异象' }, { t: 'Plane', zh: '时空' },
  { t: 'Scheme', zh: '邪计' }, { t: 'Vanguard', zh: '先锋' },
]
const SUPERTYPES = [
  { t: 'Legendary', zh: '传奇' }, { t: 'Basic', zh: '基本' },
  { t: 'Snow', zh: '雪' }, { t: 'Ongoing', zh: '持续' },
  { t: 'World', zh: '世界' },
]
const MAIN_TOKENS = new Set([...EVERGREEN, ...OTHER].map((x) => x.t))

const ZH = Object.fromEntries([...EVERGREEN, ...OTHER, ...SUPERTYPES].map((x) => [x.t, x.zh]))
const zh2token = Object.fromEntries([...EVERGREEN, ...OTHER, ...SUPERTYPES].map((x) => [x.zh, x.t]))

const searchMsg = ref('')

watch(() => state.typeModalOpen, async (v) => {
  if (v && !subtypeData.value) {
    try {
      const r = await fetch('/api/types')
      subtypeData.value = (await r.json()).subtypes
    } catch { subtypeData.value = [] }
  }
})

// 子序列模糊匹配
function fuzzy(q, s) {
  q = q.toLowerCase(); s = s.toLowerCase()
  let i = 0
  for (const c of s) {
    if (c === q[i]) i++
    if (i === q.length) return true
  }
  return i === q.length
}

function hit(item, q) {
  if (!q) return true
  return fuzzy(q, item.t) || (item.zh && fuzzy(q, item.zh))
}

const q = computed(() => query.value.trim())
const mainFiltered = computed(() => [...EVERGREEN, ...OTHER].filter((x) => hit(x, q.value)))
const supFiltered = computed(() => SUPERTYPES.filter((x) => hit(x, q.value)))
const subFiltered = computed(() =>
  (subtypeData.value || []).filter((x) => hit(x, q.value)).slice(0, q.value ? 200 : 120)
)

const selectedMain = computed(() => state.types.filter((t) => MAIN_TOKENS.has(t)))
const selectedSub = computed(() => state.types.filter((t) => !MAIN_TOKENS.has(t)))

function toggle(t) {
  const i = state.types.indexOf(t)
  if (i >= 0) state.types.splice(i, 1)
  else state.types.push(t)
  search()
}

function clearAll() {
  state.types = []
  search()
}

// 任意类型 token → 中文显示(主类型/超类型查静态表,副类别查数据对齐表)
function zhOf(t) {
  if (ZH[t]) return ZH[t]
  const s = (subtypeData.value || []).find((x) => x.t === t)
  return (s && s.zh) || t
}

// 搜索框直接搜索:空格分词,逐词映射到类型 token(中文/英文均可),
// 命中后替换已选类型并立即搜索,跳过勾选环节
function mapToken(tok) {
  const t = tok.trim()
  if (!t) return null
  if (zh2token[t]) return zh2token[t]
  const tl = t.toLowerCase()
  for (const x of [...EVERGREEN, ...OTHER, ...SUPERTYPES]) {
    if (x.t.toLowerCase() === tl) return x.t
  }
  for (const s of subtypeData.value || []) {
    if (s.zh === t || s.t.toLowerCase() === tl) return s.t
  }
  return null
}

function directSearch() {
  const toks = query.value.split(/[\s,，、]+/).filter(Boolean)
  if (!toks.length) return
  const mapped = []
  const missed = []
  for (const t of toks) {
    const m = mapToken(t)
    if (m) mapped.push(m)
    else missed.push(t)
  }
  if (!mapped.length) {
    searchMsg.value = `「${toks.join(' ')}」未能识别为任何类型,请换个词`
    return
  }
  state.types = [...new Set(mapped)]
  search()
  searchMsg.value = `已按 ${state.types.map((t) => zhOf(t)).join(' + ')} 搜索`
    + (missed.length ? `(未识别:${missed.join('、')})` : '')
}

const chip = (on) => on
  ? 'border-golddim bg-golddim/40 font-bold text-gold'
  : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/60" @click="open = false"></div>
    <div class="relative flex max-h-[85vh] w-[42rem] max-w-full flex-col rounded-sm border border-line bg-panel shadow-2xl">
      <div class="flex items-start justify-between border-b border-line p-4">
        <div>
          <h2 class="font-display text-sm font-bold tracking-widest text-parch">卡牌类型</h2>
          <p class="mt-1.5 text-xs text-faint">多选为交集:如 生物+神器 = 神器生物;传奇+生物 = 传奇生物。点击即选即生效。</p>
        </div>
        <button class="px-2 text-lg text-mute hover:text-gold" @click="open = false">✕</button>
      </div>

      <div class="border-b border-line p-3">
        <div class="flex gap-2">
          <input
            v-model="query"
            class="min-w-0 flex-1 rounded-sm border border-line bg-panel2 px-3 py-2 text-sm text-parch outline-none focus:border-golddim"
            placeholder="输入类型直接搜索,空格分隔,回车生效,如:传奇 人类"
            @keyup.enter="directSearch"
          />
          <button
            v-if="query.trim()"
            class="shrink-0 rounded-sm bg-gold px-3 py-2 text-xs font-bold text-ink transition-opacity hover:opacity-85"
            @click="directSearch"
          >搜索</button>
        </div>
        <p v-if="searchMsg" class="mt-1.5 text-[11px] text-gold">{{ searchMsg }}</p>
      </div>

      <!-- 已选 -->
      <div v-if="state.types.length" class="flex flex-wrap items-center gap-1.5 border-b border-line bg-panel2/50 px-3 py-2">
        <span class="text-[10px] tracking-[0.2em] text-faint">已选</span>
        <button
          v-for="t in state.types"
          :key="t"
          class="rounded-sm border border-golddim bg-golddim/40 px-2 py-0.5 text-[11px] font-bold text-gold"
          @click="toggle(t)"
        >{{ zhOf(t) }} ✕</button>
        <button class="ml-auto px-2 text-[11px] text-faint hover:text-gold" @click="clearAll">清空 ×{{ state.types.length }}</button>
      </div>

      <div class="flex-1 overflow-y-auto p-3">
        <template v-if="mainFiltered.length">
          <p class="mb-1.5 mt-1 text-[10px] tracking-[0.2em] text-faint">主类型</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="m in mainFiltered"
              :key="m.t"
              class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
              :class="chip(state.types.includes(m.t))"
              @click="toggle(m.t)"
            >{{ m.zh }}<span class="ml-1 text-[9px] opacity-50">{{ m.t }}</span></button>
          </div>
        </template>

        <template v-if="supFiltered.length">
          <p class="mb-1.5 mt-3 text-[10px] tracking-[0.2em] text-faint">超类型</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="m in supFiltered"
              :key="m.t"
              class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
              :class="chip(state.types.includes(m.t))"
              @click="toggle(m.t)"
            >{{ m.zh }}<span class="ml-1 text-[9px] opacity-50">{{ m.t }}</span></button>
          </div>
        </template>

        <p class="mb-1.5 mt-3 text-[10px] tracking-[0.2em] text-faint">副类别 <span class="normal-case tracking-normal">(人类、武具、灵气……)</span></p>
        <p v-if="!subtypeData" class="text-xs text-faint">加载中…</p>
        <p v-else-if="!subFiltered.length" class="text-xs text-faint">没有匹配「{{ query }}」的副类别</p>
        <div v-else class="flex flex-wrap gap-1.5">
          <button
            v-for="s in subFiltered"
            :key="s.t"
            class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
            :class="chip(state.types.includes(s.t))"
            @click="toggle(s.t)"
          >{{ s.zh || s.t }}<span class="ml-1 font-num text-[9px] opacity-50">{{ s.n }}</span></button>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-line px-4 py-2.5">
        <p class="text-xs text-faint">{{ state.types.length ? `已选 ${state.types.length} 项,交集筛选` : '未选择类型' }}</p>
        <button
          class="rounded-sm bg-gold px-4 py-1.5 text-xs font-bold text-ink transition-opacity hover:opacity-85"
          @click="open = false"
        >完成</button>
      </div>
    </div>
  </div>
</template>
