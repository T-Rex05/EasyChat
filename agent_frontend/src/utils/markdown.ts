// Markdown 渲染工具：markdown-it + DOMPurify

import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

// 创建 markdown-it 实例
const md = new MarkdownIt({
  html: false,        // 禁用 HTML 标签（安全）
  breaks: true,       // 换行符转换为 <br>
  linkify: true,      // 自动识别链接
  typographer: true,  // 智能引号等
})

// 自定义渲染规则
// 1. 代码块添加复制按钮
const defaultCodeRender = md.renderer.rules.code_block || function (tokens, idx) {
  const content = tokens[idx].content
  return `<pre class="code-block"><code>${DOMPurify.sanitize(content)}</code><button class="code-block-copy-btn">复制</button></pre>`
}
md.renderer.rules.code_block = defaultCodeRender

// 2. 外链在新标签打开
const defaultLinkRender = md.renderer.rules.link_open || function (tokens, idx, options, _env, self) {
  const hrefIndex = tokens[idx].attrIndex('href')
  if (hrefIndex >= 0) {
    const href = tokens[idx].attrs![hrefIndex][1]
    // href 属性在 markdown-it 中类型为 string|number，运行时恒为 string；String() 为幂等转换
    if (String(href).startsWith('http')) {
      tokens[idx].attrPush(['target', '_blank'])
      tokens[idx].attrPush(['rel', 'noopener noreferrer'])
    }
  }
  return self.renderToken(tokens, idx, options)
}
md.renderer.rules.link_open = defaultLinkRender

/**
 * 渲染 Markdown 为 HTML（经过 DOMPurify 消毒）
 */
export function renderMarkdown(content: string): string {
  const html = md.render(content)
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling'],
  })
}

/**
 * 清洗模型输出（移除 <think> 标签、内部工具调用行等）
 */
export function sanitizeModelOutput(content: string): string {
  if (!content) return ''

  let sanitized = content

  // 移除 <think>...</think> 标签及其内容
  sanitized = sanitized.replace(/<think>[\s\S]*?<\/think>/g, '')

  // 移除内部工具调用行（如 todo_add、todo_update 等）
  const internalTools = ['todo_add', 'todo_update', 'todo_get', 'submit_skill_for_review', 'submit_agent_for_review']
  const toolPattern = new RegExp(`^\\s*(${internalTools.join('|')})\\(.*\\)\\s*$`, 'gm')
  sanitized = sanitized.replace(toolPattern, '')

  // 移除多余空行
  sanitized = sanitized.replace(/\n{3,}/g, '\n\n')

  return sanitized.trim()
}

export default md
