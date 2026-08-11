"""Offline source catalog backed by the repository's reviewed configuration files."""

from __future__ import annotations

from pathlib import Path

from commander_ai.application.ports.source_adapter import SourceReview, SourceSummary
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.source_catalog import PermissionGatedSourceCatalog
from commander_ai.config.source_settings import SourceSettings, normalize_source_id
from commander_ai.config.yaml_loader import load_permission_gated_catalog, load_source_settings


class ConfiguredSourceCatalog:
    """List reviewed source metadata without performing network or source I/O."""

    def __init__(self, repository_root: Path | str) -> None:
        self._root = Path(repository_root).expanduser().absolute()
        self._settings_root = self._root / "configs" / "sources"

    def list_sources(self) -> tuple[SourceSummary, ...]:
        settings = self._load_settings()
        gated = self._load_gated()
        summaries: list[SourceSummary] = []
        for source_id, source in settings.items():
            status = source.approval_status
            summaries.append(
                SourceSummary(
                    source_id=source_id,
                    approval_status=status.value,
                    current_use_status=None,
                    local_sync_allowed=status in SourcePolicy.LOCAL_SYNC_ALLOWLIST,
                    public_export_allowed=status in SourcePolicy.PUBLIC_EXPORT_ALLOWLIST,
                    research_only=status not in SourcePolicy.LOCAL_SYNC_ALLOWLIST,
                )
            )
        for gated_source in gated.sources:
            if gated_source.source_id in settings:
                continue
            summaries.append(
                SourceSummary(
                    source_id=gated_source.source_id,
                    approval_status=gated_source.approval_status.value,
                    current_use_status=None,
                    local_sync_allowed=False,
                    public_export_allowed=False,
                    research_only=True,
                )
            )
        return tuple(sorted(summaries, key=lambda item: item.source_id))

    def review_source(self, source_id: str) -> SourceReview:
        normalized = normalize_source_id(source_id)
        settings = self._load_settings().get(normalized)
        if settings is not None:
            review_path = settings.review_path or self._default_review_path(normalized)
            return SourceReview(
                source_id=normalized,
                approval_status=settings.approval_status.value,
                review_path=review_path,
                review_exists=self._review_exists(review_path),
                research_only=settings.approval_status not in SourcePolicy.LOCAL_SYNC_ALLOWLIST,
            )
        gated_source = self._load_gated().get(normalized)
        if gated_source is None:
            raise KeyError("unknown source")
        review_path = self._default_review_path(normalized)
        return SourceReview(
            source_id=normalized,
            approval_status=gated_source.approval_status.value,
            review_path=review_path,
            review_exists=self._review_exists(review_path),
            research_only=True,
        )

    def _load_settings(self) -> dict[str, SourceSettings]:
        values: dict[str, SourceSettings] = {}
        for path in sorted(self._settings_root.glob("*.yaml")):
            if path.name in {"_review-template.yaml", "permission-gated.yaml"}:
                continue
            source = load_source_settings(path)
            values[source.source_id] = source
        return values

    def _load_gated(self) -> PermissionGatedSourceCatalog:
        return load_permission_gated_catalog(self._settings_root / "permission-gated.yaml")

    def _default_review_path(self, source_id: str) -> str:
        return f"docs/03-data/source-reviews/{source_id}.md"

    def _review_exists(self, review_path: str) -> bool:
        candidate = self._root.joinpath(*review_path.split("/"))
        return candidate.is_file() and not candidate.is_symlink()


__all__ = ["ConfiguredSourceCatalog"]
