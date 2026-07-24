"""EasyDesign 核心契约的稳定异常类型。"""


class EasyDesignError(Exception):
    """所有可预期 EasyDesign 异常的基类。"""


class ContractError(EasyDesignError):
    """输入或状态违反基础契约。"""


class PathPolicyError(ContractError):
    """Artifact 路径不是安全的 run 相对路径。"""


class ArtifactNotFoundError(ContractError):
    """声明的 artifact 文件不存在。"""


class ArtifactIntegrityError(ContractError):
    """Artifact 大小或 SHA-256 与声明不一致。"""


class UndeclaredArtifactError(ContractError):
    """阶段尝试读取 manifest 未声明的 artifact。"""


class ManifestStateError(ContractError):
    """Manifest 或 Attempt 状态转换违反不可变规则。"""


class SerializationError(ContractError):
    """Manifest JSON 读取、写入或模型校验失败。"""


class ConfigurationError(ContractError):
    """EasyDesign 用户配置缺失、含歧义或不符合机器契约。"""


class TargetInputError(ContractError):
    """Target source 无法识别、尚未支持或不满足入口契约。"""


class SequenceInputError(TargetInputError):
    """蛋白序列或 FASTA 输入不满足当前 Stage 01 契约。"""


class BackendContractError(ContractError):
    """外部 backend 请求、能力或调用计划违反 adapter 契约。"""


class PredictionOutputError(BackendContractError):
    """结构预测 backend 的正式输出缺失、损坏或不符合约定。"""
