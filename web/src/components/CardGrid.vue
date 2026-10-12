<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { state, nextPage, prevPage, search, LIST_COLS } from '../store'
import CardTile from './CardTile.vue'
import CardRow from './CardRow.vue'
import CardTip from './CardTip.vue'

const HEADERS = ['名称', '类型', '费用', '标签', '稀有度', 'EDHREC']

const SIZES = [
  { v: 'S', t: '小' },
  { v: 'M', t: '中' },
  { v: 'L', t: '大' },
  { v: 'LIST', t: '无图' },
]
const cols = computed(() => ({ S: 8, M: 6, L: 4 }[state.size] || 6))
const isList = computed(() => state.size === 'LIST')
const totalPages = computed(() => Math.max(1, Math.ceil(state.total / state.pageSize)))
const contextMenu = ref(null)
const contextMenuElement = ref(null)
const contextMenuPosition = ref({ x: 0, y: 0 })
const copyStatus = ref('')
const cardTip = ref(null)

function setSize(v) {
  state.size = v
  state.pageSize = v === 'LIST' ? 120 : 60
  search(false)
}

async function openCardContextMenu(card, event) {
  event.preventDefault()
  cardTip.value?.hide()
  contextMenu.value = card
  copyStatus.value = ''
  contextMenuPosition.value = { x: event.clientX, y: event.clientY }
  await nextTick()
  const bounds = contextMenuElement.value?.getBoundingClientRect()
  if (!bounds) return
  contextMenuPosition.value = {
    x: Math.max(8, Math.min(event.clientX, window.innerWidth - bounds.width - 8)),
    y: Math.max(8, Math.min(event.clientY, window.innerHeight - bounds.height - 8)),
  }
}

function showCardTip(event, card) {
  cardTip.value?.show(event, card)
}

function moveCardTip(event) {
  cardTip.value?.move(event)
}

function hideCardTip() {
  cardTip.value?.hide()
}

function closeCardContextMenu() {
  contextMenu.value = null
  copyStatus.value = ''
}

function onWindowPointerDown(event) {
  if (!contextMenuElement.value?.contains(event.target)) closeCardContextMenu()
}

function onWindowKeyDown(event) {
  if (event.key === 'Escape') closeCardContextMenu()
}

async function copyCardName(value, label) {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    copyStatus.value = `${label}已复制`
  } catch (error) {
    console.error('复制卡牌名称失败', error)
    copyStatus.value = '复制失败，请检查浏览器剪贴板权限'
  }
}

function addTagToFilter(tag) {
  if (!state.tags.includes(tag)) {
    state.tags.push(tag)
    search()
  }
  closeCardContextMenu()
}

