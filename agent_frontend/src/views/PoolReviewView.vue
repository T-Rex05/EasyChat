<template>
  <div class="pool-review-page">
    <header class="page-header">
      <div class="header-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </div>
      <div class="header-content">
        <h1 class="page-title">技能池审核</h1>
        <p class="page-desc">审核用户提交的技能，确认后即可发布到技能池供他人安装</p>
      </div>
    </header>

    <PoolReviewPanel />
  </div>
</template>

<script setup lang="ts">
import PoolReviewPanel from './admin/PoolReviewPanel.vue'
</script>

<style scoped>
.pool-review-page {
  padding: 32px;
  max-width: 1200px;
  margin: 0 auto;
  min-height: 100%;
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 28px;
}

.header-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 12px;
  flex-shrink: 0;
}

.header-icon svg {
  width: 22px;
  height: 22px;
  color: #6b7280;
}

.page-title {
  margin: 0 0 6px 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.page-desc {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}
</style>