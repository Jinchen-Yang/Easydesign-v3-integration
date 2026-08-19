"""Read-only GPCRdb endpoint adapter over the shared scientific HTTP client."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from urllib.parse import quote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from easydesign.backends.target_sources.remote import (
    RetrievalRecord,
    ScientificHttpClient,
)
from easydesign.core import BackendContractError

GPCRDB_BASE_URL = "https://gpcrdb.org/services"
GPCRDB_CONTEXT_SCHEMA = "gpcr-receptor-context-v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]+$")

_RECEPTOR_CLASS_BY_TOP_SLUG = {
    "001": "Class A (Rhodopsin)",
    "002": "Class B1 (Secretin)",
    "003": "Class B2 (Adhesion)",
    "004": "Class C (Glutamate)",
    "005": "Class D1 (Ste2-like fungal pheromone)",
    "006": "Class F (Frizzled)",
    "007": "Class O1",
    "008": "Class O2",
    "009": "Class T2",
    "010": "Other GPCRs",
}


class GpcrdbWarning(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4096)
    endpoint: str | None = None
    required: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class GpcrdbIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_name: str
    accession: str | None = None
    pdb_code: str | None = None
    preferred_chain: str | None = None
    status: Literal["resolved", "identifier_conflict"]


class GpcrdbReceptorContext(BaseModel):
    """Typed outer contract while retaining complete endpoint payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["gpcr-receptor-context-v1"] = (
        "gpcr-receptor-context-v1"
    )
    status: Literal["resolved", "partial", "identifier_conflict"]
    identity: GpcrdbIdentity
    receptor: Any
    family: dict[str, Any]
    topology: dict[str, Any]
    state: dict[str, Any]
    structures: dict[str, Any]
    interactions: dict[str, Any]
    ligands: Any = None
    mutations: Any = None
    warnings: tuple[GpcrdbWarning, ...] = ()
    retrieval_records: tuple[RetrievalRecord, ...]

    def legacy_projection(self) -> dict[str, Any]:
        """Project into the current scientific engine without dropping evidence."""

        payload = self.model_dump(mode="python")
        payload["provenance"] = [
            {
                "source": (
                    "cache"
                    if record.cache_status == "hit"
                    else "network"
                ),
                "status": "resolved",
                "method": record.method,
                "endpoint": urlparse(record.url).path,
                "url": record.url,
                "retrieved_at": record.retrieved_at.isoformat(),
                "data_sha256": record.response_sha256,
                "artifact_name": record.artifact_name,
                "status_code": record.status_code,
                "cache_status": record.cache_status,
            }
            for record in self.retrieval_records
            if record.error_type is None
        ]
        payload.pop("retrieval_records", None)
        payload.pop("status", None)
        return payload


