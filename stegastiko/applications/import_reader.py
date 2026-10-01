"""Read operator Excel import workbook (§9.2)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from openpyxl import load_workbook

from applications.import_template import TEMPLATE_VERSION

KEY_ROW = 2
DATA_ROW = 4
TABLE_DATA_START = 4


@dataclass
class ParsedImport:
    metadata: dict[str, Any]
    fields: dict[str, Any]
    children: list[dict[str, Any]] = field(default_factory=list)
    income_rows: list[dict[str, Any]] = field(default_factory=list)
    supporting_documents: list[dict[str, Any]] = field(default_factory=list)


def _cell_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    return value


def _read_metadata(ws) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        key = row[0]
        if not key:
            continue
        data[str(key)] = _cell_value(row[2] if len(row) > 2 else "")
    return data


def _read_horizontal(ws) -> dict[str, Any]:
    keys = [cell.value for cell in ws[KEY_ROW]]
    values = [_cell_value(cell.value) for cell in ws[DATA_ROW]]
    return {str(k): v for k, v in zip(keys, values) if k}


def _read_table(ws) -> list[dict[str, Any]]:
    keys = [cell.value for cell in ws[KEY_ROW]]
    keys = [str(k) for k in keys if k]
    rows: list[dict[str, Any]] = []
    for row in ws.iter_rows(min_row=TABLE_DATA_START, values_only=True):
        if not any(cell is not None and str(cell).strip() != "" for cell in row):
            break
        item = {}
        for idx, key in enumerate(keys):
            item[key] = _cell_value(row[idx]) if idx < len(row) else ""
        rows.append(item)
    return rows


def parse_import_workbook(source) -> ParsedImport:
    wb = load_workbook(source, data_only=True)
    required = ("Μεταδεδομένα", "Αίτηση", "Πρόσωπο1", "Διαμονή", "Δηλώσεις")
    for name in required:
        if name not in wb.sheetnames:
            raise ValidationError(f"Λείπει φύλλο «{name}».")

    metadata = _read_metadata(wb["Μεταδεδομένα"])
    version = str(metadata.get("template_version", "")).strip()
    if version != TEMPLATE_VERSION:
        raise ValidationError(
            f"Άγνωστη έκδοση προτύπου: «{version}» (αναμενόμενη {TEMPLATE_VERSION})."
        )

    fields: dict[str, Any] = {}
    fields.update(_read_horizontal(wb["Αίτηση"]))
    fields.update(_read_horizontal(wb["Πρόσωπο1"]))
    if "Πρόσωπο2" in wb.sheetnames:
        fields.update(_read_horizontal(wb["Πρόσωπο2"]))
    fields.update(_read_horizontal(wb["Διαμονή"]))
    fields.update(_read_horizontal(wb["Δηλώσεις"]))

    children = _read_table(wb["Τέκνα"]) if "Τέκνα" in wb.sheetnames else []
    income_rows = _read_table(wb["Εισοδήματα"]) if "Εισοδήματα" in wb.sheetnames else []
    supporting_documents = (
        _read_table(wb["Δικαιολογητικά"]) if "Δικαιολογητικά" in wb.sheetnames else []
    )

    return ParsedImport(
        metadata=metadata,
        fields=fields,
        children=children,
        income_rows=income_rows,
        supporting_documents=supporting_documents,
    )


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        raise ValidationError("Λείπει ημερομηνία.")
    return date.fromisoformat(text[:10])


def _parse_decimal(value) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ".").replace("€", "").strip())
    except InvalidOperation:
        return Decimal("0")
