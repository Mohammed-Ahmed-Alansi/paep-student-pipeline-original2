"""Integrate source-validated student data from the pipeline sources."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


OUTPUT_COLUMNS = [
    "student_id",
    "student_name",
    "age",
    "major",
    "city",
    "gpa",
    "attendance",
    "status",
    "course_name",
    "credit_hours",
    "semester",
    "score",
]


class DataIntegrationError(ValueError):
    """Raised when integration cannot safely combine source data."""


def _ensure_unique_student_ids(data: pd.DataFrame, source_name: str) -> None:
    duplicate_mask = data["student_id"].duplicated(keep=False)
    if not duplicate_mask.any():
        return

    duplicates = data.loc[duplicate_mask, "student_id"].tolist()
    raise DataIntegrationError(
        f"{source_name} data contains duplicate student_id values that would "
        f"multiply rows during integration: {duplicates}"
    )


def integrate_data(
    csv_data: pd.DataFrame,
    api_data: pd.DataFrame,
    database_data: pd.DataFrame,
) -> pd.DataFrame:
    """Return records shared by CSV, API, and database sources.

    Inputs are expected to have already passed source validation and cleaning.
    Integration only joins records by ``student_id`` and preserves source
    values as received.
    """
    for source_name, data in (
        ("CSV", csv_data),
        ("API", api_data),
        ("database", database_data),
    ):
        _ensure_unique_student_ids(data, source_name)

    integrated = (
        csv_data.copy()
        .merge(api_data.copy(), on="student_id", how="inner", validate="one_to_one")
        .merge(
            database_data.copy(),
            on="student_id",
            how="inner",
            validate="one_to_one",
        )
    )

    return integrated.loc[:, OUTPUT_COLUMNS]


def enrich_with_optional_sources(
    core_data: pd.DataFrame,
    supplemental_sources: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Left-join compatible supplemental sources without dropping core students.

    Supplemental sources must contain one row per ``student_id`` and may not
    overwrite columns already supplied by the core CSV/API/SQLite integration.
    A left join is deliberate: optional profile data should enrich matching
    students, not decide which academic rows survive.
    """
    enriched = core_data.copy(deep=True)
    _ensure_unique_student_ids(enriched, "core")

    for source_name, data in supplemental_sources.items():
        if "student_id" not in data.columns:
            raise DataIntegrationError(
                f"{source_name} data is missing the student_id column"
            )
        _ensure_unique_student_ids(data, source_name)
        overlapping = sorted(
            set(enriched.columns).intersection(data.columns).difference({"student_id"})
        )
        if overlapping:
            columns = ", ".join(overlapping)
            raise DataIntegrationError(
                f"{source_name} data would overwrite existing columns: {columns}"
            )
        enriched = enriched.merge(
            data.copy(deep=True),
            on="student_id",
            how="left",
            validate="one_to_one",
            sort=False,
        )

    return enriched
