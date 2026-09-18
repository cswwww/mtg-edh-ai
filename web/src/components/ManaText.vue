<script setup>
import { MANA } from '../store'

const props = defineProps({ text: String })

// 将 {X} 法术力符号渲染为彩色圆标
function render(t) {
  if (!t) return []
  const parts = t.split(/(\{[^}]+\})/g).filter((x) => x !== '')
  return parts.map((p) => {
    const m = p.match(/^\{([^}]+)\}$/)
    if (!m) return { txt: p }
    const sym = m[1].toUpperCase()
    const mana = MANA[sym]
    if (mana) return { sym, txt: sym, bg: mana.color, ink: mana.ink }
    // 通用/数字/横置等
    if (/^(\d+|X|Y|Z)$/.test(sym))
      return { sym, txt: sym, bg: '#cfc6b0', ink: '#191715' }
    if (sym === 'T') return { sym, txt: '↻', bg: '#cfc6b0', ink: '#191715' }
    if (sym === 'Q') return { sym, txt: '⇅', bg: '#cfc6b0', ink: '#191715' }
    if (sym === 'E') return { sym, txt: '∞', bg: '#cfc6b0', ink: '#191715' }
    if (sym === 'C') return { sym, txt: '◇', bg: '#9a917e', ink: '#191715' }
    if (sym === 'PW') return { sym, txt: 'PW', bg: '#cfc6b0', ink: '#191715' }
    if (sym.startsWith('2/')) {
      const half = sym.slice(2)
      const mana = MANA[half]
      return { sym, txt: '②' + half, bg: mana ? mana.color : '#cfc6b0', ink: mana ? mana.ink : '#191715' }
    }
    return { sym, txt: sym, bg: '#cfc6b0', ink: '#191715' }
  })
}
</script>

<template>
  <span class="whitespace-pre-wrap leading-relaxed">
    <template v-for="(p, i) in render(text)" :key="i">
      <span
        v-if="p.sym"
        class="mana-sym"
        :style="{ background: p.bg, color: p.ink }"
        >{{ p.txt }}</span
      >
      <template v-else>{{ p.txt }}</template>
    </template>
  </span>
</template>
