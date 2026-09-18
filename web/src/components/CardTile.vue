<script setup>
import { computed } from 'vue'
import { state, openDetail } from '../store'

const props = defineProps({
  card: Object,
})

const loaded = computed(() => true)

function onImg(e) {
  e.target.classList.add('loaded')
}

const sizes = {
  S: { w: 'w-24', img: 'h-32', name: 'text-[11px]' },
  M: { w: 'w-36', img: 'h-48', name: 'text-xs' },
  L: { w: 'w-52', img: 'h-72', name: 'text-sm' },
}
const sz = computed(() => sizes[state.size] || sizes.M)
</script>

<template>
  <button
    class="group flex flex-col items-start gap-1 text-left"
    :class="sz.w"
    @click="openDetail(card.oracle_id)"
  >
    <div class="w-full overflow-hidden rounded-[3px] bg-panel2" :class="sz.img">
      <img
        v-if="card.image_url"
        :src="card.image_url"
        :alt="card.name_en"
        loading="lazy"
        class="cardimg h-full w-full object-cover"
        @load="onImg"
      />
      <div v-else class="flex h-full w-full items-center justify-center text-[10px] text-faint">无图</div>
    </div>
    <div class="w-full leading-tight">
      <p class="hl-title truncate font-medium" :class="sz.name">
        {{ card.name_zh || card.name_en }}
      </p>
      <p class="truncate text-[10px] text-faint">
        <template v-if="card.name_zh">{{ card.name_en }}</template>
        <template v-else>{{ card.type_line_en }}</template>
      </p>
      <p class="mt-0.5 flex items-center gap-1 text-[10px] text-mute">
        <span v-if="card.cmc !== null" class="font-num">{{ card.cmc }}</span>
        <span v-if="card.edhrec_rank" class="text-faint">· EDH {{ card.edhrec_rank }}</span>
      </p>
    </div>
  </button>
</template>
