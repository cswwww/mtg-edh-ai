import { reactive, ref, watch } from 'vue'

const SAVED_SIZE = localStorage.getItem('mtg-view-size')
const VALID_SIZES = ['S', 'M', 'L', 'LIST']

export const MANA = {
  W: { label: '白', color: '#ece5ce', ink: '#191715' },
  U: { label: '蓝', color: '#5ba4cf', ink: '#191715' },
  B: { label: '黑', color: '#8c7cae', ink: '#f4ecd8' },
  R: { label: '红', color: '#d95f4e', ink: '#f4ecd8' },
  G: { label: '绿', color: '#6ebf71', ink: '#191715' },
}

export const state = reactive({
  q: '',
  mode: 'vector', // vector | fts
  // 卡牌颜色:默认精确匹配;ccExclude=不含未选(子集);ccPartial=部分匹配(交集)
  cardColors: [],
  ccColorless: false,
  ccMulti: false,
  ccExclude: false,
  ccPartial: false,
  // 指挥官标识色:标识色 ⊆ 所选
  ciColors: [],
  ciColorless: false,
  cmcSel: [],     // 总法术力多选,11 表示 11+
  cmcMin: null,
  cmcMax: null,
  types: [],     // 卡牌类型多选,交集(如 生物+神器 = 神器生物)
  rarities: [],   // 稀有度多选(并集)
  commander: true,
  tags: [],       // 标签筛选(复选,交集/并集由 tagMode 决定)
  tagMode: 'and', // and=交集 | or=并集
  sort: 'rel',
  page: 1,
  pageSize: SAVED_SIZE === 'LIST' ? 120 : 60,
  size: VALID_SIZES.includes(SAVED_SIZE) ? SAVED_SIZE : 'M',  // S | M | L | LIST,持久化到 localStorage
  items: [],
  total: 0,
  loading: false,
  error: '',
  detailId: null,
  typeDirect: null,   // 主搜索栏触发"分词类型直搜"时的 token 列表
  meta: null,
  slangOpen: false,
  tagPickerOpen: false,
  typeModalOpen: false,
})

// 视图尺寸持久化
watch(() => state.size, (v) => {
  localStorage.setItem('mtg-view-size', v)
})

let seq = 0

async function fetchJson(url, tries = 4) {
  let last
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url)
      if (r.ok) return await r.json()
      last = new Error('HTTP ' + r.status)
    } catch (e) {
      last = e
    }
    await new Promise((res) => setTimeout(res, 1500))
  }
  throw last
}

export async function search(resetPage = true) {
  if (resetPage) state.page = 1
  const my = ++seq
  state.loading = true
  state.error = ''
  const p = new URLSearchParams()
  p.set('q', state.q)
  p.set('mode', state.mode)
  if (state.cardColors.length || state.ccColorless) {
    p.set('cc_colors', state.cardColors.join(','))
    if (state.ccColorless) p.set('cc_colorless', '1')
    if (state.ccMulti) p.set('cc_multi', '1')
    if (state.ccExclude) p.set('cc_exclude', '1')
    if (state.ccPartial) p.set('cc_partial', '1')
  }
  if (state.ciColors.length || state.ciColorless) {
    p.set('ci_colors', state.ciColors.join(','))
    if (state.ciColorless) p.set('ci_colorless', '1')
  }
  if (state.cmcSel.length) p.set('cmc_sel', state.cmcSel.map(v => v === '11+' ? '11' : v).join(','))
  if (state.cmcMin !== null && state.cmcMin !== '') p.set('cmc_min', state.cmcMin)
  if (state.cmcMax !== null && state.cmcMax !== '') p.set('cmc_max', state.cmcMax)
  if (state.types.length) p.set('type', state.types.join(','))
  if (state.rarities.length) p.set('rarity', state.rarities.join(','))
  if (state.commander) p.set('commander', '1')
  if (state.tags.length) {
    p.set('tags', state.tags.join(','))
    p.set('tag_mode', state.tagMode)
  }
  p.set('sort', state.sort)
  p.set('page', state.page)
  p.set('page_size', state.pageSize)
  try {
    const d = await fetchJson('/api/search?' + p.toString())
    if (my !== seq) return // 过期响应
    state.items = d.items
    state.total = d.total
    state.typeDirect = d.type_direct || null
  } catch (e) {
    if (my === seq) state.error = String(e)
  } finally {
    if (my === seq) state.loading = false
  }
}

export function nextPage() {
  state.page++
  search(false)
}
export function prevPage() {
  if (state.page > 1) {
    state.page--
    search(false)
  }
}

export async function loadMeta() {
  try {
    state.meta = await fetchJson('/api/meta')
  } catch {}
}

export const detail = ref(null)

// 无图列表视图列布局(表头与 CardRow 共用):名称/类型/费用/标签/稀有度/EDHREC
export const LIST_COLS =
  'minmax(12rem,1.8fr) minmax(9rem,1.2fr) 6rem minmax(8rem,1fr) 4.5rem 5rem'
export async function openDetail(oracleId) {
  state.detailId = oracleId
  detail.value = null
  try {
    const r = await fetchJson('/api/card/' + oracleId)
    detail.value = r
  } catch {}
}
export function closeDetail() {
  state.detailId = null
  detail.value = null
}
