<template>
  <div class="panel-resize-handle" role="separator" tabindex="0"
    aria-orientation="vertical" :aria-label="label" :aria-valuenow="Math.round(width)"
    :aria-valuemin="min" :aria-valuemax="max"
    @pointerdown="startDrag" @keydown.left.prevent="resize(width - 16)"
    @keydown.right.prevent="resize(width + 16)" @keydown.home.prevent="resize(min)"
    @keydown.end.prevent="resize(max)" @dblclick="resize(initial)" />
</template>

<script setup lang="ts">
import { onUnmounted } from 'vue'
import { clampPanelWidth } from '@/utils/panelWidth'

const props = defineProps<{ label: string; width: number; min: number; max: number; initial: number }>()
const emit = defineEmits<{ resize: [width: number] }>()
let startX = 0
let startWidth = 0
let previousCursor = ''
let previousUserSelect = ''
let dragging = false

function resize(width: number) {
  emit('resize', clampPanelWidth(width, props.initial, props.min, props.max))
}

function move(event: PointerEvent) {
  resize(startWidth + event.clientX - startX)
}

function stopDrag() {
  if (!dragging) return
  dragging = false
  window.removeEventListener('pointermove', move)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
  window.removeEventListener('blur', stopDrag)
  document.body.style.cursor = previousCursor
  document.body.style.userSelect = previousUserSelect
}

function startDrag(event: PointerEvent) {
  if (event.button !== 0) return
  stopDrag()
  event.preventDefault()
  startX = event.clientX
  startWidth = props.width
  previousCursor = document.body.style.cursor
  previousUserSelect = document.body.style.userSelect
  dragging = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
  window.addEventListener('blur', stopDrag)
}

onUnmounted(stopDrag)
</script>

<style scoped>
.panel-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  z-index: 5;
  cursor: col-resize;
  touch-action: none;
}
.panel-resize-handle:hover, .panel-resize-handle:focus-visible {
  background: var(--brand);
  outline: none;
}
</style>
