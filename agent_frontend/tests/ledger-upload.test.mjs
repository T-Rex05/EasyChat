// P5 回归：账单上传错误展示与入口分流。
// 第一段先复现当前缺陷（旧提取逻辑只认 detail，业务 message 丢失）；
// 第二段验证修复后的统一提取与新入口分流判定。
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'

function loadModule(rel) {
  const raw = readFileSync(new URL(rel, import.meta.url), 'utf8')
  const script = raw.replace(/^import .*$/gm, '').replace(/export /g, '')
  const { outputText } = ts.transpileModule(script, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  })
  const exports = {}
  new Function('require', 'exports', 'module',
    outputText + '\nexports.extractErrorMessage = extractErrorMessage; exports.looksLikeImageFile = looksLikeImageFile;'
  )(() => ({ default: null }), exports, { exports })
  return exports
}

test('缺陷复现：旧版 fail() 只读 detail，AppError 的 message 中文原因丢失', () => {
  // 与修复前 LedgerView.vue fail() 同源的逻辑（缺陷基线）
  const oldFail = (err) => {
    const data = err?.response?.data
    return data?.detail ? String(data.detail) : String(err)
  }
  const axiosLike = {
    response: { data: { error: 'INVALID_INPUT', message: '图片请走截图识别候选流程，不能作为账单文件导入' } },
    message: 'Request failed with status code 422',
  }
  const shown = oldFail(axiosLike)
  assert.doesNotMatch(shown, /截图识别/, '当前行为：中文原因没有出现在界面上（这就是缺陷）')
  assert.match(shown, /422|AxiosError|Object/)
})

test('extractErrorMessage：detail 优先、message 兜底、校验数组与对象形态', async () => {
  const { extractErrorMessage } = loadModule('../src/utils/errorMessage.ts')

  assert.equal(
    extractErrorMessage({
      response: { data: { error: 'INVALID_INPUT', message: '图片请走截图识别候选流程，不能作为账单文件导入' } },
      message: 'Request failed with status code 422',
    }),
    '图片请走截图识别候选流程，不能作为账单文件导入',
  )
  assert.equal(
    extractErrorMessage({ response: { data: { detail: '文件尚未就绪，稍后再试' } } }),
    '文件尚未就绪，稍后再试',
  )
  assert.equal(
    extractErrorMessage({
      response: { data: { detail: [{ loc: ['body', 'file'], msg: '字段缺失', type: 'missing' }] } },
    }),
    'body.file: 字段缺失',
  )
  assert.equal(
    extractErrorMessage({ response: { data: { detail: { reason: '上传被拒' } } } }),
    '上传被拒',
  )
  assert.equal(extractErrorMessage(new Error('网络中断')), '网络中断')
  assert.match(extractErrorMessage(undefined), /未知错误|undefined/)
})

test('looksLikeImageFile：MIME 与扩展名双判定（绕过 accept 也算）', async () => {
  const { looksLikeImageFile } = loadModule('../src/utils/errorMessage.ts')
  assert.equal(looksLikeImageFile({ name: 'a.png', type: '' }), true)
  assert.equal(looksLikeImageFile({ name: 'photo', type: 'image/jpeg' }), true)
  assert.equal(looksLikeImageFile({ name: '微信支付账单.csv', type: 'text/csv' }), false)
  assert.equal(looksLikeImageFile({ name: 'bill.xlsx', type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), false)
  assert.equal(looksLikeImageFile({ name: 'report.pdf', type: 'application/pdf' }), false)
})