onMounted(() => {
  window.addEventListener('pointerdown', onWindowPointerDown)
  window.addEventListener('keydown', onWindowKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('pointerdown', onWindowPointerDown)
  window.removeEventListener('keydown', onWindowKeyDown)
})
</script>

<template>
  <div class="relative flex min-h-0 flex-1 flex-col">
    <div class="flex items-center justify-between border-b border-line px-4 py-2">
      <p class="text-xs text-mute">
        <span class="font-num text-sm text-gold">{{ state.total.toLocaleString() }}</span>
        张卡
        <span v-if="state.typeDirect" class="ml-2 text-golddim">
          已按类型直搜:{{ state.typeDirect.join(' + ') }}
        </span>
        <span v-if="state.loading" class="ml-2 text-faint">检索中…</span>
      </p>
      <div class="flex overflow-hidden rounded-sm border border-line">
        <button
          v-for="s in SIZES"
          :key="s.v"
          class="px-2.5 py-1 text-[11px] transition-colors"
          :class="state.size === s.v ? 'bg-golddim/40 text-gold' : 'bg-panel2 text-mute hover:text-parch'"
          @click="setSize(s.v)"
        >{{ s.t }}</button>
      </div>
    </div>

    <div v-if="state.error" class="p-8 text-sm text-[#d95f4e]">查询失败:{{ state.error }}(请确认后端服务已启动)</div>

    <!-- 无图:紧凑列表 -->
    <div v-else-if="isList" class="min-h-0 flex-1 overflow-y-auto">
      <div
        class="sticky top-0 z-10 grid gap-2 border-b border-line bg-panel px-3 py-1.5"
        :style="{ gridTemplateColumns: LIST_COLS }"
      >
        <span v-for="(h, i) in HEADERS" :key="h"
          class="text-[10px] tracking-[0.15em] text-faint"
          :class="i === HEADERS.length - 1 ? 'text-right' : ''"
        >{{ h }}</span>
      </div>
      <CardRow
        v-for="c in state.items"
        :key="c.oracle_id"
        :card="c"
        @contextmenu="openCardContextMenu"
        @preview="showCardTip"
        @preview-move="moveCardTip"
        @preview-leave="hideCardTip"
      />
      <p v-if="!state.items.length && !state.loading" class="py-16 text-center text-sm text-faint">
        没有符合条件的卡牌
      </p>
    </div>

    <!-- 图片网格 -->
    <div v-else class="grid min-h-0 flex-1 gap-3 overflow-y-auto p-4" :style="{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }">
      <CardTile
        v-for="c in state.items"
        :key="c.oracle_id"
        :card="c"
        @contextmenu="openCardContextMenu"
        @preview="showCardTip"
        @preview-move="moveCardTip"
        @preview-leave="hideCardTip"
      />
      <p v-if="!state.items.length && !state.loading" class="col-span-full py-16 text-center text-sm text-faint">
        没有符合条件的卡牌
      </p>
    </div>

    <CardTip ref="cardTip" />

    <div
      v-if="contextMenu"
      ref="contextMenuElement"
      class="fixed z-50 max-h-[80vh] w-60 overflow-y-auto rounded-sm border border-line bg-panel p-1.5 shadow-xl"
      :style="{ left: `${contextMenuPosition.x}px`, top: `${contextMenuPosition.y}px` }"
      role="menu"
      @pointerdown.stop
      @click.stop
    >
      <button
        class="block w-full rounded-sm px-2.5 py-2 text-left text-xs text-parch transition-colors hover:bg-panel2 hover:text-gold"
        role="menuitem"
        @click="copyCardName(contextMenu.name_en, '英文名称')"
      >复制卡片英文名</button>
      <button
        class="block w-full rounded-sm px-2.5 py-2 text-left text-xs text-parch transition-colors hover:bg-panel2 hover:text-gold disabled:cursor-default disabled:opacity-40"
        :disabled="!contextMenu.name_zh"
        role="menuitem"
        @click="copyCardName(contextMenu.name_zh, '中文名称')"
      >复制卡片中文名称</button>
      <div v-if="contextMenu.sf_tags?.length" class="my-1 border-t border-line pt-1">
        <button
          v-for="tag in contextMenu.sf_tags"
          :key="tag"
          class="block w-full rounded-sm px-2.5 py-1.5 text-left text-xs text-mute transition-colors hover:bg-panel2 hover:text-gold"
          :title="tag"
          role="menuitem"
          @click="addTagToFilter(tag)"
        >{{ state.meta?.tagdict?.[tag] || tag }}</button>
      </div>
      <p v-if="copyStatus" class="px-2.5 py-1.5 text-[10px] text-faint" role="status">{{ copyStatus }}</p>
    </div>

    <div class="flex items-center justify-between border-t border-line px-4 py-2">
      <button
        class="rounded-sm border border-line px-3 py-1.5 text-xs text-mute hover:text-parch disabled:opacity-30"
        :disabled="state.page <= 1 || state.loading"
        @click="prevPage()"
      >上一页</button>
      <p class="text-xs text-faint font-num">{{ state.page }} / {{ totalPages }}</p>
      <button
        class="rounded-sm border border-line px-3 py-1.5 text-xs text-mute hover:text-parch disabled:opacity-30"
        :disabled="state.page >= totalPages || state.loading"
        @click="nextPage()"
      >下一页</button>
    </div>
  </div>
</template>
