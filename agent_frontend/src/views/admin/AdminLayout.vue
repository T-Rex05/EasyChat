<template>
  <div class="admin-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      :class="['admin-tab', { active: modelValue === tab.key }]"
      @click="$emit('update:modelValue', tab.key)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
interface Tab {
  key: string
  label: string
}

defineProps<{
  tabs: Tab[]
  modelValue: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<style scoped>
.admin-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-primary);
  margin-bottom: 24px;
}

.admin-tab {
  padding: 10px 20px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: -1px;
}

.admin-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.admin-tab.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
}
</style>
