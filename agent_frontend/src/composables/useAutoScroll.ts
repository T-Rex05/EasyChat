// 智能滚动 composable

import { ref, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'

export function useAutoScroll(containerRef: { value: HTMLElement | null }) {
  const chatStore = useChatStore()
  const isUserScrolling = ref(false)

  // 检查是否在底部
  function isNearBottom(element: HTMLElement, threshold = 100): boolean {
    const { scrollTop, scrollHeight, clientHeight } = element
    return scrollHeight - scrollTop - clientHeight < threshold
  }

  // 滚动到底部
  function scrollToBottom(smooth = true) {
    if (!containerRef.value) return

    if (smooth) {
      containerRef.value.scrollTo({
        top: containerRef.value.scrollHeight,
        behavior: 'smooth',
      })
    } else {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    }
  }

  // 监听滚动事件
  function handleScroll() {
    if (!containerRef.value) return

    const nearBottom = isNearBottom(containerRef.value)

    if (nearBottom) {
      // 用户滚动到底部，恢复自动滚动
      isUserScrolling.value = false
      chatStore.setAutoScroll(true)
    } else {
      // 用户向上滚动，暂停自动滚动
      // 不再自动恢复：只有用户主动滚回底部才重新启用 autoScroll
      isUserScrolling.value = true
      chatStore.setAutoScroll(false)
    }
  }

  // 智能滚动：只有在自动滚动模式或接近底部时才滚动
  function smartScrollToBottom() {
    if (chatStore.autoScroll || isNearBottom(containerRef.value!)) {
      scrollToBottom()
    }
  }

  onMounted(() => {
    if (containerRef.value) {
      containerRef.value.addEventListener('scroll', handleScroll)
    }
  })

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('scroll', handleScroll)
    }
  })

  return {
    isUserScrolling,
    scrollToBottom,
    smartScrollToBottom,
  }
}
