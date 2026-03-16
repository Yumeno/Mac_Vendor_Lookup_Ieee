# MAC Vendor Lookup IEEE

IEEE の公開割当一覧（MA-S / MA-M / MA-L）を用いて、MAC アドレス一覧 CSV に対して割当情報を付与するためのスクリプトです。

このツールは **メーカーや機器種別の推定** までは行わず、まずは **IEEE の割当情報を機械的に付与する** ことを目的としています。

---

## できること

- 入力 CSV から MAC アドレス列を読み取る
- MAC アドレスを正規化する
- IEEE の公開 CSV（MA-S / MA-M / MA-L）と照合する
- **MA-S → MA-M → MA-L の順で最長一致**させる
- 一致した割当情報を出力 CSV に追加する
- ローカル管理アドレス（U/L bit = 1）にフラグを付ける

---

## 前提

以下のファイルが必要です。

- Python 3.10 以降推奨
- スクリプト本体
  - `mac_vendor_lookup_ieee.py`
- IEEE の公開 CSV
  - `ma-l.csv`
  - `ma-m.csv`
  - `ma-s.csv`
- 入力 MAC 一覧 CSV
  - 例: `macs.csv`

IEEE の割当一覧は IEEE Registration Authority の公開データを使用してください。

---

## ディレクトリ構成例

```text
project/
├─ mac_vendor_lookup_ieee.py
├─ README.md
├─ ma-l.csv
├─ ma-m.csv
├─ ma-s.csv
└─ macs.csv
```

---

## 入力 CSV の形式

既定では、入力 CSV に **`mac` 列** がある前提です。

### 例

```csv
mac
00:11:22:33:44:55
ac-de-48-00-11-22
7C:D9:5C:12:34:56
DA:12:34:56:78:90
```

### 補足

以下のような表記はすべて受け付けます。

- `00:11:22:33:44:55`
- `00-11-22-33-44-55`
- `001122334455`
- `0011.2233.4455`

内部では **12 桁の 16 進大文字** に正規化して照合します。

---

## 実行方法

基本形は次のとおりです。

```bash
python mac_vendor_lookup_ieee.py \
  --input macs.csv \
  --output macs_with_ieee.csv \
  --ma-l ma-l.csv \
  --ma-m ma-m.csv \
  --ma-s ma-s.csv
```

### MAC 列名が `mac` ではない場合

たとえば列名が `mac_address` の場合は、`--mac-column` を指定します。

```bash
python mac_vendor_lookup_ieee.py \
  --input macs.csv \
  --output macs_with_ieee.csv \
  --mac-column mac_address \
  --ma-l ma-l.csv \
  --ma-m ma-m.csv \
  --ma-s ma-s.csv
```

---

## 照合ルール

MAC アドレスに対して、以下の順で照合します。

1. **MA-S**（36bit = 9 hex）
2. **MA-M**（28bit = 7 hex）
3. **MA-L**（24bit = 6 hex）

より長いプレフィックスを優先することで、可能な限り具体的な割当情報を採用します。

---

## 出力列

出力 CSV には、元の列に加えて次の列が追加されます。

- `normalized_mac`
  - 正規化後の MAC アドレス（12 桁の 16 進大文字）
- `is_locally_administered`
  - ローカル管理アドレスなら `1`、そうでなければ `0`
- `ieee_registry`
  - 一致した割当種別（`MA-S` / `MA-M` / `MA-L`）
- `ieee_prefix`
  - 一致したプレフィックス
- `ieee_assignment`
  - IEEE CSV 上の Assignment 値
- `ieee_organization`
  - 組織名
- `ieee_address`
  - 住所情報
- `ieee_country`
  - 国情報
- `lookup_status`
  - `matched` / `not_found` / `error`
- `lookup_note`
  - 補足情報やエラー内容

---

## 出力例

```csv
mac,normalized_mac,is_locally_administered,ieee_registry,ieee_prefix,ieee_assignment,ieee_organization,ieee_address,ieee_country,lookup_status,lookup_note
00:11:22:33:44:55,001122334455,0,MA-L,001122,001122,Example Corp,"1 Example St",US,matched,
DA:12:34:56:78:90,DA1234567890,1,,,,,,,not_found,no MA-S/MA-M/MA-L prefix match
```

---

## エラーになる例

次のような MAC は `lookup_status=error` になります。

- 16 進文字以外を除去したあと 12 桁にならない
- 空欄
- 列名指定が誤っている

例:

```csv
mac
INVALID
12345

```

---

## 注意点

### 1. これは「割当情報」の付与です

このツールが付けるのは、あくまで IEEE の割当情報です。  
**実際の機器メーカー名や機器種別を確定するものではありません。**

### 2. ローカル管理アドレスは要注意です

`is_locally_administered=1` のものは、ランダム MAC やローカル割当の可能性があります。  
その場合、IEEE の公開割当に一致しない、または一致しても実態把握に向かないことがあります。

### 3. IEEE の CSV 仕様変更に注意してください

CSV の列名は将来変更される可能性があります。  
本スクリプトは代表的な列名候補を広めに読む実装ですが、CSV の形式変更によっては調整が必要です。

---

## 典型的な使い方

棚卸しの初手としては、次の流れが扱いやすいです。

1. Aruba 等から MAC 一覧を CSV で出力する
2. このツールで IEEE 割当情報を付与する
3. `lookup_status` で未一致を確認する
4. `is_locally_administered` が `1` のものを優先的に点検する
5. その後に必要なら別工程でメーカー名推定や資産台帳照合を行う

---

## 補足

この README は、現時点でのスクリプト仕様に合わせて記述しています。  
スクリプト側の列名やオプションを変更した場合は、README も合わせて更新してください。

