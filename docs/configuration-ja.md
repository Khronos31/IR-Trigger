# 詳細設定ガイド (Configuration Guide)

`IR-Trigger.yaml` を使用した送信機・受信機の管理、マルチ状態管理、および高度な設定方法について解説します。
---

## 1. 全体構造

```yaml
transmitters: ...    # 1. 送信機（物理デバイス）の定義
receivers: ...       # 2. 受信機（物理デバイス）の定義
devices: ...         # 3. 家電デバイス（仮想エンティティ）の定義
global: ...          # 4. グローバル設定（常に有効なリピート・リマップ）
state_machines: ...  # 5. ステートマシン（モード別の動的ルーティング）
```

---

## 2. 物理デバイス定義

### 送信機 (`transmitters`)
HA から赤外線を発信するデバイスを指定します。
- `type`: `esphome`, `nature_remo`, `webhook`, `broadlink`, `mock`
- `local_receivers`: この送信機の近くにある受信機 ID のリスト。ハウリング（無限ループ）防止用。

### 受信機 (`receivers`)
赤外線信号を検知するデバイスを指定します。
- `type`: `webhook`, `nature_remo`
- Webhook 型の場合、受信機の ID がそのまま Webhook ID となり、`/api/webhook/<receiver_id>` で信号を待ち受けます。

---

## 3. 家電デバイス定義 (`devices`)

家電を Home Assistant のエンティティとして定義します。
- `transmitter`: 送信に使用する `transmitters` 内の ID。
- `template`: 使用するリモコン辞書ファイルのパス。
  - **重要**: `media_player/J-MX100RC` のように、カテゴリディレクトリ名を含めて指定してください（拡張子 `.yaml` は不要）。

### 辞書ファイルの記述フォーマット
辞書ファイル内では、ボタン名と対応する赤外線コードを定義します。以下の2種類のフォーマットに対応しています。

1. **IRremoteESP8266 準拠のHEXコード** (推奨)
   - 形式: `プロトコル名-HEX文字列`
   - 例: `NEC-FF00FF86`

2. **Broadlink Base64 フォーマット** (`B64-` プレフィックス)
   - 形式: `B64-Base64文字列`
   - 例: `B64-JgBGAJKVDg4ODg4O...`
   - インターネット上に数多く存在するエアコン等のBase64コードをそのままコピペして利用できます。

> **💡 ヒント:** 既存の Base64 をまとめた JSON ファイルがある場合、付属のスクリプトで一括変換できます。
> `python3 tools/scripts/broadlink_json_to_yaml.py aircon_codes.json aircon.yaml --domain climate`

---

## 4. ルーティングとステートマシン

### グローバル設定 (`global`)
- `repeat`: 受信時に自動で再送（リピート）するデバイス ID のリスト。
- `remap`: 特定のコードに対するグローバルなアクション。マッチすると、それ以降の評価を中断します。

### ステートマシン (`state_machines`)
複数の独立した状態管理マシンを定義できます。
- `mode_entity`: 状態判定に使用するエンティティ（例: `input_select.av_mode`）。
- `modes`: モードごとの `remap` と `bind` 定義。

---

## 5. 評価順序と排他制御

信号受信時の評価順序は以下の通りです。
1.  **Repeat**: `global.repeat` をチェックし、該当すればリピート送信（独立して動作）。
2.  **Global Remap**: マッチすれば実行し、**以降の全評価（ステートマシン含む）を中断します。**
3.  **State Machines**: 各ステートマシンを順番に評価。1つのマシン内でマッチするとそのマシンの評価を終了し、次のステートマシンに移ります。

---

## 6. 設定の反映
ファイルを編集した後は、Home Assistant の開発者ツールなどで `ir_trigger.reload` サービスを実行してください。再起動なしで即座に反映されます。
