# 詳細設定ガイド (Configuration Guide)

`IR-Trigger.yaml` を使用した高度な設定方法について解説します。

---

## 1. 全体設定

| キー | 型 | 内容 |
| :--- | :--- | :--- |
| `mode_entity` | string | (任意) モード判定に使用する HA エンティティ ID (例: `input_select.house_mode`) |

---

## 2. 送信機 (`transmitters`)

物理的な赤外線送信デバイス（ハブ）を定義します。

| キー | 型 | 内容 |
| :--- | :--- | :--- |
| `name` | string | Home Assistant 上での表示名 |
| `type` | string | `local_usb` (AD00020P等), `esphome` |
| `index` | int | (`type: local_usb` 時) USB デバイスのインデックス（通常は 0） |
| `entity_id` | string | (`type: esphome` 時) ESPHome の `remote_transmitter` エンティティ ID |
| `local_receivers` | list | この送信機の信号を直接拾ってしまう受信機の名前。無限ループ防止に使用します。 |

---

## 3. 家電デバイス (`devices`)

操作対象となる家電（スポーク）を定義します。

| キー | 型 | 内容 |
| :--- | :--- | :--- |
| `name` | string | Home Assistant 上での表示名 |
| `transmitter` | string | 使用する送信機の ID（`transmitters` セクションのキー） |
| `force_aeha_tx` | bool | (任意) 送信時に NEC フォーマットを AEHA に変換するかどうか (デフォルト: `false`) |
| `buttons` | dict | ボタン名と赤外線コードのマップ |

**赤外線コードの形式:** `プロトコル_コード` (例: `NEC_80EA12ED`, `AEHA_XXXX`)

---

## 4. モードとルーティング (`modes`)

状況（`mode_entity` の状態）に応じた動的な動作を定義します。

### `always` モード
常に有効な特別なモードです。

### `repeat` (自動リピーター)
指定したデバイスの信号を受信した際、同じ信号を自動的に再送します。
```yaml
modes:
  always:
    repeat: ["tv_living"]
```

### `bind` (動的バインディング)
ソース（リモコン等）の各ボタンを、対象デバイスの同じボタン名へ一括で紐付けます。
```yaml
modes:
  Theater:
    bind:
      - source: general_remote
        target: projector
```

### `remap` (詳細リマッピング)
特定のコードを受信した際に、別の赤外線コードを送信したり、HA サービスを呼び出したりします。

**赤外線送信の例:**
```yaml
modes:
  always:
    remap:
      NEC_12345678: 
        transmitter: tx_main
        code: NEC_ABCDEF00
```

**HA サービス呼び出しの例:**
```yaml
modes:
  always:
    remap:
      NEC_88888888:
        service: light.toggle
        target:
          entity_id: light.living_room
```

---

## 5. 設定の反映
`IR-Trigger.yaml` を編集した後は、Home Assistant のサービス `ir_trigger.reload` を実行することで、再起動なしで設定を即座に反映できます。

