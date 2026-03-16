#!/usr/bin/env python3
"""
IEEE の MA-S / MA-M / MA-L CSV を読み込み、MAC アドレス一覧に対して
一致した割当情報を付与して CSV 出力するスクリプト。

想定用途:
- Aruba 等からエクスポートした MAC アドレス一覧の棚卸し補助
- ベンダー推定の前段として、まず IEEE 割当情報を機械的に付与する

仕様:
- 入力 MAC を正規化して 12 桁の 16 進大文字へ変換
- MA-S(36bit=9 hex) → MA-M(28bit=7 hex) → MA-L(24bit=6 hex) の順で最長一致
- 一致した割当種別・プレフィックス・組織名などを出力
- ローカル管理アドレス(U/L bit=1)はフラグを付与

前提:
- IEEE 公開 CSV をローカルに保存して使用する
- CSV の列名は将来変わる可能性があるため、代表的な候補名を広めに吸収する

使い方例:
    python mac_vendor_lookup_ieee.py \
        --input macs.csv \
        --output macs_with_ieee.csv \
        --ma-l ma-l.csv \
        --ma-m ma-m.csv \
        --ma-s ma-s.csv

入力 CSV の既定列名は `mac`。
別名を使う場合は --mac-column を指定する。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

NON_HEX_RE = re.compile(r"[^0-9A-Fa-f]")


@dataclass(frozen=True)
class RegistrySpec:
    name: str
    prefix_hex_len: int
    csv_path: Path


@dataclass
class RegistryRow:
    registry: str
    prefix: str
    organization: str
    assignment: str
    address: str
    country: str
    raw: Dict[str, str]


@dataclass
class LookupHit:
    registry: str
    prefix: str
    organization: str
    assignment: str
    address: str
    country: str


def normalize_mac(mac: str) -> str:
    """MAC アドレス文字列を 12 桁の 16 進大文字へ正規化する。"""
    normalized = NON_HEX_RE.sub("", mac).upper()
    if len(normalized) != 12:
        raise ValueError(f"invalid MAC length after normalization: {mac!r} -> {normalized!r}")
    return normalized


def is_locally_administered(mac12: str) -> bool:
    """U/L bit が 1 ならローカル管理アドレス。"""
    first_octet = int(mac12[:2], 16)
    return bool(first_octet & 0b00000010)


def candidate_value(row: Dict[str, str], keys: Iterable[str]) -> str:
    """複数候補列から最初に見つかった値を返す。"""
    for key in keys:
        value = row.get(key)
        if value is not None:
            stripped = value.strip()
            if stripped:
                return stripped
    return ""


def extract_prefix(row: Dict[str, str], prefix_hex_len: int) -> str:
    """IEEE CSV の行からプレフィックスを抽出する。"""
    prefix_candidates = (
        "Assignment",
        "MA-L",
        "MA-M",
        "MA-S",
        "OUI",
        "CID",
        "Company ID",
    )
    for key in prefix_candidates:
        value = row.get(key)
        if not value:
            continue
        compact = NON_HEX_RE.sub("", value).upper()
        if len(compact) >= prefix_hex_len:
            return compact[:prefix_hex_len]
    return ""


def load_registry(spec: RegistrySpec) -> Dict[str, RegistryRow]:
    """IEEE 公開 CSV から prefix -> RegistryRow の辞書を構築する。"""
    table: Dict[str, RegistryRow] = {}

    with spec.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prefix = extract_prefix(row, spec.prefix_hex_len)
            if not prefix:
                continue

            organization = candidate_value(
                row,
                (
                    "Organization Name",
                    "Organization",
                    "Assignment Organization Name",
                    "Registrant",
                ),
            )

            assignment = candidate_value(row, ("Assignment", "MA-L", "MA-M", "MA-S", "OUI", "CID", "Company ID"))
            address = candidate_value(
                row,
                (
                    "Organization Address",
                    "Address",
                    "Company Address",
                ),
            )
            country = candidate_value(row, ("Country", "Country Code"))

            table[prefix] = RegistryRow(
                registry=spec.name,
                prefix=prefix,
                organization=organization,
                assignment=assignment,
                address=address,
                country=country,
                raw=row,
            )

    return table


def build_registry_tables(ma_l_path: Path, ma_m_path: Path, ma_s_path: Path) -> List[Tuple[RegistrySpec, Dict[str, RegistryRow]]]:
    """MA-S → MA-M → MA-L の順で照合するためのテーブル群を返す。"""
    specs = [
        RegistrySpec(name="MA-S", prefix_hex_len=9, csv_path=ma_s_path),
        RegistrySpec(name="MA-M", prefix_hex_len=7, csv_path=ma_m_path),
        RegistrySpec(name="MA-L", prefix_hex_len=6, csv_path=ma_l_path),
    ]

    tables: List[Tuple[RegistrySpec, Dict[str, RegistryRow]]] = []
    for spec in specs:
        tables.append((spec, load_registry(spec)))
    return tables


def lookup_mac(mac12: str, tables: List[Tuple[RegistrySpec, Dict[str, RegistryRow]]]) -> Optional[LookupHit]:
    """MAC を最長一致で照合し、ヒットがあれば返す。"""
    for spec, table in tables:
        prefix = mac12[: spec.prefix_hex_len]
        row = table.get(prefix)
        if row is not None:
            return LookupHit(
                registry=row.registry,
                prefix=row.prefix,
                organization=row.organization,
                assignment=row.assignment,
                address=row.address,
                country=row.country,
            )
    return None


def enrich_csv(
    input_csv: Path,
    output_csv: Path,
    mac_column: str,
    tables: List[Tuple[RegistrySpec, Dict[str, RegistryRow]]],
) -> None:
    """入力 CSV に IEEE 割当情報を付与して出力する。"""
    with input_csv.open("r", encoding="utf-8-sig", newline="") as fin, \
         output_csv.open("w", encoding="utf-8", newline="") as fout:

        reader = csv.DictReader(fin)
        if not reader.fieldnames:
            raise ValueError("input CSV has no header")
        if mac_column not in reader.fieldnames:
            raise ValueError(f"MAC column not found: {mac_column!r}; available={reader.fieldnames}")

        extra_fields = [
            "normalized_mac",
            "is_locally_administered",
            "ieee_registry",
            "ieee_prefix",
            "ieee_assignment",
            "ieee_organization",
            "ieee_address",
            "ieee_country",
            "lookup_status",
            "lookup_note",
        ]
        fieldnames = list(reader.fieldnames) + [f for f in extra_fields if f not in reader.fieldnames]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            raw_mac = row.get(mac_column, "")
            try:
                mac12 = normalize_mac(raw_mac)
                row["normalized_mac"] = mac12
                row["is_locally_administered"] = "1" if is_locally_administered(mac12) else "0"

                hit = lookup_mac(mac12, tables)
                if hit:
                    row["ieee_registry"] = hit.registry
                    row["ieee_prefix"] = hit.prefix
                    row["ieee_assignment"] = hit.assignment
                    row["ieee_organization"] = hit.organization
                    row["ieee_address"] = hit.address
                    row["ieee_country"] = hit.country
                    row["lookup_status"] = "matched"
                    row["lookup_note"] = ""
                else:
                    row["ieee_registry"] = ""
                    row["ieee_prefix"] = ""
                    row["ieee_assignment"] = ""
                    row["ieee_organization"] = ""
                    row["ieee_address"] = ""
                    row["ieee_country"] = ""
                    row["lookup_status"] = "not_found"
                    row["lookup_note"] = "no MA-S/MA-M/MA-L prefix match"
            except Exception as e:
                row["normalized_mac"] = ""
                row["is_locally_administered"] = ""
                row["ieee_registry"] = ""
                row["ieee_prefix"] = ""
                row["ieee_assignment"] = ""
                row["ieee_organization"] = ""
                row["ieee_address"] = ""
                row["ieee_country"] = ""
                row["lookup_status"] = "error"
                row["lookup_note"] = str(e)

            writer.writerow(row)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MAC アドレス一覧に IEEE MA-S/MA-M/MA-L 情報を付与する")
    parser.add_argument("--input", required=True, type=Path, help="入力 CSV パス")
    parser.add_argument("--output", required=True, type=Path, help="出力 CSV パス")
    parser.add_argument("--mac-column", default="mac", help="入力 CSV 上の MAC 列名 (default: mac)")
    parser.add_argument("--ma-l", required=True, type=Path, help="IEEE MA-L CSV パス")
    parser.add_argument("--ma-m", required=True, type=Path, help="IEEE MA-M CSV パス")
    parser.add_argument("--ma-s", required=True, type=Path, help="IEEE MA-S CSV パス")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    tables = build_registry_tables(
        ma_l_path=args.ma_l,
        ma_m_path=args.ma_m,
        ma_s_path=args.ma_s,
    )

    enrich_csv(
        input_csv=args.input,
        output_csv=args.output,
        mac_column=args.mac_column,
        tables=tables,
    )

    print(f"done: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
