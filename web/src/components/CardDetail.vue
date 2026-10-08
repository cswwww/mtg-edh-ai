<script setup>
import { computed, ref, watch } from 'vue'
import { detail, closeDetail, state, openDetail, search } from '../store'
import ManaText from './ManaText.vue'

const faceIdx = ref(0)
const showEnText = ref(false)
watch(() => detail.value?.oracle_id, () => {
  faceIdx.value = 0
  showEnText.value = false
  lightbox.value = false
  // 换卡时收掉弹窗并清空旧列表与弹窗内筛选,防止再打开时展示上一张卡的残留数据
  similarOpen.value = false
  similar.value = []
  similarTotal.value = 0
  similarNumTags.value = 0
  similarPage.value = 1
  similarFor.value = ''
  simCi.value = []
  simCiColorless.value = false
  simTypes.value = []
  loadEdhrec()
  loadMtgstocks()
})

const edhrecData = ref(null)
const edhrecLoading = ref(false)
const edhrecError = ref('')

// 主将卡图悬浮层
const tip = ref({ show: false, x: 0, y: 0, name: '', img: '' })
function showTip(e, c) {
  tip.value = { show: true, x: 0, y: 0, name: c.name, img: c.image_url || '', pct: c.pct || 0, num: c.num_decks || 0 }
  moveTip(e)
}
// 版本卡图悬浮层(懒加载,前端再缓存一份)
const verTip = ref({ show: false, x: 0, y: 0, name: '', img: '' })
const verImgCache = new Map()
async function showVerTip(e, s) {
  verTip.value = { show: true, x: 0, y: 0, name: setTitle(s), img: '', loading: true }
  moveTip(e)
  const oid = detail.value?.oracle_id
  if (!oid) return
  const key = oid + '_' + s
  if (!verImgCache.has(key)) {
    try {
      const r = await fetch(`/api/print_image/${oid}/${s}`)
      verImgCache.set(key, r.ok ? (await r.json()).image : null)
    } catch {
      verImgCache.set(key, null)
    }
  }
  if (verTip.value.show) verTip.value = { ...verTip.value, img: verImgCache.get(key) || '', loading: false }
}
function place(refObj, e) {
  const W = 176, H = 300  // 浮层估算尺寸(宽 40*4 + 边距)
  let x = e.clientX + 18
  let y = e.clientY + 14
  if (x + W > window.innerWidth) x = e.clientX - W - 10
  if (y + H > window.innerHeight) y = window.innerHeight - H - 8
  refObj.value.x = Math.max(4, x)
  refObj.value.y = Math.max(4, y)
}
function moveTip(e) {
  if (tip.value.show) place(tip, e)
  if (verTip.value.show) place(verTip, e)
}
function hideTip() {
  tip.value.show = false
}
function hideVerTip() {
  verTip.value.show = false
}
async function loadEdhrec() {
  edhrecData.value = null
  edhrecError.value = ''
  const oid = detail.value?.oracle_id
  if (!oid) return
  edhrecLoading.value = true
  try {
    const r = await fetch('/api/edhrec/' + oid)
    if (r.ok) {
      edhrecData.value = await r.json()
    } else if (r.status === 404) {
      edhrecError.value = 'EDHREC 暂无此卡数据'
    } else {
      edhrecError.value = 'EDHREC 查询失败'
    }
  } catch {
    edhrecError.value = 'EDHREC 查询失败'
  } finally {
    edhrecLoading.value = false
  }
}

const faces = computed(() => detail.value?.faces || [])
const cur = computed(() => faces.value[faceIdx.value] || null)

// MTGStocks 价格历史外链 + 走势图数据(后端带缓存)
const mtgstocksUrl = ref('')
const msSeries = ref(null)   // {avg: [[ts,p]...], market: [[ts,p]...]}
async function loadMtgstocks() {
  mtgstocksUrl.value = ''
  msSeries.value = null
  const oid = detail.value?.oracle_id
  if (!oid) return
  try {
    const r = await fetch('/api/mtgstocks/' + oid)
    if (r.ok) {
      const d = await r.json()
      mtgstocksUrl.value = d.url || ''
      if (d.prices?.series?.avg?.length > 1) msSeries.value = d.prices.series
    }
  } catch { /* 静默失败,不展示按钮 */ }
}

