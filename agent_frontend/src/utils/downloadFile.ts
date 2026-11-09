import request from '@/api/request'

export async function downloadFile(fileId: string, filename: string): Promise<void> {
  const response = await request.get<Blob>(`/api/files/${encodeURIComponent(fileId)}/content`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // 浏览器开始接管下载后释放 URL。
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
