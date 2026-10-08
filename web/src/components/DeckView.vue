<script setup>
import { ref, computed, onMounted } from 'vue'
import { state, openDetail, LIST_COLS } from '../store'
import ManaText from './ManaText.vue'

const EXAMPLE = `Commander
1 受诅国王寇沃

Deck
1 Sol Ring
1 阳光戒
1 Rhystic Study
1 神秘熔炉
1 秘法印记
1 克撒的塔
1 太贪婪，也太深
1 森林
7 树林

// 支持 1x 名字 / 名字 (SET) 编号 / 中文或英文卡名 / 分区标题`

const text = ref('')
const cards = ref(null)      // null = 尚未解析
const unmatched = ref([])
const totalQty = ref(0)
const loading = ref(false)
const error = ref('')
const filterTags = ref([])
const tagMode = ref('and')
const showInput = ref(true)
const copiedUnmatched = ref(false)

// 牌表持久化:解析成功时保存原文,进入页面自动恢复并重解析
const DECK_KEY = 'mtg-deck-text'
function saveDeck() {
  try {
    if (text.value.trim()) localStorage.setItem(DECK_KEY, text.value)
  } catch {}
}
{
  const saved = localStorage.getItem(DECK_KEY)
  if (saved && saved.trim()) text.value = saved
}

const zhDict = computed(() => state.meta?.tagdict || {})
function tagLabel(t) {
  return zhDict.value[t] || t
}

// 每张卡展示用标签:社区标签(sf)优先,完全没有时退回 AI 标签
function cardTags(c) {
  return c.sf_tags?.length ? c.sf_tags : (c.ai_tags || [])
}

async function parse() {
  if (!text.value.trim() || loading.value) return
  loading.value = true
  error.value = ''
  copiedUnmatched.value = false
  try {
    const r = await fetch('/api/deck', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.value }),
    })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    cards.value = d.cards
    unmatched.value = d.unmatched
    totalQty.value = d.total_qty
    filterTags.value = []
    tagExpanded.value = false
    showInput.value = false
    saveDeck()
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

const tagCounts = computed(() => {
  const m = {}
  for (const c of cards.value || []) {
    for (const t of cardTags(c)) m[t] = (m[t] || 0) + c.qty
  }
  return Object.entries(m).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
})

// 标签云默认只展示前几个,其余收进「更多」;已选中的标签始终可见
const TAG_TOP_N = 12
const tagExpanded = ref(false)
const shownTagCounts = computed(() => {
  const all = tagCounts.value
  if (tagExpanded.value || all.length <= TAG_TOP_N) return all
  const head = all.slice(0, TAG_TOP_N)
  const headSet = new Set(head.map(([t]) => t))
  return head.concat(all.filter(([t]) => filterTags.value.includes(t) && !headSet.has(t)))
})
const hiddenTagCount = computed(() => tagCounts.value.length - shownTagCounts.value.length)

const untagged = computed(() =>
  (cards.value || []).filter((c) => !cardTags(c).length)
)

// ---------------- 颜色 / 类型 / 总法术力 筛选(本页独立,不影响查卡页) ----------------
const COLOR_ROWS = [
  { c: 'W', label: '白' }, { c: 'U', label: '蓝' }, { c: 'B', label: '黑' },
  { c: 'R', label: '红' }, { c: 'G', label: '绿' },
]
const QUICK_TYPES = [
  { t: 'Creature', zh: '生物' }, { t: 'Sorcery', zh: '法术' },
  { t: 'Instant', zh: '瞬间' }, { t: 'Enchantment', zh: '结界' },
  { t: 'Artifact', zh: '神器' }, { t: 'Land', zh: '地' },
  { t: 'Planeswalker', zh: '鹏洛客' },
]
const CMC_OPTIONS = [...Array.from({ length: 11 }, (_, i) => String(i)), '11+']

const fColors = ref([])
const fColorless = ref(false)
const fCcExclude = ref(false)   // 不含未选:牌面色 ⊆ 所选
const fCcPartial = ref(false)   // 部分匹配:与所选有交集
const fTypes = ref([])
const fCmc = ref([])