// SVG 折线图:对数坐标(价格波动大),双序列(avg 实线 / market 虚线)
const msChart = computed(() => {
  const s = msSeries.value
  if (!s) return null
  const W = 560, H = 150, PAD = { l: 44, r: 10, t: 12, b: 20 }
  const all = [...(s.avg || []), ...(s.market || [])]
  if (!all.length) return null
  const ts = all.map(p => p[0])
  const lo = Math.min(...all.map(p => p[1])), hi = Math.max(...all.map(p => p[1]))
  const t0 = Math.min(...ts), t1 = Math.max(...ts)
  const span = Math.max(t1 - t0, 1)
  // 对数缩放,价格必须 > 0
  const loL = Math.log10(Math.max(lo, 0.01)), hiL = Math.log10(Math.max(hi, 0.011))
  const lSpan = Math.max(hiL - loL, 0.001)
  const x = t => PAD.l + (t - t0) / span * (W - PAD.l - PAD.r)
  const y = v => PAD.t + (1 - (Math.log10(Math.max(v, 0.01)) - loL) / lSpan) * (H - PAD.t - PAD.b)
  const line = pts => pts.map(p => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')
  // 年份刻度
  const years = []
  for (let yr = new Date(t0).getUTCFullYear() + 1; yr <= new Date(t1).getUTCFullYear(); yr++) {
    const yt = Date.UTC(yr, 0, 1)
    if (yt <= t1) years.push({ x: x(yt), label: String(yr) })
  }
  const lastAvg = s.avg?.length ? s.avg[s.avg.length - 1] : null
  return {
    w: W, h: H,
    avgLine: line(s.avg || []),
    marketLine: s.market?.length > 1 ? line(s.market) : '',
    lo, hi, years,
    lastX: lastAvg ? x(lastAvg[0]) : 0,
    lastY: lastAvg ? y(lastAvg[1]) : 0,
    lastV: lastAvg ? lastAvg[1] : null,
    labelLo: lo >= 1 ? '$' + lo.toFixed(0) : '$' + lo.toFixed(2),
    labelHi: hi >= 1 ? '$' + hi.toFixed(0) : '$' + hi.toFixed(2),
  }
})
function msYear(ts) { return new Date(ts).getUTCFullYear() }

const priceUsd = computed(() => detail.value?.prices?.usd || detail.value?.prices?.usd_foil)
const rarityZh = { common: '普通', uncommon: '非普通', rare: '稀有', mythic: '秘稀' }

// 卡图大图查看器 / 类似单卡弹窗打开时锁定页面滚动
const lightbox = ref(false)
const similarOpen = ref(false)
watch([lightbox, similarOpen], ([lb, sim]) => {
  document.body.style.overflow = (lb || sim) ? 'hidden' : ''
})

// 版本 -> Scryfall 精确搜索页(该系列中的这张卡)
function setLink(s) {
  const q = `!"${detail.value.name_en}" set:${s.toLowerCase()}`
  return 'https://scryfall.com/search?q=' + encodeURIComponent(q)
}
function setTitle(s) {
  const name = state.meta?.sets?.[s.toUpperCase()]
  return name ? `${name}(${s})` : s
}

// ---- AI 元数据展示 ----
// 是否有任何 AI 内容(只有 ai_desc 一个字段了)
const hasAiMeta = computed(() => {
  return !!(detail.value?.ai_desc)
})

// ---- 类似单卡:弹窗展示,按共同标签数排序(相似度 = 共同标签 / 当前卡标签数) ----
const simTags = computed(() => {
  const d = detail.value
  if (!d) return []
  return [...new Set([...(d.sf_tags || []), ...(d.ai_tags || [])])]
})
const similar = ref([])
const similarTotal = ref(0)
const similarNumTags = ref(0)
const similarPage = ref(1)
const similarLoading = ref(false)
const similarError = ref('')
const similarFor = ref('')   // 当前列表属于哪张卡,换卡后失效
const SIM_PAGE_SIZE = 24
// 弹窗内筛选:指挥官颜色(标识色 ⊆ 所选)、卡牌类型(多选为交集)
const simCi = ref([])
const simCiColorless = ref(false)
const simTypes = ref([])
const SIM_TYPES = [
  { t: 'Creature', zh: '生物' }, { t: 'Sorcery', zh: '法术' },
  { t: 'Instant', zh: '瞬间' }, { t: 'Enchantment', zh: '结界' },
  { t: 'Artifact', zh: '神器' }, { t: 'Land', zh: '地' },
  { t: 'Planeswalker', zh: '鹏洛客' },
]
const simColors = [
  { c: 'W', label: '白' }, { c: 'U', label: '蓝' }, { c: 'B', label: '黑' },
  { c: 'R', label: '红' }, { c: 'G', label: '绿' },
]
const simFilterActive = computed(() =>
  simCi.value.length > 0 || simCiColorless.value || simTypes.value.length > 0)

function reloadSimilar() {
  loadSimilarPage(1)
}

function toggleSimCi(c) {
  const i = simCi.value.indexOf(c)
  if (i >= 0) simCi.value.splice(i, 1)
  else simCi.value.push(c)
  reloadSimilar()
}

function toggleSimType(t) {
  const i = simTypes.value.indexOf(t)
  if (i >= 0) simTypes.value.splice(i, 1)
  else simTypes.value.push(t)
  reloadSimilar()
}

function clearSimFilters() {
  simCi.value = []
  simCiColorless.value = false
  simTypes.value = []
  reloadSimilar()
}

async function loadSimilarPage(page) {
  const oid = detail.value?.oracle_id
  if (!oid) return
  similarLoading.value = true
  similarError.value = ''
  try {
    const p = new URLSearchParams()
    p.set('page', page)
    p.set('page_size', SIM_PAGE_SIZE)
    if (simCi.value.length) p.set('ci', simCi.value.join(','))
    if (simCiColorless.value) p.set('ci_colorless', '1')
    if (simTypes.value.length) p.set('type', simTypes.value.join(','))
    const r = await fetch(`/api/similar/${oid}?` + p.toString())
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    similarTotal.value = d.total
    similarNumTags.value = d.num_tags
    similar.value = page === 1 ? d.items : similar.value.concat(d.items)
    similarPage.value = page
    similarFor.value = oid
  } catch (e) {
    similarError.value = '类似单卡查询失败'
  } finally {
    similarLoading.value = false
  }
}

function openSimilar() {
  similarOpen.value = true
  // 列表为空或不是当前卡的(理论上换卡时已清空,这里兜底)才重新加载
  if (similarFor.value !== detail.value?.oracle_id || !similar.value.length) {
    loadSimilarPage(1)
  }
}

// 把标签 + 弹窗内的颜色/类型筛选带回主列表:并集语义,按 EDHREC 热度排序
function viewAllSimilar() {
  state.tags = [...simTags.value]
  state.tagMode = 'or'
  state.sort = 'edhrec'
  state.ciColors = [...simCi.value]
  state.ciColorless = simCiColorless.value
  state.types = [...simTypes.value]
  similarOpen.value = false
  closeDetail()
  search()
}

// 点单个标签 chip:按该标签查询(无搜索词时即按 EDHREC 排序的全量列表)
function searchByTag(t) {
  state.tags = [t]
  state.tagMode = 'or'
  closeDetail()
  search()
}
</script>

<template>
  <div v-if="detail || true" class="pointer-events-none fixed inset-0 z-50">
    <div
      class="absolute inset-0 cursor-pointer bg-black/50 transition-opacity"
      :class="detail ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'"
      @click="closeDetail()"
    ></div>
    <div
      class="pointer-events-auto absolute right-0 top-0 flex h-full w-[26rem] max-w-full flex-col border-l border-line bg-panel transition-transform duration-200"
      :class="detail ? 'translate-x-0' : 'translate-x-full'"
    >
      <template v-if="detail">
        <div class="flex items-start justify-between gap-2 border-b border-line p-4">
          <div>
            <h2 class="font-display text-xl font-semibold leading-tight text-parch">
              {{ detail.name_zh || detail.name_en }}
            </h2>
            <p class="mt-0.5 text-xs text-faint">{{ detail.name_en }}</p>
          </div>
          <button class="px-2 text-lg text-mute hover:text-gold" @click="closeDetail()">✕</button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-4">
          <!-- 图片区 -->
          <div class="flex gap-3">
            <div class="w-44 shrink-0">
              <img
                :src="cur?.image || detail.image_url"
                :alt="detail.name_en"
                class="w-full cursor-zoom-in rounded-[3px] transition-opacity hover:opacity-85"
                title="点击查看大图"
                @click="lightbox = true"
              />
              <div v-if="faces.length > 1" class="mt-2 flex gap-1">
                <button
                  v-for="(f, i) in faces"
                  :key="i"
                  class="flex-1 truncate rounded-sm border px-1.5 py-1 text-[11px] transition-colors"
                  :class="i === faceIdx ? 'border-gold bg-golddim/30 text-gold' : 'border-line text-mute hover:text-parch'"
                  @click="faceIdx = i"
                >{{ f.name_zh || f.name_en }}</button>
              </div>
            </div>

            <div class="min-w-0 flex-1 space-y-2 text-xs">
              <p v-if="(cur?.mana_cost ?? detail.mana_cost)" class="text-sm">
                <ManaText :text="cur?.mana_cost ?? detail.mana_cost" />
                <span class="ml-2 font-num text-mute">{{ detail.cmc }}</span>
              </p>
              <p class="text-mute">
                {{ cur?.type_zh || detail.type_line_zh }}
                <span v-if="cur?.type_zh && cur?.type_en" class="text-faint"> · {{ cur?.type_en }}</span>
                <span v-else-if="detail.type_line_en" class="text-faint"> · {{ detail.type_line_en }}</span>
              </p>
              <p v-if="cur?.pt" class="font-num text-parch">{{ cur.pt }}</p>
              <p v-else-if="detail.power" class="font-num text-parch">{{ detail.power }}/{{ detail.toughness }}</p>
              <p class="text-mute">
                {{ rarityZh[detail.rarity] || detail.rarity }}
                · {{ detail.set_code }} #{{ detail.collector_number }}
                · {{ detail.released_at }}
              </p>
              <p v-if="detail.edhrec_rank" class="text-mute">EDHREC 排名 <span class="font-num text-gold">{{ detail.edhrec_rank }}</span></p>
              <p v-if="priceUsd" class="text-mute">价格 <span class="font-num">${{ priceUsd }}</span></p>
              <p v-if="detail.sf_id || mtgstocksUrl" class="flex flex-wrap gap-1.5">
                <a
                  :href="`https://www.mtgstand.com/card-sid-${detail.sf_id}`"
                  target="_blank"
                  class="inline-block rounded-sm border border-line bg-panel2 px-2 py-1 text-[10px] tracking-[0.15em] text-mute transition-colors hover:border-golddim hover:text-gold"
                >MTGSTAND · 价格 ↗</a>
                <a
                  v-if="mtgstocksUrl"
                  :href="mtgstocksUrl"
                  target="_blank"
                  class="inline-block rounded-sm border border-line bg-panel2 px-2 py-1 text-[10px] tracking-[0.15em] text-mute transition-colors hover:border-golddim hover:text-gold"
                >MTGSTOCKS · 历史 ↗</a>
              </p>

              <!-- MTGStocks 价格走势图 -->
              <div v-if="msChart" class="mt-2">
                <p class="mb-1 flex items-center justify-between text-[10px] tracking-[0.2em] text-faint">
                  <span>MTGSTOCKS · TCGPLAYER 价格走势</span>
                  <span v-if="msChart.lastV != null" class="font-num text-gold">最新 ${{ msChart.lastV.toFixed(2) }}</span>
                </p>
                <svg :viewBox="`0 0 ${msChart.w} ${msChart.h}`" class="w-full rounded-sm border border-line bg-panel2">
                  <!-- 网格线与价格标签(对数坐标,上下限) -->
                  <text :x="4" :y="16" class="fill-faint" font-size="9">{{ msChart.labelHi }}</text>
                  <text :x="4" :y="msChart.h - 6" class="fill-faint" font-size="9">{{ msChart.labelLo }}</text>
                  <line :x1="44" :y1="12" :x2="msChart.w - 10" :y2="12" class="stroke-line" stroke-width="0.5" stroke-dasharray="2,3" />
                  <line :x1="44" :y1="msChart.h - 20" :x2="msChart.w - 10" :y2="msChart.h - 20" class="stroke-line" stroke-width="0.5" stroke-dasharray="2,3" />
                  <!-- market 虚线(2015 起有数据) -->
                  <polyline v-if="msChart.marketLine" :points="msChart.marketLine" fill="none" class="stroke-faint" stroke-width="1" stroke-dasharray="3,3" opacity="0.6" />
                  <!-- avg 实线 -->
                  <polyline :points="msChart.avgLine" fill="none" class="stroke-gold" stroke-width="1.5" />
                  <!-- 最新点 -->
                  <circle :cx="msChart.lastX" :cy="msChart.lastY" r="2.5" class="fill-gold" />
                  <!-- 年份刻度 -->
                  <text v-for="y in msChart.years" :key="y.label" :x="y.x" :y="msChart.h - 6" text-anchor="middle" class="fill-faint" font-size="8">{{ y.label }}</text>
                </svg>
                <p class="mt-0.5 text-right text-[9px] text-faint">金线均价 · 灰虚线市价(美元,对数刻度) · 按月采样</p>
              </div>
              <p v-if="detail.keywords?.length" class="leading-relaxed text-faint">
                {{ detail.keywords.join(' · ') }}
              </p>
            </div>
          </div>

          <!-- 规则叙述 -->
          <div class="mt-4 space-y-3">
            <div v-if="cur ? cur.text_zh : detail.oracle_text_zh" class="border-l-2 border-golddim pl-3">
              <p class="mb-1 text-[10px] tracking-[0.2em] text-faint">规则叙述</p>
              <ManaText :text="cur ? cur.text_zh : detail.oracle_text_zh" class="text-sm text-parch" />
            </div>
            <div v-if="cur ? cur.text_en : detail.oracle_text_en" class="border-l-2 border-line pl-3">
              <button
                v-if="!showEnText"
                class="text-[10px] tracking-[0.2em] text-faint underline-offset-2 transition-colors hover:text-gold hover:underline"
                @click="showEnText = true"
              >▸ 显示英文规则</button>
              <template v-else>
                <button
                  class="mb-1 block text-[10px] tracking-[0.2em] text-faint underline-offset-2 transition-colors hover:text-gold hover:underline"
                  @click="showEnText = false"
                >▾ 隐藏英文规则</button>
                <ManaText :text="cur ? cur.text_en : detail.oracle_text_en" class="text-sm text-mute" />
              </template>
            </div>
            <div v-if="detail.flavor_text_zh" class="pl-3 text-xs text-faint opacity-75">
              {{ detail.flavor_text_zh }}
            </div>
          </div>

          <!-- Scryfall Tagger 社区标签 -->
          <div v-if="detail.sf_tags?.length" class="mt-5">
            <p class="mb-1.5 text-[10px] tracking-[0.2em] text-faint">SCRYFALL TAGGER · 社区标签(点击按标签查询)</p>
            <div class="flex flex-wrap gap-1">
              <button
                v-for="t in detail.sf_tags"
                :key="t"
                :title="t + ' · 点击查询带此标签的卡'"
                class="rounded-sm border border-line bg-panel2 px-1.5 py-0.5 text-[10px] text-mute transition-colors hover:border-golddim hover:text-gold"
                @click="searchByTag(t)"
              >{{ state.meta?.tagdict?.[t] || t }}</button>
            </div>
          </div>

          <!-- 类似单卡:点击弹窗展示,按共同标签数排序 -->
          <button
            v-if="simTags.length"
            class="mt-5 w-full rounded-sm border border-line bg-panel2 px-2 py-1.5 text-[11px] tracking-[0.15em] text-mute transition-colors hover:border-golddim hover:text-gold"
            @click="openSimilar()"
          >⚭ 类似单卡 · 按 {{ simTags.length }} 个标签查找</button>

          <!-- AI 功能定位(LLM 一句话) -->
          <div v-if="hasAiMeta" class="mt-5">
            <p class="mb-1.5 text-[10px] tracking-[0.2em] text-faint">AI · 功能定位</p>
            <div v-if="detail.ai_desc" class="border-l-2 border-golddim pl-3 text-xs text-parch">
              <p>{{ detail.ai_desc }}</p>
            </div>
          </div>

          <!-- EDHREC 主将使用率 -->
          <div class="mt-5">
            <p class="mb-1.5 text-[10px] tracking-[0.2em] text-faint">EDHREC · 使用这张卡的主将</p>
            <p v-if="edhrecLoading" class="text-xs text-faint">查询中…</p>
            <p v-else-if="edhrecError" class="text-xs text-faint">{{ edhrecError }}</p>
            <div v-else class="space-y-1.5">
              <div v-for="c in edhrecData?.commanders?.slice(0, 10) || []" :key="c.slug" class="flex items-center gap-2">
                <div class="h-1.5 shrink-0 rounded-sm bg-gold" :style="{ width: `${(c.pct || 0) * 100}px` }"></div>
                <a
                  :href="`https://edhrec.com${c.url || '/commanders/' + c.slug}`"
                  target="_blank"
                  class="min-w-0 flex-1 truncate text-xs text-parch hover:text-gold"
                  @mouseenter="showTip($event, c)"
                  @mousemove="moveTip"
                  @mouseleave="hideTip"
                >{{ c.name }}</a>
                <span class="shrink-0 font-num text-[10px] text-faint">{{ c.pct ? (c.pct * 100).toFixed(1) + '%' : '' }} · {{ (c.num_decks || 0).toLocaleString() }}</span>
              </div>
              <p v-if="!edhrecData?.commanders?.length" class="text-xs text-faint">EDHREC 暂无数据</p>
              <p v-else class="pt-1 text-right text-[10px] text-faint">
                数据来自 EDHREC · {{ (edhrecData.num_decks || 0).toLocaleString() }} 套牌在用
              </p>
            </div>
          </div>

          <!-- 主将卡图悬浮层(挂载到 body,避免被抽屉的 translate 影响定位) -->
          <Teleport to="body">
            <div
              v-if="verTip.show"
              class="pointer-events-none fixed z-[60] w-40 overflow-hidden rounded-[3px] border border-line bg-panel shadow-2xl"
              :style="{ left: verTip.x + 'px', top: verTip.y + 'px' }"
            >
              <img v-if="verTip.img" :src="verTip.img" class="cardimg loaded block w-full" />
              <div v-else class="flex h-52 w-full items-center justify-center text-[10px] text-faint">
                {{ verTip.loading ? '加载中…' : '无卡图' }}
              </div>
              <div class="border-t border-line bg-panel px-1.5 py-1">
                <p class="truncate text-[10px] text-mute">{{ verTip.name }}</p>
              </div>
            </div>
            <div
              v-if="tip.show"
              class="pointer-events-none fixed z-[60] w-40 overflow-hidden rounded-[3px] border border-line bg-panel shadow-2xl"
              :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
            >
              <img v-if="tip.img" :src="tip.img" class="cardimg loaded block w-full" />
              <div v-else class="flex h-52 w-full items-center justify-center text-[10px] text-faint">无卡图</div>
              <div class="border-t border-line bg-panel px-1.5 py-1">
                <p class="truncate text-[10px] text-mute">{{ tip.name }}</p>
                <div class="mt-1 flex items-center gap-1.5">
                  <div class="h-1 flex-1 overflow-hidden rounded-sm bg-panel2">
                    <div class="h-full rounded-sm bg-gold" :style="{ width: `${Math.min(100, tip.pct * 100)}%` }"></div>
                  </div>
                  <span class="shrink-0 font-num text-[9px] text-faint">
                    {{ (tip.pct * 100).toFixed(1) }}% · {{ tip.num.toLocaleString() }} 套
                  </span>
                </div>
              </div>
            </div>
          </Teleport>

          <!-- 版本(点击跳 Scryfall 该系列的这张卡) -->
          <div class="mt-5">
            <p class="mb-1.5 text-[10px] tracking-[0.2em] text-faint">版本({{ detail.all_sets.length }})</p>
            <div class="flex flex-wrap gap-1">
              <a
                v-for="s in detail.all_sets"
                :key="s"
                :href="setLink(s)"
                target="_blank"
                :title="setTitle(s)"
                class="rounded-sm bg-panel2 px-1.5 py-0.5 font-num text-[10px] text-mute transition-colors hover:bg-golddim/40 hover:text-gold"
                @mouseenter="showVerTip($event, s)"
                @mousemove="moveTip"
                @mouseleave="hideVerTip"
              >{{ s }}</a>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="flex h-full items-center justify-center text-sm text-faint">加载中…</div>
    </div>

    <!-- 卡图大图查看器(挂载 body,盖住抽屉) -->
    <Teleport to="body">
      <div
        v-if="lightbox && detail"
        class="pointer-events-auto fixed inset-0 z-[70] flex cursor-zoom-out items-center justify-center bg-black/85 p-6"
        @click="lightbox = false"
      >
        <img
          :src="cur?.image || detail.image_url"
          :alt="detail.name_en"
          class="max-h-full max-w-full rounded-[6px] shadow-2xl"
        />
        <p class="absolute bottom-4 left-1/2 -translate-x-1/2 text-xs text-faint">点击任意处关闭 · 当前面: {{ cur?.name_zh || cur?.name_en || detail.name_zh || detail.name_en }}</p>
      </div>
    </Teleport>

    <!-- 类似单卡弹窗(页面居中,按共同标签数排序) -->
    <Teleport to="body">
      <div
        v-if="similarOpen && detail"
        class="pointer-events-auto fixed inset-0 z-[65] flex items-center justify-center p-4"
      >
        <div class="absolute cursor-pointer inset-0 bg-black/60" @click="similarOpen = false"></div>
        <div class="relative flex max-h-[86vh] w-[54rem] max-w-full flex-col rounded-md border border-line bg-panel shadow-2xl">
          <div class="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
            <div class="min-w-0">
              <h3 class="font-display text-base font-semibold text-parch">
                类似单卡 · {{ detail.name_zh || detail.name_en }}
              </h3>
              <p class="mt-0.5 text-[10px] text-faint">
                按共同标签数排序 · 相似度 = 共同标签 / {{ similarNumTags || simTags.length }} 个标签 · 共 {{ similarTotal }} 张
              </p>
            </div>
            <button class="px-2 text-lg text-mute hover:text-gold" @click="similarOpen = false">✕</button>
          </div>

          <!-- 筛选栏:指挥官颜色 + 卡牌类型 -->
          <div class="space-y-1.5 border-b border-line px-4 py-2.5">
            <div class="flex items-center gap-2">
              <span class="w-14 shrink-0 text-[10px] tracking-[0.15em] text-faint">指挥官颜色</span>
              <div class="flex flex-wrap gap-1">
                <button
                  v-for="m in simColors"
                  :key="m.c"
                  class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
                  :class="simCi.includes(m.c) ? 'border-golddim bg-golddim/40 font-bold text-gold' : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
                  @click="toggleSimCi(m.c)"
                >{{ m.label }}</button>
                <button
                  class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
                  :class="simCiColorless ? 'border-golddim bg-golddim/40 font-bold text-gold' : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
                  title="未选颜色时:只显示无色牌 · 已选颜色时:无色牌始终包含(指挥官规则:无色可进任何套牌)"
                  @click="simCiColorless = !simCiColorless; reloadSimilar()"
                >无色</button>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="w-14 shrink-0 text-[10px] tracking-[0.15em] text-faint">卡牌类型</span>
              <div class="flex flex-wrap gap-1">
                <button
                  v-for="m in SIM_TYPES"
                  :key="m.t"
                  class="rounded-sm border px-2 py-0.5 text-[11px] transition-colors"
                  :class="simTypes.includes(m.t) ? 'border-golddim bg-golddim/40 font-bold text-gold' : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
                  @click="toggleSimType(m.t)"
                >{{ m.zh }}</button>
                <button
                  v-if="simFilterActive"
                  class="rounded-sm border border-line px-2 py-0.5 text-[11px] text-faint transition-colors hover:border-golddim hover:text-gold"
                  @click="clearSimFilters()"
                >清空筛选</button>
              </div>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto p-4">
            <p v-if="similarLoading && !similar.length" class="py-8 text-center text-xs text-faint">查询中…</p>
            <p v-else-if="similarError" class="py-8 text-center text-xs text-faint">{{ similarError }}</p>
            <p v-else-if="!similar.length" class="py-8 text-center text-xs text-faint">{{ simFilterActive ? '没有符合筛选条件的卡' : '暂无共同标签的卡' }}</p>
            <div v-else class="grid grid-cols-4 gap-3 sm:grid-cols-5 lg:grid-cols-6">
              <button
                v-for="c in similar"
                :key="c.oracle_id"
                class="group min-w-0 text-left"
                :title="c.shared_tags?.length ? `共同标签:${c.shared_tags.join(' · ')}` : ''"
                @click="similarOpen = false; openDetail(c.oracle_id)"
              >
                <div class="aspect-[63/88] w-full overflow-hidden rounded-[3px] bg-panel2">
                  <img
                    v-if="c.image_url"
                    :src="c.image_url"
                    :alt="c.name_en"
                    loading="lazy"
                    class="cardimg h-full w-full object-cover"
                    @load="e => e.target.classList.add('loaded')"
                  />
                  <div v-else class="flex h-full w-full items-center justify-center text-[10px] text-faint">无图</div>
                </div>
                <p class="mt-0.5 truncate text-[10px] text-mute transition-colors group-hover:text-gold">{{ c.name_zh || c.name_en }}</p>
                <!-- 相似度指标:百分比 + 共同标签数 + 迷你进度条 -->
                <div class="mt-0.5">
                  <div class="flex items-baseline justify-between font-num text-[9px]">
                    <span class="font-bold text-gold">{{ Math.round((c.similarity || 0) * 100) }}%</span>
                    <span class="text-faint">{{ c.shared }}/{{ similarNumTags }} 标签</span>
                  </div>
                  <div class="mt-0.5 h-1 overflow-hidden rounded-sm bg-panel2">
                    <div class="h-full rounded-sm bg-gold" :style="{ width: `${Math.round((c.similarity || 0) * 100)}%` }"></div>
                  </div>
                </div>
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5">
            <button
              class="text-[10px] text-faint underline-offset-2 transition-colors hover:text-gold hover:underline"
              @click="viewAllSimilar()"
            >在主列表查看全部 {{ similarTotal }} 张 →</button>
            <button
              v-if="similar.length < similarTotal"
              class="rounded-sm border border-line bg-panel2 px-3 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-gold disabled:opacity-50"
              :disabled="similarLoading"
              @click="loadSimilarPage(similarPage + 1)"
            >{{ similarLoading ? '加载中…' : '加载更多' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
