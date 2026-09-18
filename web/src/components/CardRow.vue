<script setup>
import { computed } from 'vue'
import { state, openDetail, LIST_COLS } from '../store'

const props = defineProps({
  card: Object,
})

const rarityMap = {
  common: { t: '普通', c: 'text-faint' },
  uncommon: { t: '非普通', c: 'text-[#8fa8a0]' },
  rare: { t: '稀有', c: 'text-[#5ba4cf]' },
  mythic: { t: '秘稀', c: 'text-[#d95f4e]' },
}
const rarity = computed(() => rarityMap[props.card.rarity] || rarityMap.common)

const tagZh = computed(() => {
  const td = state.meta?.tagdict || {}
  return (props.card.sf_tags || [])
    .filter((t) => typeof t === 'string' && /^[a-z]/.test(t))
    .slice(0, 3)
    .map((t) => td[t] || t)
    .join(' / ')
})
</script>

<template>
  <button
    class="grid w-full items-center gap-2 border-b border-line px-3 py-1.5 text-left transition-colors hover:bg-panel2"
    :style="{ gridTemplateColumns: LIST_COLS }"
    @click="openDetail(card.oracle_id)"
  >
    <!-- 名称 -->
    <span class="min-w-0">
      <span class="block truncate text-xs font-medium text-parch">{{ card.name_zh || card.name_en }}</span>
      <span v-if="card.name_zh" class="block truncate text-[10px] text-faint">{{ card.name_en }}</span>
    </span>
    <!-- 类型 -->
    <span class="truncate text-[11px] text-mute">{{ card.type_line_zh || card.type_line_en }}</span>
    <!-- 费用 -->
    <span class="truncate font-num text-[11px] text-mute" :title="card.mana_cost">
      {{ card.mana_cost || '—' }}
    </span>
    <!-- 标签 -->
    <span class="truncate text-[10px] text-mute" :title="tagZh">{{ tagZh || '—' }}</span>
    <!-- 稀有度 -->
    <span class="text-[11px]" :class="rarity.c">{{ rarity.t }}</span>
    <!-- EDHREC -->
    <span class="text-right font-num text-[10px] text-faint">{{ card.edhrec_rank || '—' }}</span>
  </button>
</template>
