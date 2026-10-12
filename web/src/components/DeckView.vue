<script setup>
import { ref, computed, onMounted } from 'vue'
import { state, openDetail, LIST_COLS } from '../store'
import ManaText from './ManaText.vue'
import CardTip from './CardTip.vue'

// 悬停卡图浮窗(网格瓦片与无图列表行共用)
const cardTip = ref(null)

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
    clearAttrFilters()
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
// 选项不再写死,全部由当前牌表动态推导
const COLOR_ROWS = [
  { c: 'W', label: '白' }, { c: 'U', label: '蓝' }, { c: 'B', label: '黑' },
  { c: 'R', label: '红' }, { c: 'G', label: '绿' },
]
const TYPE_DEFS = [
  { t: 'Creature', zh: '生物' }, { t: 'Sorcery', zh: '法术' },
  { t: 'Instant', zh: '瞬间' }, { t: 'Enchantment', zh: '结界' },
  { t: 'Artifact', zh: '神器' }, { t: 'Land', zh: '地' },
  { t: 'Planeswalker', zh: '鹏洛客' }, { t: 'Battle', zh: '战役' },
  { t: 'Kindred', zh: '亲缘' }, { t: 'Tribal', zh: '部族' },
]

// 牌表里实际出现的颜色(按 WUBRG 顺序)
const deckColors = computed(() => {
  const present = new Set()
  for (const c of cards.value || []) for (const col of c.colors || []) present.add(col)
  return COLOR_ROWS.filter((m) => present.has(m.c))
})
// 是否存在无色牌(决定是否显示「无」按钮)
const hasColorless = computed(() =>
  (cards.value || []).some((c) => !(c.colors || []).length)
)
// 牌表里实际出现的卡牌类型,带数量,降序
const deckTypes = computed(() => {
  const list = cards.value || []
  return TYPE_DEFS
    .map((d) => ({
      ...d,
      n: list.reduce((s, c) => s + ((c.type_line_en || '').includes(d.t) ? c.qty : 0), 0),
    }))
    .filter((d) => d.n > 0)
    .sort((a, b) => b.n - a.n || a.t.localeCompare(b.t))
})
// 牌表里实际出现的总法术力档位(含 11+)
const cmcOptions = computed(() => {
  const set = new Set()
  for (const c of cards.value || []) {
    const v = c.cmc ?? 0
    set.add(v >= 11 ? '11+' : String(v))
  }
  return [...set].sort((a, b) => (a === '11+' ? 99 : Number(a)) - (b === '11+' ? 99 : Number(b)))
})

// ---------------- 法术力曲线(按牌表动态统计,只统计法术,不含地) ----------------
const isLand = (c) => (c.type_line_en || '').includes('Land')
const curve = computed(() => {
  const buckets = Array.from({ length: 12 }, () => 0)
  for (const c of cards.value || []) {
    if (isLand(c)) continue
    buckets[Math.min(c.cmc ?? 0, 11)] += c.qty
  }
  return buckets
})
const curveMax = computed(() => Math.max(1, ...curve.value))
const curveSpellsTotal = computed(() => curve.value.reduce((s, n) => s + n, 0))
const curveLandsTotal = computed(() =>
  (cards.value || []).reduce((s, c) => s + (isLand(c) ? c.qty : 0), 0)
)
// 指挥官主将(Partner 时可能有多位;牌表未标主将时可手动指定,持久化到 localStorage)
const CMD_KEY = 'mtg-deck-commander'
function loadCmd() {
  try { return JSON.parse(localStorage.getItem(CMD_KEY) || 'null') } catch { return null }
}
const manualCmd = ref(loadCmd())
function setManualCommander(c) {
  manualCmd.value = c
  try { localStorage.setItem(CMD_KEY, JSON.stringify(c)) } catch {}
}
function clearManualCommander() {
  manualCmd.value = null
  try { localStorage.removeItem(CMD_KEY) } catch {}
}
const commanders = computed(() => {
  const list = cards.value || []
  const m = list.filter((c) => c.is_commander)
  if (manualCmd.value && !m.some((c) => c.oracle_id === manualCmd.value.oracle_id)) {
    // 手动指定的卡在牌表里:直接展示牌表数据(无「手动」标记);不在牌表里才追加手动条目
    const inDeck = list.find((c) => c.oracle_id === manualCmd.value.oracle_id)
    m.push(inDeck ? inDeck : { ...manualCmd.value, _manual: true })
  }
  return m
})
// 主将 oracle_id 集合:网格/列表里的徽标以它为准(含手动指定)
const commanderIds = computed(() => new Set(commanders.value.map((c) => c.oracle_id)))

