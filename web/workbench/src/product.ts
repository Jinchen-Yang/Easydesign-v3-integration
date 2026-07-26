import type { StageState } from "./types";

export const stageNames = [
  "第1步：准备目标结构",
  "第2步：选择结合区域",
  "第3步：生成设计方案",
  "第4步：小规模生成",
  "第5步：筛选与验证",
  "第6步：规模化生成",
  "第7步：最终候选",
] as const;

export const stageShortNames = [
  "目标结构",
  "结合区域",
  "设计方案",
  "小规模",
  "筛选验证",
  "规模化",
  "最终候选",
] as const;

export const stateCopy: Record<StageState, { label: string; description: string }> = {
  draft: { label: "草稿", description: "尚未提交运行" },
  validating: { label: "正在检查", description: "正在检查配置与输入" },
  ready: { label: "可以运行", description: "配置和运行环境检查通过" },
  queued: { label: "等待运行", description: "正在等待可用计算资源" },
  running: { label: "正在运行", description: "正在执行计算任务" },
  "awaiting-human-approval": {
    label: "等待你的确认",
    description: "需要你确认科学选择后才能继续",
  },
  succeeded: { label: "已完成", description: "本步骤已完成并保存正式结果" },
  "scientific-stop": {
    label: "未达到继续条件",
    description: "程序已正常完成，但结果没有达到下一步的科学门槛",
  },
  "operational-failed": { label: "运行失败", description: "软件、环境或输出文件发生错误" },
  "not-reached": { label: "尚未开始", description: "本次运行还没有进入这一步" },
  "simulated-preview": { label: "演示回放", description: "这是演示状态，不是新的科学运行" },
};

export const artifactNames: Record<string, string> = {
  "target-structure": "目标结构",
  "target-bundle": "目标结构包",
  "sequence-fasta": "目标序列",
  "residue-mapping": "残基编号映射",
  "structure-quality": "结构质量报告",
  hotspots: "已确认结合区域",
  "design-matrix": "设计方案矩阵",
  "strategy-bundle": "设计策略包",
  "pilot-progress-final": "小规模生成进度",
  "pilot-bundle": "小规模候选包",
  "pilot-filter-report": "小规模筛选报告",
  "expansion-validation-report": "扩展与复核报告",
  "final-candidate-package": "最终候选包",
};

export function artifactName(id: string) {
  return artifactNames[id] || id.replaceAll("-", " ");
}

export function capabilityLabel(value: string) {
  const labels: Record<string, string> = {
    planned: "已规划",
    implemented: "功能已实现",
    "smoke-validated": "已通过工程验证",
    "scientifically-validated": "已通过科学验证",
    "production-ready": "可用于正式生产",
  };
  return labels[value] || value;
}
