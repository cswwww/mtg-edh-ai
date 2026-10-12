<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { state } from '../store'

const props = defineProps({
  deck: { type: Object, required: true },
})
const emit = defineEmits(['close', 'detail'])

const STORAGE_PREFIX = 'mtg-deck-canvas:'
const STAGE_WIDTH = 3600
const STAGE_HEIGHT = 2400
const CARD_WIDTH = 150
const CARD_HEIGHT = 210
const TYPE_FILTERS = [
  { type: 'Creature', label: '生物' },
  { type: 'Sorcery', label: '法术' },
  { type: 'Instant', label: '瞬间' },
  { type: 'Enchantment', label: '结界' },
  { type: 'Artifact', label: '神器' },
  { type: 'Land', label: '地' },
  { type: 'Planeswalker', label: '鹏洛客' },
  { type: 'Battle', label: '战役' },
  { type: 'Kindred', label: '亲缘' },
  { type: 'Tribal', label: '部族' },
]
const cards = computed(() => props.deck.cards || [])
const query = ref('')
const selectedTypes = ref([])
const zoom = ref(1)
const tool = ref('select')
const elements = ref([])
const strokes = ref([])
const groups = ref([])
const selectedIds = ref([])
const storageError = ref('')
const failedCardImages = ref(new Set())
const stage = ref(null)
const viewport = ref(null)
const draftStroke = ref(null)
const selectionRect = ref(null)
const pointerAction = ref(null)
const cardContextMenu = ref(null)

const filteredCards = computed(() => {
  const value = query.value.trim().toLocaleLowerCase()
  return cards.value.filter((card) => {
    const matchesQuery = !value ||
      (card.name_zh || '').toLocaleLowerCase().includes(value) ||
      (card.name_en || '').toLocaleLowerCase().includes(value)
    const typeLine = card.type_line_en || ''
    const matchesType = !selectedTypes.value.length ||
      selectedTypes.value.some((type) => typeLine.includes(type))
    return matchesQuery && matchesType
  })
})
const deckTypeFilters = computed(() => TYPE_FILTERS.map((filter) => ({
  ...filter,
  count: cards.value.reduce((total, card) =>
    total + ((card.type_line_en || '').includes(filter.type) ? card.qty || 0 : 0), 0),
})).filter((filter) => filter.count > 0))
const groupViews = computed(() => groups.value.map((group) => {
  const memberElements = elements.value.filter((item) => group.memberIds.includes(item.id))
  const memberStrokes = strokes.value.filter((stroke) => group.memberIds.includes(stroke.id))
  const xs = memberElements.flatMap((item) => [item.x, item.x + (item.type === 'card' ? CARD_WIDTH : 190)])
  const ys = memberElements.flatMap((item) => [item.y, item.y + (item.type === 'card' ? CARD_HEIGHT : 90)])
  for (const stroke of memberStrokes) {
    xs.push(...stroke.points.map((point) => point.x))
    ys.push(...stroke.points.map((point) => point.y))
  }
  if (!xs.length) return null
  const left = Math.max(0, Math.min(...xs) - 8)
  const top = Math.max(0, Math.min(...ys) - 8)
  const right = Math.min(STAGE_WIDTH, Math.max(...xs) + 8)
  const bottom = Math.min(STAGE_HEIGHT, Math.max(...ys) + 8)
  return {
    ...group,
    left,
    top,
    width: right - left,
    height: bottom - top,
    selected: group.memberIds.every((id) => selectedIds.value.includes(id)),
  }
}).filter(Boolean))
const selectedGroupIds = computed(() => groups.value
  .filter((group) => group.memberIds.some((id) => selectedIds.value.includes(id)))
  .map((group) => group.id))
const canGroupSelection = computed(() => selectedIds.value.length >= 2)
const canUngroupSelection = computed(() => selectedGroupIds.value.length > 0)

function toggleType(type) {
  const index = selectedTypes.value.indexOf(type)
  if (index === -1) selectedTypes.value.push(type)
  else selectedTypes.value.splice(index, 1)
}

