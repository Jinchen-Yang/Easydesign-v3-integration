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
