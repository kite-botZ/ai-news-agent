/**
 * 极简 Markdown 渲染器。
 *
 * 简报内容是 LLM 生成的 Markdown，直接丢进 <pre> 会露出 #、** 这些符号，
 * 这里做一层轻量渲染。不引入第三方库。
 *
 * 安全：先对文本做 HTML 转义，再套 Markdown 规则，
 * 所以模型即使输出了 <script> 也只会被当成普通文字。
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** 行内元素：先转义，再套规则 */
function inline(raw: string): string {
  let t = escapeHtml(raw)

  // 行内代码 `code`
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>')

  // 链接 [文本](url)，只放行 http(s)
  t = t.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  )

  // 加粗 **文本**
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // 斜体 *文本*
  t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')

  return t
}

export function renderMarkdown(md: string): string {
  if (!md) return ''

  const lines = md.split(/\r?\n/)
  const out: string[] = []
  let listOpen: 'ul' | 'ol' | null = null

  const closeList = () => {
    if (listOpen) {
      out.push(`</${listOpen}>`)
      listOpen = null
    }
  }

  for (const raw of lines) {
    const trimmed = raw.trim()

    // 空行 → 断开列表
    if (!trimmed) {
      closeList()
      continue
    }

    // 分隔线 --- *** ___
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      closeList()
      out.push('<hr/>')
      continue
    }

    // 标题 # ## ###（页面标题已是 h1，这里从 h2 起）
    const h = /^(#{1,6})\s+(.*)$/.exec(trimmed)
    if (h) {
      closeList()
      const level = Math.min(h[1].length + 1, 6)
      out.push(`<h${level}>${inline(h[2])}</h${level}>`)
      continue
    }

    // 引用 >
    if (trimmed.startsWith('>')) {
      closeList()
      out.push(`<blockquote>${inline(trimmed.replace(/^>\s?/, ''))}</blockquote>`)
      continue
    }

    // 无序列表 - * +
    const ul = /^[-*+]\s+(.*)$/.exec(trimmed)
    if (ul) {
      if (listOpen !== 'ul') {
        closeList()
        out.push('<ul>')
        listOpen = 'ul'
      }
      out.push(`<li>${inline(ul[1])}</li>`)
      continue
    }

    // 有序列表 1. 2.
    const ol = /^\d+\.\s+(.*)$/.exec(trimmed)
    if (ol) {
      if (listOpen !== 'ol') {
        closeList()
        out.push('<ol>')
        listOpen = 'ol'
      }
      out.push(`<li>${inline(ol[1])}</li>`)
      continue
    }

    // 普通段落
    closeList()
    out.push(`<p>${inline(trimmed)}</p>`)
  }

  closeList()
  return out.join('\n')
}
