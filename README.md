# IR-Trigger

Home Assistant向けの軽量・高レスポンスな赤外線(IR)双方向統合システムです。  
リモコンの赤外線信号を受信してオートメーションのトリガーにするだけでなく、Home Assistant上の標準エンティティ（Light, MediaPlayer等）やボタンから赤外線を送信し、家電を直接操作することが可能です。

---

## 🚀 特徴

1. **双方向 IR 通信**
   - **受信**: 信号を正規化し、HAイベントおよびセンサーに即座に反映。
   - **送信**: `pyusb`（Local USB）や ESPHome 経由で、HA上のエンティティから赤外線を送信。
2. **Auto-Domain Wrapper (代表エンティティ自動生成)**
   - リモコン定義に `domain` と `mapping` を追加するだけで、`light` や `media_player` 等の標準エンティティを自動生成。
   - 音声アシスタント（Google Home等）からの操作に完全対応。
3. **辞書エコシステム (テンプレートエンジン)**
   - `template: "型番"` 指定により、外部の共通辞書ファイルを読み込んで利用可能。
   - 公式辞書とユーザー独自の辞書をディープマージし、柔軟なカスタマイズが可能。
4. **ハブ＆スポーク構造 (via_device)**
   - 送信機（ハブ）と家電デバイス（スポーク）をHAのデバイスレジストリ上で紐付け、直感的な管理を実現。
5. **動的ルーティングとバインディング**
   - リモコンと家電をYAMLで「バインド」するだけで、ボタン1つで自動的な中継や remapping が可能。
6. **HA再起動不要の動的更新**
   - サービス `ir_trigger.reload` で、YAML設定や辞書ファイルをダウンタイムなしで即座に反映。

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

HAの設定ディレクトリ（`config/` 直下）に `IR-Trigger.yaml` を作成します。

```yaml
# IR-Trigger.yaml

# モード切替用のエンティティ（任意）
mode_entity: input_select.ir_remote_mode

# 1. 送信機（ハブ）の定義
transmitters:
  tx_study_ad00020p:
    name: "スタディの送信機"
    type: local_usb
    index: 0
    local_receivers: ["rx_study_ad00020p"]

# 2. 家電デバイス（スポーク）の定義
devices:
  TV_Study:
    name: "スタディのテレビ"
    transmitter: tx_study_ad00020p
    template: "J-MX100RC" # 👈 外部辞書からボタンやドメイン設定を読み込む

  Light_Living:
    name: "リビングの照明"
    transmitter: tx_study_ad00020p
    template: "IR-A04HS"

# 3. ルーティングとモード設定
modes:
  always:
    repeat: ["TV_Study"]
  TV:
    bind:
      - source: Master_Remote
        target: TV_Study
```

---

## 📖 3. 辞書ファイル (Templates)

共通のリモコン定義を以下のディレクトリに配置することで、複数のデバイスから使い回すことができます。

- **公式辞書:** `custom_components/ir_trigger/remotes/`
- **ユーザー辞書:** `config/ir_trigger_remotes/`

### 辞書ファイルの例 (`J-MX100RC.yaml`)
```yaml
domain: "media_player"
mapping:
  turn_on: "POWER"
  turn_off: "POWER"
  volume_up: "VOL_UP"
  volume_down: "VOL_DOWN"
buttons:
  POWER: NEC_80EA12ED
  VOL_UP: NEC_80EA1AE5
  ...
```

---

## 📡 4. 動作仕様

### デバイスとエンティティ
- **代表エンティティ**: `domain` が指定された場合、そのドメインのエンティティが作られます（Optimistic Update 対応）。
- **ボタン**: `buttons` で定義された各機能がボタンエンティティとして自動生成されます。これらは代表エンティティと共存します。

### イベント
信号受信時、`ir_trigger_received` イベントが発火します。

---

## 🛠️ 5. サービス

- **`ir_trigger.reload`**: `IR-Trigger.yaml` および辞書ファイルを即座に再読み込みします。
- **`ir_trigger.send_code`**: 任意の送信機から任意のコードを直接送信します。

---

## 🛠️ トラブルシューティング

一部の受信機で反応が悪い場合、デバイス設定で `force_aeha_tx: true` を指定することで、NECフォーマットをAEHAに変換して送信し、回避できる可能性があります。
