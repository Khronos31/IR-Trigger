# IR-Trigger

Home Assistant向けの軽量・高レスポンスな赤外線(IR)双方向統合システムです。  
リモコンの赤外線信号を受信してオートメーションのトリガーにするだけでなく、Home Assistant上の標準エンティティ（Light, MediaPlayer等）やボタンから赤外線を送信し、家電を直接操作することが可能です。

---

## 🚀 特徴

1. **双方向 IR 通信**
   - **受信**: 信号を正規化し、HAイベントおよびセンサーに即座に反映。
   - **送信**: ESPHome や Nature Remo など経由で, HA上のエンティティから赤外線を送信。
2. **Multi-State Machine (マルチ状態管理)**
   - 複数の `state_machines` を定義でき、AV機器や照明などの独立したモード管理が可能。
   - 二重発火防止ロジックを搭載し、正確なルーティングを実現。
3. **Auto-Domain Wrapper (代表エンティティ自動生成)**
   - リモコン定義に `domain` と `mapping` を追加するだけで、`light` や `media_player` 等の標準エンティティを自動生成。
4. **辞書エコシステム (テンプレートエンジン)**
   - `template: "型番"` 指定により、内蔵辞書やユーザー独自の辞書ファイルを読み込んで利用可能。
5. **ハブ＆スポーク構造 (via_device)**
   - 送信機（ハブ）と家電デバイス（スポーク）をHAのデバイスレジストリ上で紐付け。

---

## 📦 1. インストール

### カスタム統合のインストール
1. HACSから、カスタムリポジトリ `https://github.com/Khronos31/IR-Trigger` を追加し、ダウンロードします。
2. `configuration.yaml` に以下を追記し、Home Assistant を再起動します。
   ```yaml
   ir_trigger:
   ```

---

## 📝 2. 設定 (IR-Trigger.yaml)

```yaml
# 1. 送信機 (Transmitters) の定義
transmitters:
  tx_study:
    name: "スタディの送信機"
    type: esphome
    node_name: "atom_s3_study"
    local_receivers: ["rx_study_webhook"] # 無限ループ防止

# 2. 受信機 (Receivers) の定義
receivers:
  rx_study_webhook:
    name: "スタディのWebhook受信機"
    type: webhook
  rx_living_esp:
    name: "リビングのESP受信機"
    type: webhook # /api/webhook/rx_living_esp で待機

# 3. 家電デバイス (Devices) の定義
devices:
  TV_Study:
    name: "スタディのテレビ"
    transmitter: tx_study
    template: "media_player/J-MX100RC" # ディレクトリを含めた明示的な指定

# 4. グローバル設定
global:
  repeat: ["TV_Study"] # 自動リピーター
  remap:
    "NEC_12345678": # 特定のボタンでサービスを呼ぶ
      - service: light.toggle
        target: { entity_id: light.living }

# 5. ステートマシン（モードに応じた動的ルーティング）
state_machines:
  - name: "Study AV"
    mode_entity: input_select.ir_remote_mode
    modes:
      TV:
        bind:
          - { source: Master_Remote, target: TV_Study }
```

---

## 📖 3. 辞書ファイル (Templates)

共有のリモコン定義を以下のディレクトリに配置できます。設定ファイルでは、これらのディレクトリからの相対パス（`.yaml` 無し）を指定してください。

- **内蔵辞書 (Built-in):** `custom_components/ir_trigger/remotes/`
- **ユーザー辞書 (Custom):** `config/ir_trigger_remotes/`

📚 対応リモコン一覧（内蔵辞書）はこちら:  
https://github.com/Khronos31/IR-Trigger/tree/main/custom_components/ir_trigger/remotes  

---

## 🛠️ 4. トラブルシューティング

現在、特に報告されている制限事項はありません。