function colorMatch(c) {
  const S = new Set(fColors.value)
  const C = new Set(c.colors || [])
  if (!S.size && !fColorless.value) return true
  if (!C.size) return fColorless.value
  if (!S.size) return false
  if (fCcPartial.value) return [...C].some((x) => S.has(x))
  if (fCcExclude.value) return [...C].every((x) => S.has(x))
  return C.size === S.size && [...C].every((x) => S.has(x))   // 默认精确匹配
}
function typeMatch(c) {
  if (!fTypes.value.length) return true
  const tl = c.type_line_en || ''
  return fTypes.value.every((t) => tl.includes(t))
}
function cmcMatch(c) {
  if (!fCmc.value.length) return true
  const v = c.cmc ?? 0
  return fCmc.value.some((s) => (s === '11+' ? v >= 11 : v === Number(s)))
}

const attrFilterActive = computed(() =>
  fColors.value.length || fColorless.value || fTypes.value.length || fCmc.value.length)

function clearAttrFilters() {
  fColors.value = []
  fColorless.value = false
  fCcExclude.value = false
  fCcPartial.value = false
  fTypes.value = []
  fCmc.value = []
}

function toggleIn(arr, v) {
  const i = arr.indexOf(v)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(v)
}

const filtered = computed(() => {
  const list = cards.value || []
  return list.filter((c) => {
    if (!colorMatch(c) || !typeMatch(c) || !cmcMatch(c)) return false
    if (!filterTags.value.length) return true
    const tags = cardTags(c)
    return tagMode.value === 'and'
      ? filterTags.value.every((t) => tags.includes(t))
      : filterTags.value.some((t) => tags.includes(t))
  })
})

const anyFilter = computed(() => attrFilterActive.value || filterTags.value.length)

const filteredQty = computed(() => filtered.value.reduce((s, c) => s + c.qty, 0))

// 进入页面:有存档牌表则自动恢复并重解析
onMounted(() => {
  if (text.value.trim()) parse()
})

// 视图尺寸:与查卡页共用 state.size(S/M/L/LIST,持久化到 localStorage)
const SIZES = [
  { v: 'S', t: '小' },
  { v: 'M', t: '中' },
  { v: 'L', t: '大' },
  { v: 'LIST', t: '无图' },
]
const cols = computed(() => ({ S: 8, M: 6, L: 4 }[state.size] || 6))
const isList = computed(() => state.size === 'LIST')
const nameCls = computed(() =>
  ({ S: 'text-[11px]', M: 'text-xs', L: 'text-sm' }[state.size] || 'text-xs'))

// 无图列表列布局:数量 + 查卡页同款六列
const LIST_HEADS = ['数量', '名称', '类型', '费用', '标签', '稀有度', 'EDHREC']
const listCols = '3rem ' + LIST_COLS

const rarityMap = {
  common: { t: '普通', c: 'text-faint' },
  uncommon: { t: '非普通', c: 'text-[#8fa8a0]' },
  rare: { t: '稀有', c: 'text-[#5ba4cf]' },
  mythic: { t: '秘稀', c: 'text-[#d95f4e]' },
}
function rarityOf(c) {
  return rarityMap[c.rarity] || rarityMap.common
}
function tagsOf(c) {
  return cardTags(c)
    .slice(0, 3)
    .map((t) => zhDict.value[t] || t)
    .join(' / ')
}

function toggleTag(t) {
  const i = filterTags.value.indexOf(t)
  if (i >= 0) filterTags.value.splice(i, 1)
  else filterTags.value.push(t)
}

function clearFilter() {
  filterTags.value = []
}

async function copyUnmatched() {
  try {
    await navigator.clipboard.writeText(unmatched.value.join('\n'))
    copiedUnmatched.value = true
    setTimeout(() => (copiedUnmatched.value = false), 1500)
  } catch {}
}

function onImg(e) {
  e.target.classList.add('loaded')
}
</script>