function persist() {
  try {
    localStorage.setItem(STORAGE_PREFIX + props.deck.id, JSON.stringify({
      elements: elements.value,
      strokes: strokes.value,
      groups: groups.value,
    }))
    storageError.value = ''
  } catch (error) {
    storageError.value = `保存画布失败: ${String(error)}`
  }
}

onMounted(() => {
  try {
    const stored = localStorage.getItem(STORAGE_PREFIX + props.deck.id)
    if (!stored) return
    const data = JSON.parse(stored)
    if (!Array.isArray(data.elements) || (!Array.isArray(data.strokes) && !Array.isArray(data.lines))) {
      throw new Error('画布存档格式无效')
    }
    const savedElements = data.elements.filter((item) =>
      item && typeof item.id === 'string' &&
      (item.type === 'card' || item.type === 'text') &&
      Number.isFinite(item.x) && Number.isFinite(item.y))
    let restoredMissingImages = false
    elements.value = savedElements.map((item) => {
      if (item.type !== 'card' || item.image) return item
      const card = cards.value.find((entry) =>
        (item.oracleId && entry.oracle_id === item.oracleId) ||
        item.name === entry.name_zh || item.name === entry.name_en)
      if (!card) return item
      restoredMissingImages = true
      return {
        ...item,
        oracleId: card.oracle_id,
        image: card.image_url || '',
        fallbackImage: normalizeFallbackImage(card.art_crop),
        imageFailed: false,
      }
    })
    const storedStrokes = data.strokes || data.lines
      .filter((line) => line && typeof line.id === 'string' &&
        [line.x1, line.y1, line.x2, line.y2].every(Number.isFinite))
      .map((line) => ({
        id: line.id,
        points: [{ x: line.x1, y: line.y1 }, { x: line.x2, y: line.y2 }],
      }))
    strokes.value = storedStrokes.filter((stroke) =>
      stroke && typeof stroke.id === 'string' &&
      Array.isArray(stroke.points) && stroke.points.length > 1 &&
      stroke.points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)))
    const validMemberIds = new Set([
      ...elements.value.map((item) => item.id),
      ...strokes.value.map((stroke) => stroke.id),
    ])
    groups.value = (Array.isArray(data.groups) ? data.groups : [])
      .filter((group) => group && typeof group.id === 'string' && Array.isArray(group.memberIds))
      .map((group) => ({
        ...group,
        name: typeof group.name === 'string' ? group.name : '未命名分组',
        memberIds: [...new Set(group.memberIds.filter((id) => validMemberIds.has(id)))],
      }))
      .filter((group) => group.memberIds.length >= 2)
    if (restoredMissingImages) persist()
  } catch (error) {
    storageError.value = `读取画布失败: ${String(error)}`
  }
})

