# IR-Trigger

Home Assistant向けの軽量・高レスポンスな赤外線(IR)双方向統合システムです。  
リモコンの赤外線信号を受信してオートメーションのトリガーにするだけでなく、Home Assistant上の標準エンティティ（Light, MediaPlayer等）やボタンから赤外線を送信し、家電を直接操作することが可能です。

---

## 🚀 特徴

1. **双方向 IR 通信**
   - **[受信 (Receivers)](docs/receivers.md)**: 信号を正規化し、HAイベントおよびセンサーに即座に反映。
   - **[送信 (Transmitters)](docs/transmitters.md)**: Webhook や ESPHome、Nature Remo などを経由して、HA上のエンティティから赤外線を送信。
2. **Multi-State Machine (マルチ状態管理)**
   - 複数の `state_machines` を定義でき、AV機器や照明などの独立したモード管理が可能。
   - 二重発火防止ロジックを搭載し、正確なルーティングを実現。
3. **Auto-Domain Wrapper (代表エンティティ自動生成)**
   - リモコン定義に `domain` と `mapping` を追加するだけで、`light` や `media_player` 等の標準エンティティを自動生成。
4. **辞書エコシステム (テンプレートエンジン)**
   - `template: "型番"` 指定により、内蔵辞書やユーザー独自の辞書ファイルを読み込んで利用可能。
   - インターネット上の巨大な **Broadlink Base64 (`B64-`) コード資産** をそのまま流用可能なネイティブサポート。
5. **ハブ＆スポーク構造 (via_device)**
   - 送信機（ハブ）と家電デバイス（スポーク）をHAのデバイスレジストリ上で紐付け。
6. **動的エアコンプロトコル**
   - Pythonテンプレートから全状態フレームを生成し、対応リモコンの受信信号でClimate状態を同期。
   - Hitachi RAR-7A3（RAS-V22E/V25E/V28E/V36E/V40E2）を内蔵。

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

  Climate_Bedroom:
    name: "ベッドルームのエアコン"
    transmitter: tx_study
    receiver: rx_study_webhook # 同型機が複数ある場合の誤同期を防止
    template: "climate/RAR-7A3"

# 4. グローバル設定
global:
  repeat: ["TV_Study"] # 自動リピーター
  remap:
    "NEC-12345678": # 特定のボタンでサービスを呼ぶ
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

### Broadlink Base64 資産の流用
インターネット上のオープンなデータベース等で配布されている Broadlink 用の Base64 文字列（例: `JgBQAAAB...`）を、そのまま辞書ファイルに記述して利用できます。
コードの先頭に `B64-` を付けるだけで、自動的に HA や ESPHome、Nature Remo が解釈できる内部フォーマットに変換して送信されます。

また、既存のJSON形式のBase64辞書をIR-Trigger用のYAML形式に一括変換するスクリプトも同梱しています。
```bash
python3 tools/scripts/broadlink_json_to_yaml.py input.json output.yaml --domain climate
```

---

## 🛠️ 4. トラブルシューティング

現在、特に報告されている制限事項はありません。

---

## 🌡️ 5. Hitachi RAR-7A3

`template: "climate/RAR-7A3"` は、冷房・暖房・除湿・これっきり自動、6段階の風量、eco／セーブの組み合わせをClimateエンティティから送信します。上下・左右スイング、フィルター掃除、標準Climateに対応するモードがない「涼快」は同じデバイス配下のボタンになります。

RAR-7A3の受信フレームからClimate状態も同期します。複数室に同型機がある場合は、各デバイスへ `receiver`（文字列またはリスト）を指定し、別室の信号による誤同期を防いでください。スイングはリモコン自体がトグル信号しか送らないため、現在状態は追跡できません。

---

## 🚢 6. リリース

`VERSION` を正として、次のコマンドで `manifest.json` を同時更新します。

```bash
python tools/scripts/release_version.py set 1.1.0
python tools/scripts/release_version.py check
```

`main` のCI（単体テスト、HACS、hassfest）が成功してから同じ版の `v1.1.0` タグをpushします。タグ用CIはバージョン一致を再検証し、HACS用 `ir_trigger.zip` とGitHub Releaseを自動作成します。公開済みタグは移動せず、修正は新しい版としてリリースします。