<template>
  <div class="min-h-0 flex-1 overflow-y-auto">
    <!-- 输入区 -->
    <div v-if="showInput || !cards" class="mx-auto max-w-2xl px-4 py-10">
      <h2 class="font-display text-xl font-bold text-parch">指挥官牌表 · 标签拆解</h2>
      <p class="mt-1 text-xs text-mute">
        把整份牌表粘到下面(支持 moxfield / 导出的 TXT 格式,中英文卡名均可),
        我会把每张卡按 Tagger 社区标签归类,方便你看这套牌的节奏、去除、过牌等功能分布。
      </p>
      <textarea
        v-model="text"
        rows="14"
        spellcheck="false"
        class="mt-4 w-full resize-y rounded-sm border border-line bg-panel2 p-3 font-num text-xs leading-relaxed text-parch outline-none placeholder:text-faint focus:border-golddim"
        placeholder="Commander&#10;1 欧纳克第二世，乌尔博格之王&#10;&#10;Deck&#10;1 Sol Ring&#10;1 阳光戒&#10;..."
        @keydown.ctrl.enter="parse"
        @keydown.meta.enter="parse"
      ></textarea>
      <div class="mt-3 flex items-center gap-3">
        <button
          class="rounded-sm border px-4 py-1.5 text-sm font-bold tracking-widest transition-colors"
          :class="loading || !text.trim()
            ? 'cursor-not-allowed border-line bg-panel2 text-faint'
            : 'border-golddim bg-golddim/40 text-gold hover:bg-golddim/60'"
          :disabled="loading || !text.trim()"
          @click="parse"
        >{{ loading ? '解析中…' : '解析牌表' }}</button>
        <button class="text-[11px] text-faint transition-colors hover:text-gold" @click="text = EXAMPLE">填入示例</button>
        <span class="text-[11px] text-faint">⌘/Ctrl + Enter 直接解析</span>
      </div>
      <p v-if="error" class="mt-3 text-xs text-red-400">解析失败:{{ error }}</p>
    </div>

    <!-- 结果区 -->
    <div v-else class="px-4 py-4">
      <div class="flex flex-wrap items-center gap-2">
        <button
          class="rounded-sm border px-2.5 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-parch"
          @click="showInput = true"
        >✎ 重新粘贴</button>
        <span class="font-num text-[11px] text-mute">
          {{ cards.length }} 种卡 · {{ totalQty }} 张 · {{ tagCounts.length }} 个标签
        </span>
        <span v-if="unmatched.length" class="rounded-sm border border-red-900 bg-red-950/40 px-2 py-0.5 text-[10px] text-red-300">
          {{ unmatched.length }} 行未识别
        </span>
        <span class="flex-1"></span>
        <button
          v-if="filterTags.length"
          class="rounded-sm border px-1.5 py-1 font-num text-[11px] font-bold transition-colors"
          :class="tagMode === 'and'
            ? 'border-golddim bg-golddim/40 text-gold'
            : 'border-line bg-panel2 text-mute hover:text-parch'"
          :title="tagMode === 'and' ? '当前为交集(同时命中),点击切换为并集' : '当前为并集(命中任一),点击切换为交集'"
          @click="tagMode = tagMode === 'and' ? 'or' : 'and'"
        >{{ tagMode === 'and' ? '∩' : '∪' }}</button>
        <button
          v-if="filterTags.length"
          class="px-2 py-0.5 text-[10px] text-faint transition-colors hover:text-gold"
          @click="clearFilter"
        >清空筛选</button>
        <div class="flex overflow-hidden rounded-sm border border-line">
          <button
            v-for="s in SIZES"
            :key="s.v"
            class="px-2.5 py-1 text-[11px] transition-colors"
            :class="state.size === s.v ? 'bg-golddim/40 text-gold' : 'bg-panel2 text-mute hover:text-parch'"
            @click="state.size = s.v"
          >{{ s.t }}</button>
        </div>
      </div>

      <!-- 颜色 / 类型 / 总法术力 筛选 -->
      <div class="mt-3 rounded-sm border border-line bg-panel p-3">
        <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div class="flex items-center gap-1.5">
            <span class="text-[10px] tracking-widest text-faint">颜色</span>
            <button
              v-for="m in COLOR_ROWS"
              :key="m.c"
              class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
              :class="fColors.includes(m.c)
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              @click="toggleIn(fColors, m.c)"
            >{{ m.label }}</button>
            <button
              class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
              :class="fColorless
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              title="把无色牌(含基本地)也算进来"
              @click="fColorless = !fColorless"
            >无</button>
            <button
              class="rounded-sm border px-1.5 py-0.5 text-[10px] transition-colors"
              :class="fCcExclude
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              title="当前:精确匹配(牌面色=所选) · 点击:不含未选(牌面色⊆所选)"
              @click="fCcExclude = !fCcExclude; if (fCcExclude) fCcPartial = false"
            >⊆</button>
            <button
              class="rounded-sm border px-1.5 py-0.5 font-num text-[10px] transition-colors"
              :class="fCcPartial
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              title="当前:精确匹配(牌面色=所选) · 点击:部分匹配(与所选有交集)"
              @click="fCcPartial = !fCcPartial; if (fCcPartial) fCcExclude = false"
            >∩</button>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="text-[10px] tracking-widest text-faint">类型</span>
            <button
              v-for="m in QUICK_TYPES"
              :key="m.t"
              class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
              :class="fTypes.includes(m.t)
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              title="多选为交集(如 神器+生物 = 神器生物)"
              @click="toggleIn(fTypes, m.t)"
            >{{ m.zh }}</button>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="text-[10px] tracking-widest text-faint">总法术力</span>
            <button
              v-for="v in CMC_OPTIONS"
              :key="v"
              class="rounded-sm border px-1.5 py-0.5 font-num text-[11px] transition-colors"
              :class="fCmc.includes(v)
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              @click="toggleIn(fCmc, v)"
            >{{ v }}</button>
          </div>
          <button
            v-if="attrFilterActive"
            class="px-1.5 py-0.5 text-[10px] text-faint transition-colors hover:text-gold"
            @click="clearAttrFilters"
          >清除</button>
        </div>
        <p class="mt-1.5 text-[10px] text-faint">颜色默认精确匹配(⊆=不含未选 · ∩=部分匹配);类型多选为交集;总法术力多选为并集</p>
      </div>

      <!-- 未识别行 -->
      <div v-if="unmatched.length" class="mt-3 rounded-sm border border-red-900 bg-red-950/30 p-3">
        <div class="flex items-center gap-3">
          <p class="text-[11px] font-bold text-red-300">以下 {{ unmatched.length }} 行没能匹配到卡库:</p>
          <button
            class="rounded-sm border border-red-800 px-2 py-0.5 text-[10px] text-red-200 transition-colors hover:bg-red-900/50"
            @click="copyUnmatched"
          >{{ copiedUnmatched ? '已复制 ✓' : '复制清单' }}</button>
        </div>
        <p class="mt-1 font-num text-[10px] leading-relaxed text-red-200/70">{{ unmatched.join('、') }}</p>
      </div>

      <!-- 标签云 -->
      <div class="mt-3 rounded-sm border border-line bg-panel p-3">
        <p class="text-[10px] tracking-widest text-faint">牌内标签(点击筛选,悬浮看英文原名)</p>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <button
            v-for="[t, n] in shownTagCounts"
            :key="t"
            class="rounded-sm border px-2 py-0.5 text-[10px] transition-colors"
            :class="filterTags.includes(t)
              ? 'border-golddim bg-golddim/40 font-bold text-gold'
              : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
            :title="t"
            @click="toggleTag(t)"
          >{{ tagLabel(t) }} <span class="font-num text-faint">{{ n }}</span></button>
          <button
            v-if="hiddenTagCount > 0"
            class="rounded-sm border border-dashed px-2 py-0.5 text-[10px] transition-colors"
            :class="filterTags.length ? 'border-golddim text-gold' : 'border-line text-mute hover:border-golddim hover:text-parch'"
            @click="tagExpanded = true"
          >更多 · {{ hiddenTagCount }}</button>
          <button
            v-else-if="tagExpanded && tagCounts.length > TAG_TOP_N"
            class="rounded-sm border border-dashed border-line px-2 py-0.5 text-[10px] text-mute transition-colors hover:border-golddim hover:text-parch"
            @click="tagExpanded = false"
          >收起</button>
          <span v-if="untagged.length" class="text-[10px] text-faint">
            ({{ untagged.length }} 张卡无标签)
          </span>
        </div>
      </div>

      <!-- 命中统计 -->
      <p v-if="anyFilter" class="mt-3 text-[11px] text-mute">
        筛选命中 <span class="font-num font-bold text-gold">{{ filtered.length }}</span> 种 /
        <span class="font-num">{{ filteredQty }}</span> 张
      </p>

      <!-- 无图:紧凑列表(数量 + 查卡页同款六列) -->
      <template v-if="isList">
        <div
          class="mt-3 grid gap-2 border-b border-line bg-panel px-3 py-1.5"
          :style="{ gridTemplateColumns: listCols }"
        >
          <span v-for="(h, i) in LIST_HEADS" :key="h"
            class="text-[10px] tracking-[0.15em] text-faint"
            :class="i === LIST_HEADS.length - 1 ? 'text-right' : ''"
          >{{ h }}</span>
        </div>
        <button
          v-for="c in filtered"
          :key="c.oracle_id"
          class="grid w-full items-center gap-2 border-b border-line px-3 py-1.5 text-left transition-colors hover:bg-panel2"
          :style="{ gridTemplateColumns: listCols }"
          @click="openDetail(c.oracle_id)"
        >
          <span class="font-num text-[11px] font-bold text-gold">×{{ c.qty }}</span>
          <span class="min-w-0">
            <span class="block truncate text-xs font-medium text-parch">
              <span v-if="c.is_commander" class="mr-1 rounded-sm bg-gold px-1 text-[9px] font-bold text-ink">主将</span>{{ c.name_zh || c.name_en }}
              <span v-if="c.fuzzy" class="text-[9px] text-yellow-500" title="模糊匹配,卡名可能与原牌表略有出入">?</span>
            </span>
            <span v-if="c.name_zh" class="block truncate text-[10px] text-faint">{{ c.name_en }}</span>
          </span>
          <span class="truncate text-[11px] text-mute">{{ c.type_line_zh || c.type_line_en }}</span>
          <span class="truncate font-num text-[11px] text-mute" :title="c.mana_cost">{{ c.mana_cost || '—' }}</span>
          <span class="truncate text-[10px] text-mute" :title="cardTags(c).join(' / ')">{{ tagsOf(c) || '—' }}</span>
          <span class="text-[11px]" :class="rarityOf(c).c">{{ rarityOf(c).t }}</span>
          <span class="text-right font-num text-[10px] text-faint">{{ c.edhrec_rank || '—' }}</span>
        </button>
        <p v-if="!filtered.length" class="py-16 text-center text-sm text-faint">没有符合筛选条件的卡牌</p>
      </template>

      <!-- 卡牌网格(小/中/大):图片 + 数量徽标 + 可点标签 -->
      <div
        v-else
        class="mt-3 grid gap-3"
        :style="{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }"
      >
        <div v-for="c in filtered" :key="c.oracle_id" class="group flex flex-col gap-1">
          <button class="relative block w-full overflow-hidden rounded-[3px] bg-panel2" @click="openDetail(c.oracle_id)">
            <img
              v-if="c.image_url"
              :src="c.image_url"
              :alt="c.name_en"
              loading="lazy"
              class="cardimg block aspect-[63/88] w-full object-cover"
              @load="onImg"
            />
            <div v-else class="flex aspect-[63/88] w-full items-center justify-center text-[10px] text-faint">无图</div>
            <span v-if="c.is_commander" class="absolute left-1 top-1 rounded-sm bg-gold px-1.5 py-0.5 text-[10px] font-bold text-ink">主将</span>
            <span class="absolute bottom-1 right-1 rounded-sm bg-ink/80 px-1.5 py-0.5 font-num text-[10px] font-bold text-parch">×{{ c.qty }}</span>
          </button>
          <div class="leading-tight">
            <p class="hl-title truncate font-medium" :class="nameCls">
              {{ c.name_zh || c.name_en }}
              <span v-if="c.fuzzy" class="text-[9px] text-yellow-500" title="模糊匹配,卡名可能与原牌表略有出入">?</span>
            </p>
            <p class="mt-0.5 flex items-center gap-1.5 text-[10px] text-mute">
              <span v-if="c.cmc !== null" class="font-num">{{ c.cmc }}</span>
              <ManaText v-if="c.mana_cost" :text="c.mana_cost" />
            </p>
            <div class="mt-1 flex flex-wrap gap-1">
              <button
                v-for="t in cardTags(c)"
                :key="t"
                class="rounded-sm border px-1.5 py-px text-[9px] transition-colors"
                :class="filterTags.includes(t)
                  ? 'border-golddim bg-golddim/40 text-gold'
                  : 'border-line bg-panel2 text-faint hover:border-golddim hover:text-parch'"
                :title="t"
                @click="toggleTag(t)"
              >{{ tagLabel(t) }}</button>
            </div>
          </div>
        </div>
        <p v-if="!filtered.length" class="col-span-full py-16 text-center text-sm text-faint">没有符合筛选条件的卡牌</p>
      </div>

      <!-- 无标签卡 -->
      <div v-if="!filterTags.length && untagged.length" class="mt-6">
        <p class="text-[10px] tracking-widest text-faint">无标签卡 {{ untagged.length }} 张</p>
        <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          <button
            v-for="c in untagged"
            :key="c.oracle_id"
            class="hl-title truncate text-xs text-mute hover:text-parch"
            @click="openDetail(c.oracle_id)"
          >{{ c.name_zh || c.name_en }} <span class="font-num text-faint">×{{ c.qty }}</span></button>
        </div>
      </div>
    </div>
  </div>
</template>