function makeId() {
  return globalThis.crypto?.randomUUID?.() || `canvas-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function normalizeFallbackImage(url) {
  return (url || '').replace(/!default_art_crop(?=\?)/, '')
}

function stagePoint(event) {
  const rect = stage.value.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(STAGE_WIDTH, (event.clientX - rect.left) / zoom.value)),
    y: Math.max(0, Math.min(STAGE_HEIGHT, (event.clientY - rect.top) / zoom.value)),
  }
}

function addCard(card, x, y) {
  const item = {
    id: makeId(),
    type: 'card',
    x: Math.max(0, Math.min(STAGE_WIDTH - CARD_WIDTH, x)),
    y: Math.max(0, Math.min(STAGE_HEIGHT - CARD_HEIGHT, y)),
    oracleId: card.oracle_id || '',
    name: card.name_zh || card.name_en,
    image: card.image_url || card.image || '',
    fallbackImage: normalizeFallbackImage(card.art_crop || card.fallbackImage),
    imageFailed: false,
    qty: card.qty || 1,
  }
  elements.value.push(item)
  selectedIds.value = [item.id]
  persist()
}

function openCardContextMenu(event, item) {
  event.preventDefault()
  event.stopPropagation()
  const width = 160
  const height = 132
  cardContextMenu.value = {
    itemId: item.id,
    x: Math.max(8, Math.min(event.clientX, window.innerWidth - width - 8)),
    y: Math.max(8, Math.min(event.clientY, window.innerHeight - height - 8)),
  }
}

function copyContextCard() {
  const source = elements.value.find((item) => item.id === cardContextMenu.value?.itemId)
  if (!source) {
    cardContextMenu.value = null
    return
  }
  const copy = {
    ...source,
    id: makeId(),
    x: Math.min(STAGE_WIDTH - CARD_WIDTH, source.x + 24),
    y: Math.min(STAGE_HEIGHT - CARD_HEIGHT, source.y + 24),
    imageFailed: false,
  }
  elements.value.push(copy)
  selectedIds.value = [copy.id]
  cardContextMenu.value = null
  persist()
}

function deleteContextCard() {
  const itemId = cardContextMenu.value?.itemId
  if (!itemId) return
  elements.value = elements.value.filter((item) => item.id !== itemId)
  groups.value = groups.value
    .map((group) => ({ ...group, memberIds: group.memberIds.filter((id) => id !== itemId) }))
    .filter((group) => group.memberIds.length >= 2)
  selectedIds.value = selectedIds.value.filter((id) => id !== itemId)
  cardContextMenu.value = null
  persist()
}

function showContextCardDetail() {
  const item = elements.value.find((entry) => entry.id === cardContextMenu.value?.itemId)
  cardContextMenu.value = null
  if (!item) return
  const card = cards.value.find((entry) =>
    (item.oracleId && entry.oracle_id === item.oracleId) ||
    item.name === entry.name_zh || item.name === entry.name_en)
  const oracleId = item.oracleId || card?.oracle_id
  if (oracleId) emit('detail', oracleId)
}

function onDragStart(event, card) {
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('application/x-mtg-card', JSON.stringify({
    oracle_id: card.oracle_id,
    name: card.name_zh || card.name_en,
    name_zh: card.name_zh,
    name_en: card.name_en,
    image_url: card.image_url || '',
    art_crop: card.art_crop || '',
    qty: card.qty || 1,
  }))
}

function onImageError(item) {
  if (item.fallbackImage && item.image !== item.fallbackImage) {
    item.image = item.fallbackImage
    persist()
    return
  }
  item.imageFailed = true
}

function onSidebarImageError(card) {
  failedCardImages.value = new Set([...failedCardImages.value, card.oracle_id])
}

function onDrop(event) {
  event.preventDefault()
  const data = event.dataTransfer.getData('application/x-mtg-card')
  if (!data) return
  try {
    const point = stagePoint(event)
    addCard(JSON.parse(data), point.x - CARD_WIDTH / 2, point.y - CARD_HEIGHT / 2)
    tool.value = 'select'
  } catch (error) {
    storageError.value = `添加卡牌失败: ${String(error)}`
  }
}

function beginMove(event, ids) {
  const selected = new Set(ids)
  const movingElements = elements.value
    .filter((element) => selected.has(element.id))
    .map((element) => ({ id: element.id, x: element.x, y: element.y }))
  const movingStrokes = strokes.value
    .filter((stroke) => selected.has(stroke.id))
    .map((stroke) => ({ id: stroke.id, points: stroke.points.map((point) => ({ ...point })) }))
  const xs = movingElements.flatMap((item) => [item.x, item.x + (elements.value.find((element) => element.id === item.id)?.type === 'card' ? CARD_WIDTH : 190)])
  const ys = movingElements.flatMap((item) => [item.y, item.y + (elements.value.find((element) => element.id === item.id)?.type === 'card' ? CARD_HEIGHT : 90)])
  for (const stroke of movingStrokes) {
    xs.push(...stroke.points.map((point) => point.x))
    ys.push(...stroke.points.map((point) => point.y))
  }
  pointerAction.value = {
    type: 'move',
    start: stagePoint(event),
    elements: movingElements,
    strokes: movingStrokes,
    bounds: { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) },
  }
  event.currentTarget.setPointerCapture(event.pointerId)
}

function startNodeDrag(event, item) {
  if (tool.value !== 'select' || event.button !== 0) return
  event.preventDefault()
  event.stopPropagation()
  if (!selectedIds.value.includes(item.id)) selectedIds.value = [item.id]
  beginMove(event, selectedIds.value)
}

function startGroupDrag(event, group) {
  event.preventDefault()
  event.stopPropagation()
  selectedIds.value = [...group.memberIds]
  beginMove(event, group.memberIds)
}

function groupSelection() {
  const memberIds = new Set(selectedIds.value)
  for (const group of groups.value) {
    if (group.memberIds.some((id) => memberIds.has(id))) {
      group.memberIds.forEach((id) => memberIds.add(id))
    }
  }
  const uniqueIds = [...memberIds]
  if (uniqueIds.length < 2) return
  const groupedIds = new Set(uniqueIds)
  groups.value = groups.value.filter((group) =>
    !group.memberIds.some((id) => groupedIds.has(id)))
  groups.value.push({ id: makeId(), name: '新建分组', memberIds: uniqueIds })
  selectedIds.value = uniqueIds
  persist()
}

function ungroupSelection() {
  const groupedIds = new Set(selectedGroupIds.value)
  if (!groupedIds.size) return
  groups.value = groups.value.filter((group) => !groupedIds.has(group.id))
  persist()
}

function renameGroup(group, event) {
  const savedGroup = groups.value.find((item) => item.id === group.id)
  if (!savedGroup) return
  savedGroup.name = event.target.value
  persist()
}

function rectFromPoints(a, b) {
  return {
    left: Math.min(a.x, b.x),
    top: Math.min(a.y, b.y),
    right: Math.max(a.x, b.x),
    bottom: Math.max(a.y, b.y),
  }
}

function intersects(a, b) {
  return a.left <= b.right && a.right >= b.left &&
    a.top <= b.bottom && a.bottom >= b.top
}

function selectInRect(rect) {
  const ids = elements.value.filter((item) => {
    const width = item.type === 'card' ? CARD_WIDTH : 190
    const height = item.type === 'card' ? CARD_HEIGHT : 90
    return intersects(rect, { left: item.x, top: item.y, right: item.x + width, bottom: item.y + height })
  }).map((item) => item.id)
  for (const stroke of strokes.value) {
    const xs = stroke.points.map((point) => point.x)
    const ys = stroke.points.map((point) => point.y)
    if (intersects(rect, {
      left: Math.min(...xs),
      top: Math.min(...ys),
      right: Math.max(...xs),
      bottom: Math.max(...ys),
    })) ids.push(stroke.id)
  }
  selectedIds.value = ids
}

function onStagePointerDown(event) {
  if (event.button !== 0) return
  const point = stagePoint(event)
  if (tool.value === 'pen') {
    draftStroke.value = { id: makeId(), points: [point] }
    event.currentTarget.setPointerCapture(event.pointerId)
  } else if (tool.value === 'text') {
    const item = { id: makeId(), type: 'text', x: point.x, y: point.y, text: '' }
    elements.value.push(item)
    selectedIds.value = [item.id]
    tool.value = 'select'
    persist()
    nextTick(() => stage.value?.querySelector(`[data-text-id="${item.id}"]`)?.focus())
  } else {
    const hadSelection = selectedIds.value.length > 0
    selectedIds.value = []
    if (!hadSelection) {
      selectionRect.value = { x1: point.x, y1: point.y, x2: point.x, y2: point.y }
      pointerAction.value = { type: 'marquee', start: point }
      event.currentTarget.setPointerCapture(event.pointerId)
    }
  }
}

function onStagePointerMove(event) {
  const point = stagePoint(event)
  if (draftStroke.value) {
    const points = draftStroke.value.points
    const previous = points[points.length - 1]
    if (Math.hypot(point.x - previous.x, point.y - previous.y) >= 2) points.push(point)
    return
  }
  if (!pointerAction.value) return
  if (pointerAction.value.type === 'marquee') {
    selectionRect.value.x2 = point.x
    selectionRect.value.y2 = point.y
    selectInRect(rectFromPoints(pointerAction.value.start, point))
    return
  }
  const bounds = pointerAction.value.bounds
  const dx = Math.max(-bounds.left, Math.min(STAGE_WIDTH - bounds.right,
    point.x - pointerAction.value.start.x))
  const dy = Math.max(-bounds.top, Math.min(STAGE_HEIGHT - bounds.bottom,
    point.y - pointerAction.value.start.y))
  for (const origin of pointerAction.value.elements) {
    const item = elements.value.find((element) => element.id === origin.id)
    if (!item) continue
    item.x = origin.x + dx
    item.y = origin.y + dy
  }
  for (const origin of pointerAction.value.strokes) {
    const stroke = strokes.value.find((item) => item.id === origin.id)
    if (!stroke) continue
    stroke.points = origin.points.map((originPoint) => ({
      x: Math.max(0, Math.min(STAGE_WIDTH, originPoint.x + dx)),
      y: Math.max(0, Math.min(STAGE_HEIGHT, originPoint.y + dy)),
    }))
  }
}

function onStagePointerUp() {
  if (draftStroke.value) {
    if (draftStroke.value.points.length > 1) {
      strokes.value.push(draftStroke.value)
      persist()
    }
    draftStroke.value = null
  }
  if (pointerAction.value) {
    const wasMoving = pointerAction.value.type === 'move'
    selectionRect.value = null
    pointerAction.value = null
    if (wasMoving) persist()
  }
}

function onStrokePointerDown(event, stroke) {
  if (tool.value !== 'select') return
  event.preventDefault()
  event.stopPropagation()
  if (!selectedIds.value.includes(stroke.id)) selectedIds.value = [stroke.id]
  beginMove(event, selectedIds.value)
}

function onElementClick(item) {
  selectedIds.value = [item.id]
}

function updateText(item, event) {
  item.text = event.target.value
  persist()
}

function deleteSelected() {
  if (!selectedIds.value.length) return
  const selected = new Set(selectedIds.value)
  elements.value = elements.value.filter((item) => !selected.has(item.id))
  strokes.value = strokes.value.filter((stroke) => !selected.has(stroke.id))
  groups.value = groups.value
    .map((group) => ({ ...group, memberIds: group.memberIds.filter((id) => !selected.has(id)) }))
    .filter((group) => group.memberIds.length >= 2)
  selectedIds.value = []
  persist()
}

function clearCanvas() {
  if (!elements.value.length && !strokes.value.length) return
  if (!window.confirm('确定清空这张画布吗？')) return
  elements.value = []
  strokes.value = []
  groups.value = []
  selectedIds.value = []
  persist()
}

function setZoom(value) {
  const next = Math.max(0.4, Math.min(1.5, value))
  if (!viewport.value) {
    zoom.value = next
    return
  }
  const centerX = (viewport.value.scrollLeft + viewport.value.clientWidth / 2) / zoom.value
  const centerY = (viewport.value.scrollTop + viewport.value.clientHeight / 2) / zoom.value
  zoom.value = next
  requestAnimationFrame(() => {
    viewport.value.scrollLeft = centerX * next - viewport.value.clientWidth / 2
    viewport.value.scrollTop = centerY * next - viewport.value.clientHeight / 2
  })
}

</script>

<template>
  <div
    class="fixed inset-0 flex min-h-0 bg-ink text-parch"
    :class="state.detailId ? 'z-40' : 'z-[90]'"
    @click="cardContextMenu = null"
    @keydown.esc="cardContextMenu = null"
  >
    <aside class="flex w-64 shrink-0 flex-col border-r border-line bg-panel sm:w-72">
      <div class="border-b border-line p-3">
        <div class="flex items-center gap-2">
          <button
            class="rounded-sm border border-line bg-panel2 px-2 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-parch"
            @click="emit('close')"
          >← 返回牌表</button>
          <h2 class="min-w-0 flex-1 truncate font-display text-sm font-bold">{{ deck.name }}</h2>
        </div>
        <input
          v-model="query"
          type="search"
          class="mt-3 w-full rounded-sm border border-line bg-panel2 px-2.5 py-2 text-xs text-parch outline-none placeholder:text-faint focus:border-golddim"
          placeholder="筛选牌表中的卡牌"
        />
        <div v-if="deckTypeFilters.length" class="mt-3">
          <div class="flex items-center justify-between">
            <p class="text-[10px] tracking-widest text-faint">类型筛选</p>
            <button
              v-if="selectedTypes.length"
              class="text-[10px] text-faint transition-colors hover:text-gold"
              @click="selectedTypes = []"
            >清空</button>
          </div>
          <div class="mt-1.5 flex flex-wrap gap-1">
            <button
              v-for="filter in deckTypeFilters"
              :key="filter.type"
              class="rounded-sm border px-1.5 py-1 text-[10px] transition-colors"
              :class="selectedTypes.includes(filter.type)
                ? 'border-golddim bg-golddim/40 font-bold text-gold'
                : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'"
              :aria-pressed="selectedTypes.includes(filter.type)"
              @click="toggleType(filter.type)"
            >{{ filter.label }} <span class="font-num text-faint">{{ filter.count }}</span></button>
          </div>
        </div>
        <p class="mt-2 text-[10px] text-faint">拖动卡牌到右侧画布 · {{ cards.length }} 种卡</p>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <button
          v-for="card in filteredCards"
          :key="card.oracle_id"
          class="mb-1.5 flex w-full items-center gap-2 rounded-sm border border-line bg-panel2 p-1.5 text-left transition-colors hover:border-golddim"
          draggable="true"
          @dragstart="onDragStart($event, card)"
          @click="addCard(card, 100 + (elements.length % 6) * 24, 100 + (elements.length % 6) * 24)"
        >
          <img
            v-if="card.image_url && !failedCardImages.has(card.oracle_id)"
            :src="card.image_url"
            :alt="card.name_en"
            loading="lazy"
            class="h-14 w-10 shrink-0 rounded-sm object-cover"
            @error="onSidebarImageError(card)"
          />
          <div v-else class="flex h-14 w-10 shrink-0 items-center justify-center rounded-sm bg-ink text-[9px] text-faint">
            {{ failedCardImages.has(card.oracle_id) ? '卡图不可用' : '无图' }}
          </div>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-[11px] font-medium text-parch">{{ card.name_zh || card.name_en }}</span>
            <span v-if="card.name_zh" class="block truncate text-[9px] text-faint">{{ card.name_en }}</span>
            <span class="mt-1 block font-num text-[9px] text-mute">×{{ card.qty }}</span>
          </span>
        </button>
        <p v-if="!filteredCards.length" class="px-2 py-8 text-center text-xs text-faint">没有匹配的卡牌</p>
      </div>
    </aside>

    <section class="flex min-w-0 flex-1 flex-col">
      <header class="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-3 py-2">
        <span class="mr-1 text-xs font-bold text-parch">画布</span>
        <button
          class="rounded-sm border px-2.5 py-1 text-[11px] transition-colors"
          :class="tool === 'select' ? 'border-golddim bg-golddim/40 text-gold' : 'border-line bg-panel2 text-mute hover:text-parch'"
          @click="tool = 'select'"
        >选择</button>
        <button
          class="rounded-sm border border-line bg-panel2 px-2.5 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-parch disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canGroupSelection"
          @click="groupSelection"
        >组合</button>
        <button
          class="rounded-sm border border-line bg-panel2 px-2.5 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-parch disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canUngroupSelection"
          @click="ungroupSelection"
        >取消组合</button>
        <button
          class="rounded-sm border px-2.5 py-1 text-[11px] transition-colors"
          :class="tool === 'text' ? 'border-golddim bg-golddim/40 text-gold' : 'border-line bg-panel2 text-mute hover:text-parch'"
          @click="tool = 'text'"
        >＋ 文本框</button>
        <button
          class="rounded-sm border px-2.5 py-1 text-[11px] transition-colors"
          :class="tool === 'pen' ? 'border-golddim bg-golddim/40 text-gold' : 'border-line bg-panel2 text-mute hover:text-parch'"
          @click="tool = 'pen'"
        >✎ 画笔</button>
        <button
          class="rounded-sm border border-line bg-panel2 px-2.5 py-1 text-[11px] text-mute transition-colors hover:border-golddim hover:text-parch disabled:opacity-40"
          :disabled="!selectedIds.length"
          @click="deleteSelected"
        >删除选中{{ selectedIds.length ? ` · ${selectedIds.length}` : '' }}</button>
        <button
          class="rounded-sm border border-line bg-panel2 px-2.5 py-1 text-[11px] text-mute transition-colors hover:border-red-700 hover:text-red-300"
          @click="clearCanvas"
        >清空</button>
        <span class="flex-1"></span>
        <button class="rounded-sm border border-line bg-panel2 px-2 py-1 text-xs text-mute hover:text-parch" @click="setZoom(zoom - 0.1)">−</button>
        <span class="min-w-10 text-center font-num text-[10px] text-mute">{{ Math.round(zoom * 100) }}%</span>
        <button class="rounded-sm border border-line bg-panel2 px-2 py-1 text-xs text-mute hover:text-parch" @click="setZoom(zoom + 0.1)">＋</button>
        <button class="rounded-sm border border-line bg-panel2 px-2 py-1 text-[10px] text-mute hover:text-parch" @click="setZoom(1)">重置缩放</button>
      </header>
      <p v-if="storageError" class="border-b border-red-900 bg-red-950/40 px-3 py-1.5 text-[10px] text-red-300">{{ storageError }}</p>
      <div
        ref="viewport"
        class="min-h-0 flex-1 overflow-auto bg-[#171512]"
        @dragover.prevent
        @drop="onDrop"
      >
        <div
          class="relative m-8 shrink-0"
          :style="{ width: `${STAGE_WIDTH * zoom}px`, height: `${STAGE_HEIGHT * zoom}px` }"
        >
          <div
            ref="stage"
            class="absolute left-0 top-0 overflow-hidden border border-[#51483b] bg-[#211e19]"
            :class="tool === 'pen' || selectionRect ? 'cursor-crosshair' : tool === 'text' ? 'cursor-text' : 'cursor-default'"
            :style="{
              width: `${STAGE_WIDTH}px`,
              height: `${STAGE_HEIGHT}px`,
              transform: `scale(${zoom})`,
              transformOrigin: 'top left',
              backgroundImage: 'radial-gradient(#51483b 1px, transparent 1px)',
              backgroundSize: '24px 24px',
            }"
            @pointerdown="onStagePointerDown"
            @pointermove="onStagePointerMove"
            @pointerup="onStagePointerUp"
            @pointercancel="onStagePointerUp"
          >
            <svg class="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
              <polyline
                v-for="stroke in strokes"
                :key="stroke.id"
                :points="stroke.points.map((point) => `${point.x},${point.y}`).join(' ')"
                fill="none"
                stroke="#d4a437"
                stroke-width="4"
                stroke-linecap="round"
                stroke-linejoin="round"
                :class="selectedIds.includes(stroke.id) ? 'opacity-100' : 'opacity-80'"
                :stroke-width="selectedIds.includes(stroke.id) ? 6 : 4"
                style="pointer-events: stroke; cursor: pointer"
                @pointerdown="onStrokePointerDown($event, stroke)"
              />
              <polyline
                v-if="draftStroke"
                :points="draftStroke.points.map((point) => `${point.x},${point.y}`).join(' ')"
                fill="none"
                stroke="#d4a437"
                stroke-width="4"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-dasharray="8 6"
              />
            </svg>
            <div
              v-if="selectionRect"
              class="pointer-events-none absolute border border-sky-300 bg-sky-400/15"
              :style="{
                left: `${Math.min(selectionRect.x1, selectionRect.x2)}px`,
                top: `${Math.min(selectionRect.y1, selectionRect.y2)}px`,
                width: `${Math.abs(selectionRect.x2 - selectionRect.x1)}px`,
                height: `${Math.abs(selectionRect.y2 - selectionRect.y1)}px`,
              }"
            ></div>
            <div
              v-for="item in elements"
              :key="item.id"
              class="absolute select-none"
              :class="[
                item.type === 'card' ? 'h-[210px] w-[150px]' : 'min-h-10 w-48',
                selectedIds.includes(item.id) ? 'ring-2 ring-gold' : '',
                tool === 'select' ? 'cursor-grab active:cursor-grabbing' : '',
              ]"
              :style="{ left: `${item.x}px`, top: `${item.y}px` }"
              @pointerdown="startNodeDrag($event, item)"
              @click.stop="onElementClick(item)"
              @contextmenu="item.type === 'card' ? openCardContextMenu($event, item) : null"
            >
              <template v-if="item.type === 'card'">
                <img
                  v-if="item.image && !item.imageFailed"
                  :src="item.image"
                  :alt="item.name"
                  draggable="false"
                  class="h-full w-full rounded-md object-cover shadow-xl"
                  @error="onImageError(item)"
                />
                <div v-else class="flex h-full w-full flex-col items-center justify-center rounded-md border border-line bg-panel2 p-2 text-center text-xs text-mute">
                  <span>{{ item.name }}</span>
                  <span v-if="item.imageFailed" class="mt-1 text-[9px] text-faint">卡图暂不可用</span>
                  <span v-else class="mt-1 text-[9px] text-faint">无卡图</span>
                </div>
                <span class="absolute bottom-1 right-1 rounded-sm bg-ink/85 px-1.5 py-0.5 text-[9px] text-parch">{{ item.name }} ×{{ item.qty }}</span>
              </template>
              <textarea
                v-else
                :data-text-id="item.id"
                :value="item.text"
                rows="3"
                spellcheck="false"
                class="min-h-10 w-full resize rounded-sm border border-golddim/70 bg-ink/80 p-2 text-sm leading-relaxed text-parch outline-none placeholder:text-faint focus:border-gold"
                placeholder="输入文本…"
                @pointerdown.stop
                @input="updateText(item, $event)"
              />
              <div
                v-if="item.type === 'text' && selectedIds.includes(item.id)"
                class="cursor-grab border-t border-golddim/40 bg-panel2/80 px-2 py-0.5 text-[9px] text-faint active:cursor-grabbing"
                @pointerdown="startNodeDrag($event, item)"
              >拖动文本框</div>
            </div>
            <div
              v-for="group in groupViews"
              :key="group.id"
              class="pointer-events-none absolute border-2 border-dashed"
              :class="group.selected ? 'border-gold/80' : 'border-golddim/50'"
              :style="{
                left: `${group.left}px`,
                top: `${group.top}px`,
                width: `${group.width}px`,
                height: `${group.height}px`,
              }"
            >
              <div
                class="pointer-events-none absolute left-0 flex max-w-[320px] items-center gap-1"
                :class="group.top < 36 ? 'top-1' : 'bottom-full mb-1'"
              >
                <input
                  :value="group.name"
                  :aria-label="`编辑分组名称：${group.name}`"
                  class="pointer-events-auto w-36 min-w-0 rounded-sm border border-golddim bg-ink/95 px-2 py-1 text-[11px] font-bold text-gold outline-none focus:border-gold"
                  @pointerdown.stop
                  @focus="selectedIds = [...group.memberIds]"
                  @input="renameGroup(group, $event)"
                />
                <button
                  class="pointer-events-auto cursor-grab rounded-sm border border-line bg-panel px-1.5 py-1 text-[10px] text-mute hover:text-parch active:cursor-grabbing"
                  :aria-label="`拖动分组：${group.name}`"
                  title="拖动整个分组"
                  @pointerdown="startGroupDrag($event, group)"
                >⠿</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <footer class="flex items-center justify-between border-t border-line bg-panel px-3 py-1.5 text-[10px] text-faint">
        <span>画布内容自动保存在此浏览器 · 拖动空白区域可用滚动条浏览大画布</span>
        <span>{{ elements.length }} 个元素 · {{ strokes.length }} 条笔迹 · 已选 {{ selectedIds.length }}</span>
      </footer>
    </section>
    <div
      v-if="cardContextMenu"
      class="fixed z-[100] w-40 overflow-hidden rounded-sm border border-line bg-panel py-1 shadow-2xl"
      :style="{ left: `${cardContextMenu.x}px`, top: `${cardContextMenu.y}px` }"
      role="menu"
      aria-label="卡牌操作"
      @click.stop
    >
      <button
        class="block w-full px-3 py-2 text-left text-xs text-mute transition-colors hover:bg-panel2 hover:text-parch"
        role="menuitem"
        @click="deleteContextCard"
      >删除</button>
      <button
        class="block w-full px-3 py-2 text-left text-xs text-mute transition-colors hover:bg-panel2 hover:text-parch"
        role="menuitem"
        @click="copyContextCard"
      >复制</button>
      <button
        class="block w-full px-3 py-2 text-left text-xs text-mute transition-colors hover:bg-panel2 hover:text-parch"
        role="menuitem"
        @click="showContextCardDetail"
      >详情</button>
    </div>
  </div>
</template>
