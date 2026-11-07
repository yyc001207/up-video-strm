import { beforeEach, describe, expect, it, vi } from 'vitest'

const { openLogDirMock } = vi.hoisted(() => ({ openLogDirMock: vi.fn() }))

vi.mock('@/api/desktop', () => ({
  desktopApi: { openLogDir: openLogDirMock }
}))

import { useLogDir } from '@/composables/useLogDir'

describe('useLogDir', () => {
  beforeEach(() => {
    openLogDirMock.mockReset()
  })

  it('按日志类型调用桌面接口', async () => {
    openLogDirMock.mockResolvedValue({ code: 200, data: { path: 'D:/logs' } })
    const { open } = useLogDir('upload')

    await open()

    expect(openLogDirMock).toHaveBeenCalledWith('upload')
  })

  it('接口失败时不抛错（提示由拦截器负责）', async () => {
    openLogDirMock.mockRejectedValue({ code: 400, msg: '仅 Windows 本地环境支持打开日志文件夹' })
    const { open } = useLogDir('openlist')

    await expect(open()).resolves.toBeUndefined()
  })

  it('请求未结束时重复点击不会重复调用', async () => {
    let resolveFirst: (() => void) | null = null
    openLogDirMock.mockImplementation(
      () =>
        new Promise(resolve => {
          resolveFirst = () => resolve({ code: 200, data: { path: '' } })
        })
    )
    const { open } = useLogDir('automation')

    const first = open()
    await open()
    expect(openLogDirMock).toHaveBeenCalledTimes(1)

    resolveFirst?.()
    await first
  })
})
