<script setup>
import { computed, ref, watch } from 'vue'
import { detail, closeDetail, state } from '../store'
import ManaText from './ManaText.vue'

const faceIdx = ref(0)
const showEnText = ref(false)
watch(() => detail.value?.oracle_id, () => {
  faceIdx.value = 0
  showEnText.value = false
  lightbox.value = false
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

// 卡图大图查看器
const lightbox = ref(false)
watch(lightbox, v => { document.body.style.overflow = v ? 'hidden' : '' })

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
// 是否有任何 AI 内容
const hasAiMeta = computed(() => {
  const d = detail.value
  if (!d) return false
  return !!(
    d.ai_desc ||
    d.ai_deck_role?.length ||
    d.ai_strategy?.length ||
    d.ai_countermeta?.answers?.length ||
    d.ai_countermeta?.weak_to?.length ||
    (d.ai_phase && d.ai_phase !== 'any') ||
    d.ai_theme_keywords?.length
  )
})

// AI 枚举值 → 中文显示
const roleZh = {
  ramp: '法术力加速', card_advantage: '抓牌优势', removal: '去除',
  wincon: '致胜手段', protection: '保护', combo: '组合技组件',
  tutor: '导师', card_selection: '手牌筛选', recursion: '坟场利用',
  mana_rock: '法术力资源', token: '铺场', finisher: '终结技',
  counter: '反击', draw_engine: '抓牌引擎', threat: '战场威胁',
}
const strategyZh = {
  tokens: '衍生物', aristocrats: '贵族牺牲', reanimator: '复生',
  voltron: '指挥官武装', lifegain: '回血', mill: '磨牌',
  control: '控制', combo: '组合技', stax: '资源锁控',
  spellslinger: '法术狂', '+1+1_counters': '指示物',
  sacrifice: '牺牲', blink: '闪现', flicker: '闪烁',
  treasures: '珍宝', artifact: '神器', enchantress: '结界',
  graveyard: '坟场', burn: '直伤', anthem: '群体增益', evasion: '穿透',
}
const phaseZh = {
  early: '前期', mid: '中盘', late: '终盘', any: '通用',
}
const counterZh = {
  hexproof: '辟邪生物', evasion: '穿透生物', planeswalker: '鹏洛客',
  artifact: '神器', enchantment: '结界', graveyard: '坟场',
  commander: '指挥官', token: '衍生物', aristocrat: '贵族牺牲',
  flyer: '飞行生物', indestructible: '不灭生物',
  high_cost_threat: '高费威胁', tapped_creature: '横置生物',
  mass_removal: '扫场', counter_spell: '反击咒语',
  graveyard_hate: '坟场仇恨', artifact_hate: '神器破坏',
  enchantment_hate: '结界破坏', trample: '践踏生物', lifegain: '回血',
  protection_from_color: '单色保护', tutor_hate: '反导师',
}
</script>

<template>
  <div v-if="detail || true" class="pointer-events-none fixed inset-0 z-50">
    <div
      class="absolute inset-0 bg-black/50 transition-opacity"
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
            <p class="mb-1.5 text-[10px] tracking-[0.2em] text-faint">SCRYFALL TAGGER · 社区标签</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="t in detail.sf_tags"
                :key="t"
                :title="t"
                class="rounded-sm border border-line bg-panel2 px-1.5 py-0.5 text-[10px] text-mute"
              >{{ state.meta?.tagdict?.[t] || t }}</span>
            </div>
          </div>

          <!-- AI 元数据(LLM 生成的结构化字段) -->
          <div v-if="hasAiMeta" class="mt-5">
            <p class="mb-1.5 text-[10px] tracking-[0.2em] text-faint">AI · 卡牌元数据</p>

            <!-- 功能定位 -->
            <div v-if="detail.ai_desc" class="border-l-2 border-golddim pl-3 text-xs text-parch">
              <p class="mb-1 text-[10px] tracking-[0.2em] text-faint">功能定位</p>
              <p>{{ detail.ai_desc }}</p>
            </div>

            <!-- 卡组角色 + 策略主题 -->
            <div v-if="detail.ai_deck_role?.length || detail.ai_strategy?.length" class="mt-3">
              <p class="mb-1 text-[10px] tracking-[0.2em] text-faint">卡组角色 / 策略主题</p>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="r in detail.ai_deck_role || []"
                  :key="'r-' + r"
                  :title="r"
                  class="rounded-sm border border-golddim/60 bg-golddim/15 px-1.5 py-0.5 text-[10px] text-gold"
                >{{ roleZh[r] || r }}</span>
                <span
                  v-for="s in detail.ai_strategy || []"
                  :key="'s-' + s"
                  :title="s"
                  class="rounded-sm border border-line bg-panel2 px-1.5 py-0.5 text-[10px] text-mute"
                >{{ strategyZh[s] || s }}</span>
                <span
                  v-if="detail.ai_phase && detail.ai_phase !== 'any'"
                  :title="'phase: ' + detail.ai_phase"
                  class="ml-1 rounded-sm border border-line bg-panel2 px-1.5 py-0.5 text-[10px] tracking-wider text-faint"
                >{{ phaseZh[detail.ai_phase] || detail.ai_phase }}</span>
              </div>
            </div>

            <!-- 反制 meta:克 / 怕 -->
            <div
              v-if="detail.ai_countermeta?.answers?.length || detail.ai_countermeta?.weak_to?.length"
              class="mt-3"
            >
              <p class="mb-1 text-[10px] tracking-[0.2em] text-faint">反制关系</p>
              <div class="space-y-1 text-[11px]">
                <p v-if="detail.ai_countermeta.answers?.length" class="flex flex-wrap items-baseline gap-1.5">
                  <span class="shrink-0 rounded-sm bg-emerald/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-emerald">克</span>
                  <span class="text-parch">{{ detail.ai_countermeta.answers.map(c => counterZh[c] || c).join('、') }}</span>
                </p>
                <p v-if="detail.ai_countermeta.weak_to?.length" class="flex flex-wrap items-baseline gap-1.5">
                  <span class="shrink-0 rounded-sm bg-rose/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-rose">怕</span>
                  <span class="text-parch">{{ detail.ai_countermeta.weak_to.map(c => counterZh[c] || c).join('、') }}</span>
                </p>
              </div>
            </div>

            <!-- 用户俗称 / 联想词 -->
            <div v-if="detail.ai_theme_keywords?.length" class="mt-3">
              <p class="mb-1 text-[10px] tracking-[0.2em] text-faint">用户俗称 / 联想词</p>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="k in detail.ai_theme_keywords"
                  :key="k"
                  class="rounded-sm border border-line bg-panel2 px-1.5 py-0.5 text-[10px] text-mute"
                >{{ k }}</span>
              </div>
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
  </div>
</template>
