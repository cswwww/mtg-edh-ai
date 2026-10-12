<script setup>
import { ref } from 'vue'

// 通用卡图悬浮层:悬停卡/行时展示加大版卡图,方便读卡面文字
// 用法:<CardTip ref="tip" /> + @mouseenter="tip.show($event, card, sub)"
//      @mousemove="tip.move" @mouseleave="tip.hide"
const showTip = ref(false)
const x = ref(0)
const y = ref(0)
const name = ref('')
const img = ref('')
const sub = ref('')

const W = 264, H = 460  // 浮层估算尺寸(卡图 256 宽 + 底部信息条)

function place(e) {
  let px = e.clientX + 18
  let py = e.clientY + 14
  if (px + W > window.innerWidth) px = e.clientX - W - 10
  if (py + H > window.innerHeight) py = window.innerHeight - H - 8
  x.value = Math.max(4, px)
  y.value = Math.max(4, py)
}

// card: 含 name_zh / name_en / image_url 字段的卡对象;subText: 底部附加行
function show(e, card, subText = '') {
  name.value = card.name_zh || card.name_en || ''
  img.value = card.image_url || ''
  sub.value = subText
  showTip.value = true
  place(e)
}
function move(e) {
  if (showTip.value) place(e)
}
function hide() {
  showTip.value = false
}

defineExpose({ show, move, hide })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="showTip"
      class="pointer-events-none fixed z-[70] w-64 overflow-hidden rounded-[3px] border border-line bg-panel shadow-2xl"
      :style="{ left: x + 'px', top: y + 'px' }"
    >
      <img v-if="img" :src="img" class="cardimg loaded block w-full" />
      <div v-else class="flex h-80 w-full items-center justify-center text-[10px] text-faint">无卡图</div>
      <div class="border-t border-line bg-panel px-1.5 py-1">
        <p class="truncate text-[10px] text-mute">{{ name }}</p>
        <p v-if="sub" class="mt-0.5 font-num text-[9px] text-faint">{{ sub }}</p>
      </div>
    </div>
  </Teleport>
</template>