class GpcrdbAdapter:
    """Interpret GPCRdb endpoints; transport, cache and evidence stay shared."""

    def __init__(
        self,
        client: ScientificHttpClient,
        *,
        base_url: str = GPCRDB_BASE_URL,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise BackendContractError("GPCRdb base_url 必须是绝对 HTTPS URL")
        self.client = client
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _clean_identifier(value: str, label: str) -> str:
        cleaned = value.strip()
        if not cleaned or _IDENTIFIER.fullmatch(cleaned) is None:
            raise BackendContractError(f"非法 GPCRdb {label}: {value!r}")
        return cleaned

    @staticmethod
    def _artifact_slug(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower()

    def _get(self, endpoint: str, *, artifact_name: str) -> Any:
        if endpoint.startswith("/") or ".." in endpoint.split("/"):
            raise BackendContractError(f"非法 GPCRdb endpoint: {endpoint}")
        response = self.client.request(
            "GET",
            f"{self.base_url}/{endpoint.strip('/')}/",
            artifact_name=artifact_name,
        )
        return response.json()

    def _optional(
        self,
        endpoint: str,
        *,
        artifact_name: str,
        warnings: list[GpcrdbWarning],
    ) -> Any:
        try:
            return self._get(endpoint, artifact_name=artifact_name)
        except BackendContractError as error:
            warnings.append(
                GpcrdbWarning(
                    code="optional_gpcrdb_endpoint_failed",
                    message=str(error),
                    endpoint=f"/services/{endpoint.strip('/')}/",
                )
            )
            return None

    @staticmethod
    def _parent_slug(parent: object) -> str | None:
        if isinstance(parent, Mapping):
            value = parent.get("slug")
        else:
            value = parent
        return str(value).strip() if value else None

    def _family_context(
        self,
        family_slug: str | None,
        *,
        warnings: list[GpcrdbWarning],
    ) -> tuple[Any, list[dict[str, Any]]]:
        if not family_slug:
            return None, []
        record = self._optional(
            f"proteinfamily/{quote(family_slug, safe='-_.')}",
            artifact_name=f"gpcrdb-family-{self._artifact_slug(family_slug)}.json",
            warnings=warnings,
        )
        chain: list[dict[str, Any]] = []
        current = record if isinstance(record, Mapping) else None
        seen: set[str] = set()
        for _ in range(12):
            if not isinstance(current, Mapping):
                break
            slug = str(current.get("slug") or "").strip()
            if not slug or slug in seen:
                break
            seen.add(slug)
            chain.append({"slug": slug, "name": current.get("name")})
            parent = current.get("parent")
            parent_slug = self._parent_slug(parent)
            if not parent_slug or parent_slug in seen:
                break
            if parent_slug == "000":
                chain.append(
                    {
                        "slug": parent_slug,
                        "name": parent.get("name") if isinstance(parent, Mapping) else None,
                    }
                )
                break
            fetched = self._optional(
                f"proteinfamily/{quote(parent_slug, safe='-_.')}",
                artifact_name=f"gpcrdb-family-{self._artifact_slug(parent_slug)}.json",
                warnings=warnings,
            )
            current = fetched if isinstance(fetched, Mapping) else None
        chain.reverse()
        return record, chain

    def fetch_receptor_context(
        self,
        *,
        entry: str | None = None,
        accession: str | None = None,
        pdb_code: str | None = None,
    ) -> GpcrdbReceptorContext:
        """Resolve identity plus optional topology/state/interaction evidence."""

        if not any((entry, accession, pdb_code)):
            raise BackendContractError(
                "GPCRdb context 至少需要 entry、accession 或 pdb_code 之一"
            )
        start_record = len(self.client.records)
        entry_value = self._clean_identifier(entry, "entry") if entry else None
        accession_value = (
            self._clean_identifier(accession, "accession") if accession else None
        )
        pdb_value = (
            self._clean_identifier(pdb_code, "pdb_code").upper()
            if pdb_code
            else None
        )
        warnings: list[GpcrdbWarning] = []

        selected_structure: Any = None
        if pdb_value:
            selected_structure = self._get(
                f"structure/{quote(pdb_value, safe='-_.')}",
                artifact_name=f"gpcrdb-structure-{pdb_value.lower()}.json",
            )
            if isinstance(selected_structure, Mapping):
                structure_entry = selected_structure.get("protein")
                if entry_value and structure_entry and (
                    entry_value.lower() != str(structure_entry).lower()
                ):
                    warnings.append(
                        GpcrdbWarning(
                            code="identifier_conflict",
                            message=(
                                "提供的 entry 与 GPCRdb structure receptor 不一致"
                            ),
                            required=True,
                            details={
                                "provided_entry": entry_value,
                                "structure_entry": structure_entry,
                            },
                        )
                    )
                elif not entry_value and structure_entry:
                    entry_value = self._clean_identifier(
                        str(structure_entry), "structure protein"
                    )

        protein: Any = None
        if entry_value:
            protein = self._get(
                f"protein/{quote(entry_value, safe='-_.')}",
                artifact_name=f"gpcrdb-protein-{self._artifact_slug(entry_value)}.json",
            )
        elif accession_value:
            protein = self._get(
                f"protein/accession/{quote(accession_value, safe='-_.')}",
                artifact_name=(
                    f"gpcrdb-protein-accession-{self._artifact_slug(accession_value)}.json"
                ),
            )
            if (
                isinstance(protein, Sequence)
                and not isinstance(protein, (str, bytes, bytearray))
                and len(protein) == 1
                and isinstance(protein[0], Mapping)
            ):
                protein = protein[0]
            if isinstance(protein, Mapping) and protein.get("entry_name"):
                entry_value = self._clean_identifier(
                    str(protein["entry_name"]), "resolved entry"
                )
                protein = self._get(
                    f"protein/{quote(entry_value, safe='-_.')}",
                    artifact_name=f"gpcrdb-protein-{self._artifact_slug(entry_value)}.json",
                )

        if not entry_value or not isinstance(protein, Mapping):
            raise BackendContractError(
                "GPCRdb 无法解析唯一 receptor entry；停止解释后续 topology"
            )

        resolved_accession = protein.get("accession")
        if accession_value and resolved_accession and (
            accession_value.upper() != str(resolved_accession).upper()
        ):
            warnings.append(
                GpcrdbWarning(
                    code="identifier_conflict",
                    message="提供的 accession 与解析后的 receptor 不一致",
                    required=True,
                    details={
                        "provided_accession": accession_value,
                        "resolved_accession": resolved_accession,
                    },
                )
            )
        accession_value = str(resolved_accession or accession_value or "") or None

        family_slug = str(protein.get("family") or "") or None
        family_record, family_parent_chain = self._family_context(
            family_slug,
            warnings=warnings,
        )
        encoded_entry = quote(entry_value, safe="-_.")
        residues = self._optional(
            f"residues/extended/{encoded_entry}",
            artifact_name=f"gpcrdb-residues-{self._artifact_slug(entry_value)}.json",
            warnings=warnings,
        )
        available_structures = self._optional(
            f"structure/protein/{encoded_entry}",
            artifact_name=f"gpcrdb-structures-{self._artifact_slug(entry_value)}.json",
            warnings=warnings,
        )
        representatives = self._optional(
            f"structure/protein/{encoded_entry}/representative",
            artifact_name=(
                f"gpcrdb-structures-{self._artifact_slug(entry_value)}-representative.json"
            ),
            warnings=warnings,
        )
        mutations = self._optional(
            f"mutants/{encoded_entry}",
            artifact_name=f"gpcrdb-mutants-{self._artifact_slug(entry_value)}.json",
            warnings=warnings,
        )
        ligand_records = self._optional(
            f"ligands/{encoded_entry}",
            artifact_name=f"gpcrdb-ligands-{self._artifact_slug(entry_value)}.json",
            warnings=warnings,
        )

        ligand_interactions = None
        peptide_interactions = None
        gprotein_interactions = None
        if pdb_value:
            encoded_pdb = quote(pdb_value, safe="-_.")
            ligand_interactions = self._optional(
                f"structure/{encoded_pdb}/interaction",
                artifact_name=f"gpcrdb-interactions-{pdb_value.lower()}-ligand.json",
                warnings=warnings,
            )
            peptide_interactions = self._optional(
                f"structure/{encoded_pdb}/peptideinteraction",
                artifact_name=f"gpcrdb-interactions-{pdb_value.lower()}-peptide.json",
                warnings=warnings,
            )
            gprotein_interactions = self._optional(
                f"structure/{encoded_pdb}/complexinteraction",
                artifact_name=f"gpcrdb-interactions-{pdb_value.lower()}-complex.json",
                warnings=warnings,
            )

        receptor_class = (
            selected_structure.get("class")
            if isinstance(selected_structure, Mapping)
            else None
        )
        if not receptor_class:
            for item in reversed(family_parent_chain):
                name = str(item.get("name") or "")
                if name.startswith("Class "):
                    receptor_class = name
                    break
        if not receptor_class and family_slug:
            receptor_class = _RECEPTOR_CLASS_BY_TOP_SLUG.get(
                family_slug.split("_")[0]
            )

        conflict = any(item.code == "identifier_conflict" for item in warnings)
        optional_failure = any(
            item.code == "optional_gpcrdb_endpoint_failed" for item in warnings
        )
        status: Literal["resolved", "partial", "identifier_conflict"] = (
            "identifier_conflict"
            if conflict
            else "partial"
            if optional_failure or residues is None
            else "resolved"
        )
        return GpcrdbReceptorContext(
            status=status,
            identity=GpcrdbIdentity(
                entry_name=entry_value,
                accession=accession_value,
                pdb_code=pdb_value,
                preferred_chain=(
                    str(selected_structure.get("preferred_chain"))
                    if isinstance(selected_structure, Mapping)
                    and selected_structure.get("preferred_chain")
                    else None
                ),
                status="identifier_conflict" if conflict else "resolved",
            ),
            receptor=dict(protein),
            family={
                "slug": family_slug,
                "record": family_record,
                "parent_chain": family_parent_chain,
                "class": receptor_class,
                "numbering_scheme": protein.get("residue_numbering_scheme"),
            },
            topology={
                "residues": residues,
                "source": "GPCRdb residues/extended",
            },
            state={
                "selected": (
                    selected_structure.get("state")
                    if isinstance(selected_structure, Mapping)
                    else None
                ),
                "source": (
                    "GPCRdb structure annotation"
                    if selected_structure is not None
                    else None
                ),
            },
            structures={
                "selected": selected_structure,
                "available": available_structures,
                "representative_by_state": representatives,
            },
            interactions={
                "ligand": ligand_interactions,
                "peptide": peptide_interactions,
                "gprotein": gprotein_interactions,
            },
            ligands=ligand_records,
            mutations=mutations,
            warnings=tuple(warnings),
            retrieval_records=tuple(self.client.records[start_record:]),
        )


def fetch_receptor_context(
    client: ScientificHttpClient,
    *,
    entry: str | None = None,
    accession: str | None = None,
    pdb_code: str | None = None,
) -> GpcrdbReceptorContext:
    return GpcrdbAdapter(client).fetch_receptor_context(
        entry=entry,
        accession=accession,
        pdb_code=pdb_code,
    )


__all__ = [
    "GPCRDB_BASE_URL",
    "GPCRDB_CONTEXT_SCHEMA",
    "GpcrdbAdapter",
    "GpcrdbIdentity",
    "GpcrdbReceptorContext",
    "GpcrdbWarning",
    "fetch_receptor_context",
]
