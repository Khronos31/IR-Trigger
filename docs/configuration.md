# 詳細設定ガイド (Configuration Guide)

`IR-Trigger.yaml` を使用した高度な設定方法について解説します。

---

## 1. 送信機 (`transmitters`)

送信機（ハブとなるデバイス）を定義します。

| キー | 型 | 内容 |
| :--- | :--- | :--- |
| `name` | string | Home Assistant 上での表示名 |
| `type` | string | `local_usb`, `esphome`, `webhook` |
| `index` | int | USB デバイスのインデックス（0から開始） |
| `entity_id` | string | ESPHome 送信機の場合のリモートエンティティID |
| `url` | string | Webhook 送信機の場合の送信先URL |
| `local_receivers` | list | この送信機の近くにある受信機のリスト（ループ防止用） |

---

## 2. デバイス (`devices`)

操作対象となる家電（スポーク）を定義します。

| キー | 型 | 内容 |
| :--- | :--- | :--- |
| `name` | string | Home Assistant 上での表示名 |
| `transmitter` | string | 使用する送信機の ID（`transmitters` で定義したもの） |
| `buttons` | dict | ボタン名と赤外線コードのマップ |

**ボタン名の命名規則:** `NEC_56A912ED` のように、`プロトコル_コード` 形式で記述します。

---

## 3. モードとルーティング (`modes`)

状況に応じた動的な動作を定義します。

### `repeat` (自動リピーター)
指定したデバイスのボタンが押された（＝受信機が検知した）際、自動的にそのデバイスに紐付けられた送信機から同じ信号を再送します。
```yaml
modes:
  always:
    repeat: ["TV_Living", "AC_Office"]
```

### `bind` (動的バインディング)
特定のリモコン（ソース）の入力を、別の家電（ターゲット）の操作へ動的に振り向けます。
```yaml
modes:
  Movie:
    bind:
      source: Master_Remote
      target: Projector_Screen
```

---

## 4. サービス再読み込み
設定を変更した後は、HAのサービス `ir_trigger.reload` を実行してください。
