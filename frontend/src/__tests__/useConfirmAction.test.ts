import { beforeEach, describe, expect, it, vi } from 'vitest'

const { confirmMock } = vi.hoisted(() => ({ confirmMock: vi.fn() }))

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: confirmMock }
}))

import { useConfirmAction } from '@/composables/useConfirmAction'

describe('useConfirmAction', () => {
  beforeEach(() => {
    confirmMock.mockReset()
  })

  it('确认时返回 true，并带上红色主按钮与默认文案', async () => {
    confirmMock.mockResolvedValue('confirm')
    const { confirmDanger } = useConfirmAction()

    const confirmed = await confirmDanger({ title: '删除任务', message: '将删除该任务，不可恢复。' })

    expect(confirmed).toBe(true)
    expect(confirmMock).toHaveBeenCalledTimes(1)
    const [, , options] = confirmMock.mock.calls[0]
    expect(options).toMatchObject({
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger'
    })
  })

  it('取消时返回 false，不抛错', async () => {
    confirmMock.mockRejectedValue('cancel')
    const { confirmDanger } = useConfirmAction()

    await expect(confirmDanger({ title: '删除任务', message: '不可恢复', confirmText: '删除' })).resolves.toBe(false)
    const [, , options] = confirmMock.mock.calls[0]
    expect(options.confirmButtonText).toBe('删除')
  })

  it('关闭弹窗同样返回 false', async () => {
    confirmMock.mockRejectedValue('close')
    const { confirmDanger } = useConfirmAction()

    await expect(confirmDanger({ title: 't', message: 'm' })).resolves.toBe(false)
  })
})
