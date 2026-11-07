/**
 * 危险操作确认（唯一允许直接调用 `ElMessageBox.confirm` 的地方）。
 *
 * 只统一「warning + 红色主按钮 + 默认按钮文案」的调用形态；
 * 标题与正文由页面传入并保持原文，不做二次改写。
 */
import { ElMessageBox } from 'element-plus'

export interface ConfirmDangerOptions {
  title: string
  message: string
  /** 默认「确定」。 */
  confirmText?: string
  /** 默认「取消」。 */
  cancelText?: string
}

/** 返回 `true` 表示确认执行，取消 / 关闭返回 `false`（不抛错）。 */
export function useConfirmAction(): {
  confirmDanger: (options: ConfirmDangerOptions) => Promise<boolean>
} {
  async function confirmDanger(options: ConfirmDangerOptions): Promise<boolean> {
    try {
      await ElMessageBox.confirm(options.message, options.title, {
        type: 'warning',
        confirmButtonText: options.confirmText ?? '确定',
        cancelButtonText: options.cancelText ?? '取消',
        confirmButtonClass: 'el-button--danger'
      })
      return true
    } catch {
      return false
    }
  }

  return { confirmDanger }
}
