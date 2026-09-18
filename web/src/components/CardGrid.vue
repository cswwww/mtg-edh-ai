<script setup>
import { computed } from 'vue'
import { state, nextPage, prevPage, search, LIST_COLS } from '../store'
import CardTile from './CardTile.vue'
import CardRow from './CardRow.vue'

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

function setSize(v) {
  state.size = v
  state.pageSize = v === 'LIST' ? 120 : 60
  search(false)
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
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
      <CardRow v-for="c in state.items" :key="c.oracle_id" :card="c" />
      <p v-if="!state.items.length && !state.loading" class="py-16 text-center text-sm text-faint">
        没有符合条件的卡牌
      </p>
    </div>

    <!-- 图片网格 -->
    <div v-else class="grid min-h-0 flex-1 gap-3 overflow-y-auto p-4" :style="{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))` }">
      <CardTile v-for="c in state.items" :key="c.oracle_id" :card="c" />
      <p v-if="!state.items.length && !state.loading" class="col-span-full py-16 text-center text-sm text-faint">
        没有符合条件的卡牌
      </p>
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