// 主将选择器:按卡名实时搜索(走 /api/search 全文模式)
const pickerOpen = ref(false)
const pickerQ = ref('')
const pickerItems = ref([])
const pickerLoading = ref(false)
let pickerSeq = 0
let pickerTimer = 0
async function pickerSearch() {
  const q = pickerQ.value.trim()
  pickerItems.value = []
  if (!q) return
  const my = ++pickerSeq
  pickerLoading.value = true
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q) + '&mode=fts&page_size=8')
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    if (my === pickerSeq) pickerItems.value = d.items || []
  } catch {
    if (my === pickerSeq) pickerItems.value = []
  } finally {
    if (my === pickerSeq) pickerLoading.value = false
  }
}
function onPickerInput() {
  clearTimeout(pickerTimer)
  pickerTimer = setTimeout(pickerSearch, 250)
}
function pickCommander(it) {
  setManualCommander({
    oracle_id: it.oracle_id,
    name_zh: it.name_zh,
    name_en: it.name_en,
    image_url: it.image_url,
    cmc: it.cmc,
    mana_cost: it.mana_cost,
    type_line_zh: it.type_line_zh,
    type_line_en: it.type_line_en,
    rarity: it.rarity,
    edhrec_rank: it.edhrec_rank,
    qty: 1,
  })
  pickerOpen.value = false
  pickerQ.value = ''
  pickerItems.value = []
}
function closePicker() {
  pickerOpen.value = false
  pickerQ.value = ''
  pickerItems.value = []
}
function curvePct(n) {
  return `${(n / curveMax.value) * 100}%`
}
function curveLabel(i) {
  return i >= 11 ? '11+' : String(i)
}

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
    <CardTip ref="cardTip" />
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

      <!-- 指挥官主将(始终显示;未识别时可在面板内手动搜索指定) -->
      <div class="mt-3 flex items-stretch gap-3 rounded-sm border border-golddim/60 bg-panel p-3">
        <div class="flex shrink-0 flex-col justify-center border-r border-line pr-3">
          <span class="text-[10px] tracking-[0.2em] text-faint">主将</span>
        </div>

        <!-- 已有主将:展示 + 可再添加(搭档) -->
        <div v-if="commanders.length && !pickerOpen" class="flex min-w-0 flex-1 flex-wrap items-center gap-x-6 gap-y-2">
          <div
            v-for="c in commanders"
            :key="c.oracle_id"
            class="group flex min-w-0 items-stretch gap-2.5"
          >
            <button class="flex min-w-0 items-stretch gap-2.5 text-left" @click="openDetail(c.oracle_id)">
              <div class="w-[68px] shrink-0 overflow-hidden rounded-[3px] bg-panel2">
                <img
                  v-if="c.image_url"
                  :src="c.image_url"
                  :alt="c.name_en"
                  loading="lazy"
                  class="block aspect-[63/88] w-full object-cover transition-transform group-hover:scale-105"
                  @load="onImg"
                />
                <div v-else class="flex aspect-[63/88] w-full items-center justify-center text-[9px] text-faint">无图</div>
              </div>
              <div class="min-w-0 py-0.5">
                <p class="hl-title truncate text-sm font-bold text-gold group-hover:text-parch">{{ c.name_zh || c.name_en }}</p>
                <p v-if="c.name_zh" class="truncate font-num text-[10px] text-faint">{{ c.name_en }}</p>
                <p class="mt-1 flex items-center gap-1.5 font-num text-[11px] text-mute">
                  <span>{{ c.cmc }}</span>
                  <ManaText v-if="c.mana_cost" :text="c.mana_cost" />
                </p>
                <p class="mt-0.5 truncate text-[10px] text-mute">{{ c.type_line_zh || c.type_line_en }}</p>
                <p class="mt-1 truncate text-[10px] text-faint">
                  <span :class="rarityOf(c).c">{{ rarityOf(c).t }}</span>
                  <span v-if="c.edhrec_rank"> · EDHREC #{{ c.edhrec_rank }}</span>
                  <span v-if="c._manual" class="text-yellow-600/70" title="手动指定的主将"> · 手动</span>
                </p>
              </div>
            </button>
            <button
              v-if="c._manual"
              class="self-start px-0.5 text-[10px] text-faint transition-colors hover:text-red-400"
              title="移除手动指定的主将"
              @click="clearManualCommander"
            >×</button>
          </div>
          <button
            class="rounded-sm border border-dashed px-2.5 py-1.5 text-[11px] transition-colors"
            :class="commanders.length ? 'border-line text-mute hover:border-golddim hover:text-parch' : 'border-golddim text-gold'"
            @click="pickerOpen = true"
          >＋ 添加</button>
        </div>

        <!-- 主将选择器:无主将时默认展开,或点「添加」打开 -->
        <div v-else class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <input
              v-model="pickerQ"
              type="text"
              spellcheck="false"
              class="w-full max-w-sm rounded-sm border border-line bg-panel2 px-2 py-1 text-xs text-parch outline-none placeholder:text-faint focus:border-golddim"
              placeholder="搜索卡名指定主将(中英文均可),回车立即搜索"
              @input="onPickerInput"
              @keydown.enter="pickerSearch"
            />
            <span v-if="pickerLoading" class="text-[10px] text-faint">搜索中…</span>
            <button
              v-if="commanders.length"
              class="shrink-0 text-[10px] text-faint transition-colors hover:text-gold"
              @click="closePicker"
            >收起</button>
          </div>
          <div v-if="pickerItems.length" class="mt-2 flex flex-wrap gap-1.5">
            <button
              v-for="it in pickerItems"
              :key="it.oracle_id"
              class="flex items-center gap-1.5 rounded-sm border border-line bg-panel2 px-1.5 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-parch"
              @click="pickCommander(it)"
            >
              <img
                v-if="it.image_url"
                :src="it.image_url"
                :alt="it.name_en"
                loading="lazy"
                class="h-8 w-[23px] rounded-[2px] object-cover"
              />
              <span class="truncate">{{ it.name_zh || it.name_en }}</span>
              <span class="font-num text-[9px] text-faint">{{ it.cmc }}</span>
            </button>
          </div>
          <p v-else-if="pickerQ.trim() && !pickerLoading" class="mt-2 text-[10px] text-faint">没有匹配的卡,换个关键词试试</p>
          <p v-else class="mt-2 text-[10px] text-faint">牌表里没有识别到主将,搜索一张卡把它设为这套牌的主将</p>
        </div>
      </div>

      <!-- 曲线 + 筛选:左右两栏(筛选在左,曲线在右,高度对齐) -->
      <div class="mt-3 flex flex-wrap gap-3">

      <!-- 法术力曲线(右栏,固定宽度,与筛选栏等高) -->
      <div class="order-2 flex w-[320px] shrink-0 flex-col rounded-sm border border-line bg-panel p-3">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span class="text-[10px] tracking-widest text-faint">法术力曲线</span>
          <span class="text-[10px] text-faint">法术 {{ curveSpellsTotal }} 张 · 不含地(地 {{ curveLandsTotal }} 张)</span>
        </div>
        <div class="mt-2 flex flex-1 items-end gap-1">
          <div v-for="(n, i) in curve" :key="i" class="flex min-w-0 flex-1 flex-col items-center gap-0.5"
            :title="`${curveLabel(i)} 费:${n} 张`"
          >
            <span class="font-num text-[9px] leading-none text-faint">{{ n || '' }}</span>
            <div class="flex h-20 w-full flex-col justify-end">
              <div class="w-full bg-golddim" :style="{ height: curvePct(n) }"></div>
            </div>
            <span class="font-num text-[9px] leading-none text-mute">{{ curveLabel(i) }}</span>
          </div>
        </div>
      </div>

      <!-- 颜色 / 类型 / 总法术力 筛选 -->
      <div class="order-1 min-w-0 flex-1 rounded-sm border border-line bg-panel p-3">
        <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div class="flex items-center gap-1.5">
            <span class="text-[10px] tracking-widest text-faint">颜色</span>
            <button
              v-for="m in deckColors"
              :key="m.c"
              class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
              :class="fColors.includes(m.c)
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              @click="toggleIn(fColors, m.c)"
            >{{ m.label }}</button>
            <button
              v-if="hasColorless"
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
          <div v-if="deckTypes.length" class="flex items-center gap-1.5">
            <span class="text-[10px] tracking-widest text-faint">类型</span>
            <button
              v-for="m in deckTypes"
              :key="m.t"
              class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
              :class="fTypes.includes(m.t)
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              title="多选为交集(如 神器+生物 = 神器生物)"
              @click="toggleIn(fTypes, m.t)"
            >{{ m.zh }} <span class="font-num text-faint">{{ m.n }}</span></button>
          </div>
          <div v-if="cmcOptions.length" class="flex items-center gap-1.5">
            <span class="text-[10px] tracking-widest text-faint">总法术力</span>
            <button
              v-for="v in cmcOptions"
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
          @mouseenter="cardTip?.show($event, c, `×${c.qty} · ${c.type_line_zh || c.type_line_en || ''}`)"
          @mousemove="cardTip?.move"
          @mouseleave="cardTip?.hide"
        >
          <span class="font-num text-[11px] font-bold text-gold">×{{ c.qty }}</span>
          <span class="min-w-0">
            <span class="block truncate text-xs font-medium text-parch">
              <span v-if="commanderIds.has(c.oracle_id)" class="mr-1 rounded-sm bg-gold px-1 text-[9px] font-bold text-ink">主将</span>{{ c.name_zh || c.name_en }}
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
        <div
          v-for="c in filtered"
          :key="c.oracle_id"
          class="group flex flex-col gap-1"
          @mouseenter="cardTip?.show($event, c)"
          @mousemove="cardTip?.move"
          @mouseleave="cardTip?.hide"
        >
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
            <span v-if="commanderIds.has(c.oracle_id)" class="absolute left-1 top-1 rounded-sm bg-gold px-1.5 py-0.5 text-[10px] font-bold text-ink">主将</span>
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
            @mouseenter="cardTip?.show($event, c, `×${c.qty}`)"
            @mousemove="cardTip?.move"
            @mouseleave="cardTip?.hide"
          >{{ c.name_zh || c.name_en }} <span class="font-num text-faint">×{{ c.qty }}</span></button>
        </div>
      </div>
    </div>
  </div>
</template>
