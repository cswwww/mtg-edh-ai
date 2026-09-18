<script setup>
import { state, search } from '../store'

const modes = [
  { v: 'vector', t: '语义' },
  { v: 'fts', t: '卡名' },
]
const sorts = [
  { v: 'rel', t: '按相关度' },
  { v: 'edhrec', t: '按 EDHREC 热度' },
  { v: 'cmc_asc', t: '法术力值 ↑' },
  { v: 'cmc_desc', t: '法术力值 ↓' },
  { v: 'name', t: '按名称' },
]
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <div class="flex overflow-hidden rounded-sm border border-line">
      <button
        v-for="m in modes"
        :key="m.v"
        class="px-3 py-2 text-xs tracking-widest transition-colors"
        :class="state.mode === m.v ? 'bg-gold text-ink font-bold' : 'bg-panel2 text-mute hover:text-parch'"
        @click="state.mode = m.v; search()"
      >{{ m.t }}</button>
    </div>
    <input
      v-model="state.q"
      class="min-w-56 flex-1 rounded-sm border border-line bg-panel2 px-3 py-2 text-sm text-parch placeholder-faint outline-none focus:border-golddim"
      placeholder="中文 / 拼音首字母(如 ygj)/ 卡名,或描述效果:每当有生物死去时抓牌"
      @keyup.enter="search()"
    />
    <button
      class="rounded-sm bg-gold px-4 py-2 text-xs font-bold tracking-widest text-ink hover:opacity-85"
      @click="search()"
    >搜索</button>
    <select
      v-model="state.sort"
      class="rounded-sm border border-line bg-panel2 px-2 py-2 text-xs text-mute outline-none"
      @change="search()"
    >
      <option v-for="s in sorts" :key="s.v" :value="s.v">{{ s.t }}</option>
    </select>
    <button
      class="rounded-sm border border-line bg-panel2 px-3 py-2 text-xs tracking-widest text-mute transition-colors hover:border-golddim hover:text-gold"
      title="查看/编辑语义搜索黑话词典"
      @click="state.slangOpen = true"
    >词典</button>
  </div>
</template>
