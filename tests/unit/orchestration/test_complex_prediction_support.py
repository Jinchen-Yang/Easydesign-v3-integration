from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import MsaMode, TemplateMode
from easydesign.core import ManifestStateError
from easydesign.orchestration.complex_prediction_support import (
    configured_prediction_chain,
)
from easydesign.orchestration.config import (
    ComplexTemplateConfig,
    DisabledComplexMsaConfig,
    PrecomputedComplexMsaConfig,
    QueryOnlyComplexMsaConfig,
    RemoteProtenixMsaConfig,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_resolves_remote_msa_precomputed_pairing_and_binder_templates(
    tmp_path: Path,
) -> None:
    paired = (tmp_path / "binder-paired.a3m").resolve()
    paired.write_text(">query\nACDE\n>paired\nAC-E\n", encoding="utf-8")
    templates = (tmp_path / "binder-templates.json").resolve()
    templates.write_text(
        json.dumps(
            [
                {
                    "mmcif": "data_binder\n#\n",
                    "queryIndices": [0, 1, 2, 3],
                    "templateIndices": [0, 1, 2, 3],
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    chain = configured_prediction_chain(
        chain_id="B",
        role="binder",
        sequence="ACDE",
        unpaired_msa=RemoteProtenixMsaConfig(),
        paired_msa=PrecomputedComplexMsaConfig(
            path=paired,
            sha256=_sha(paired),
        ),
        templates=ComplexTemplateConfig(
            mode="precomputed",
            data_path=templates,
            data_sha256=_sha(templates),
        ),
        query_only_root=tmp_path / "queries",
        target_condition=None,
    )

    assert chain.unpaired_msa_mode is MsaMode.REMOTE
    assert chain.unpaired_msa_path is None
    assert chain.paired_msa_mode is MsaMode.PRECOMPUTED
    assert chain.paired_msa_path is not None
    assert chain.paired_msa_path != paired
    assert chain.paired_msa_path.parent == tmp_path / "queries"
    assert _sha(chain.paired_msa_path) == _sha(paired)
    assert chain.template_mode is TemplateMode.PRECOMPUTED
    assert chain.template_data_path is not None
    assert chain.template_data_path != templates
    assert chain.template_data_path.parent == tmp_path / "queries"
    assert _sha(chain.template_data_path) == _sha(templates)


def test_resolves_query_only_and_disabled_features_independently(
    tmp_path: Path,
) -> None:
    chain = configured_prediction_chain(
        chain_id="A",
        role="target",
        sequence="FGHI",
        unpaired_msa=QueryOnlyComplexMsaConfig(),
        paired_msa=DisabledComplexMsaConfig(),
        templates=ComplexTemplateConfig(mode="disabled"),
        query_only_root=tmp_path / "queries",
        target_condition=None,
    )

    assert chain.unpaired_msa_mode is MsaMode.PRECOMPUTED
    assert chain.unpaired_msa_path is not None
    assert chain.unpaired_msa_path.read_text() == ">query\nFGHI\n"
    assert chain.paired_msa_mode is MsaMode.DISABLED
    assert chain.paired_msa_path is None
    assert chain.template_mode is TemplateMode.DISABLED


def test_precomputed_msa_must_match_chain_query(tmp_path: Path) -> None:
    msa = (tmp_path / "wrong.a3m").resolve()
    msa.write_text(">query\nAAAA\n", encoding="utf-8")

    with pytest.raises(ManifestStateError, match="query"):
        configured_prediction_chain(
            chain_id="B",
            role="binder",
            sequence="CCCC",
            unpaired_msa=PrecomputedComplexMsaConfig(
                path=msa,
                sha256=_sha(msa),
            ),
            paired_msa=DisabledComplexMsaConfig(),
            templates=ComplexTemplateConfig(mode="disabled"),
            query_only_root=tmp_path / "queries",
            target_condition=None,
        )
