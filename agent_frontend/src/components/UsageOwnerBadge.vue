<template>
  <span class="usage-owner-badge" :title="label">{{ label }}</span>
</template>

<script setup lang="ts">
defineProps<{ label: string }>()
</script>

<style scoped>
.usage-owner-badge {
  display: inline-block;
  max-width: 100%;
  min-width: 0;
  padding: 1px 7px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, #ac7a4e 64%, var(--border-primary));
  border-radius: 5px;
  background: color-mix(in srgb, #d79858 15%, var(--bg-primary));
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 650;
  line-height: 1.5;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}
</style>
