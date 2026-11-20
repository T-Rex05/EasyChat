<template>
  <span class="channel-badge" :data-channel="channel === 'wechat' || channel === 'web' ? channel : undefined">
    {{ channel === 'wechat' ? '微信' : channel === 'web' ? 'Web' : '来源未知' }}
  </span>
</template>

<script setup lang="ts">
defineProps<{ channel?: string | null }>()
</script>

<style scoped>
.channel-badge {
  display: inline-flex;
  align-items: center;
  flex: none;
  width: max-content;
  padding: 1px 6px;
  border: 1px solid currentColor;
  border-radius: 5px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 650;
  line-height: 1.5;
  white-space: nowrap;
}
.channel-badge[data-channel='wechat'] {
  color: var(--text-primary);
  background: color-mix(in srgb, #1dba69 18%, transparent);
  border-color: #37915e;
}
.channel-badge[data-channel='web'] {
  color: var(--text-primary);
  background: color-mix(in srgb, #576dff 15%, transparent);
  border-color: #6977ce;
}
</style>
