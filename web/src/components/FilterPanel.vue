<script setup>
import { state, search } from '../store'

const colorRows = [
  { c: 'W', label: '白' }, { c: 'U', label: '蓝' }, { c: 'B', label: '黑' },
  { c: 'R', label: '红' }, { c: 'G', label: '绿' },
]
const ccModifiers = [
  { k: 'ccMulti', t: '必须多色' },
  { k: 'ccExclude', t: '不含未选' },
  { k: 'ccPartial', t: '部分匹配' },
]
const cmcOptions = [...Array.from({ length: 11 }, (_, i) => String(i)), '11+']
const quickTypes = [
  { t: 'Creature', zh: '生物' }, { t: 'Sorcery', zh: '法术' },
  { t: 'Instant', zh: '瞬间' }, { t: 'Enchantment', zh: '结界' },
  { t: 'Artifact', zh: '神器' }, { t: 'Land', zh: '地' },
  { t: 'Planeswalker', zh: '鹏洛客' },
]
const rarityList = [
  { v: 'common', t: '普通' },
  { v: 'uncommon', t: '非普通' },
  { v: 'rare', t: '稀有' },
  { v: 'mythic', t: '秘稀' },
]

function toggleIn(arr, v) {
  const i = arr.indexOf(v)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(v)
  search()
}

const sec = 'mt-4 first:mt-0'
const h = 'mb-2 text-[11px] tracking-[0.2em] text-faint'
// 金色 chip:未选=暗色描边,选中=金描边+金底+金字
const chip = (on) => on
  ? 'border-golddim bg-golddim/40 font-bold text-gold'
  : 'border-line bg-panel2 text-mute hover:border-golddim hover:text-parch'
</script>

<template>
  <aside class="w-52 shrink-0 space-y-0 overflow-y-auto border-r border-line bg-panel p-4">
    <div :class="sec">
      <p :class="h">颜色</p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="m in colorRows"
          :key="m.c"
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state.cardColors.includes(m.c))"
          @click="toggleIn(state.cardColors, m.c)"
        >{{ m.label }}</button>
        <button
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state.ccColorless)"
          @click="state.ccColorless = !state.ccColorless; search()"
        >无</button>
      </div>
      <div class="mt-1.5 flex flex-wrap gap-1">
        <button
          v-for="m in ccModifiers"
          :key="m.k"
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state[m.k])"
          @click="state[m.k] = !state[m.k]; search()"
        >{{ m.t }}</button>
      </div>
    </div>

    <div :class="sec">
      <p :class="h">指挥官标识色</p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="m in colorRows"
          :key="m.c"
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state.ciColors.includes(m.c))"
          @click="toggleIn(state.ciColors, m.c)"
        >{{ m.label }}</button>
        <button
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state.ciColorless)"
          @click="state.ciColorless = !state.ciColorless; search()"
        >无色</button>
      </div>
      <p class="mt-1.5 text-[10px] leading-relaxed text-faint">搜索结果卡牌的标识色为所选颜色的子集</p>
    </div>

    <div :class="sec">
      <p :class="h">总法术力</p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="v in cmcOptions"
          :key="v"
          class="rounded-sm border px-2 py-1 font-num text-[11px] transition-colors"
          :class="chip(state.cmcSel.includes(v))"
          @click="toggleIn(state.cmcSel, v)"
        >{{ v }}</button>
        <button
          v-if="state.cmcSel.length"
          class="rounded-sm border border-line px-2 py-1 text-[11px] text-faint hover:text-gold"
          @click="state.cmcSel = []; search()"
        >清</button>
      </div>
    </div>

    <div :class="sec">
      <p :class="h">卡牌类型 <span class="text-faint">(多选为交集)</span></p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="m in quickTypes"
          :key="m.t"
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state.types.includes(m.t))"
          @click="toggleIn(state.types, m.t)"
        >{{ m.zh }}</button>
        <button
          class="rounded-sm border border-dashed px-2 py-1 text-[11px] transition-colors"
          :class="state.types.length ? 'border-golddim text-gold' : 'border-line text-mute hover:border-golddim hover:text-parch'"
          @click="state.typeModalOpen = true"
        >更多{{ state.types.length ? ` · ${state.types.length}` : '' }}</button>
      </div>
    </div>

    <div :class="sec">
      <p :class="h">稀有度 <span class="text-faint">(多选为并集)</span></p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="r in rarityList"
          :key="r.v"
          class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
          :class="chip(state.rarities.includes(r.v))"
          @click="toggleIn(state.rarities, r.v)"
        >{{ r.t }}</button>
      </div>
    </div>

    <div :class="sec">
      <button
        class="rounded-sm border px-2 py-1 text-[11px] transition-colors"
        :class="chip(state.commander)"
        @click="state.commander = !state.commander; search()"
      >仅指挥官赛制合法</button>
    </div>
  </aside>
</template>
