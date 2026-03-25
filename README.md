# IR-Trigger

Home Assistant向けの軽量・高レスポンスな赤外線(IR)双方向統合システムです。  
リモコンの赤外線信号を受信してオートメーションのトリガーにするだけでなく、Home Assistant上のボタンエンティティから赤外線を送信し、家電を直接操作することが可能です。

---

## 🚀 特徴

1. **双方向 IR 通信**
   - **受信**: 信号を正規化し、HAイベントおよびセンサーに即座に反映。
   - **送信**: `pyusb`（Local USB）や ESPHome 経由で、HA上のボタンから赤外線を送信。
2. **ハブ＆スポーク構造 (via_device)**
   - 送信機（ハブ）と家電デバイス（スポーク）をHAのデバイスレジストリ上で紐付け、直感的な管理を実現。
3. **動的ルーティングとバインディング**
   - リモコンと家電をYAMLで「バインド」するだけで、ボタン1つで自動的な中継や remapping が可能。
4. **自動リピーター (Auto-Repeater)**
   - 受信した信号を別の送信機から自動的に再送信。無限ループ防止機能（`local_receivers`）を搭載。
5. **HA再起動不要の動的更新**
   - サービス `ir_trigger.reload` で、YAML設定をダウンタイムなしで即座に反映。

---

## 📦 1. インストール

### カスタム統合のインストール
1. HACSから、カスタムリポジトリ `https://github.com/Khronos31/IR-Trigger` を追加し、ダウンロードします。
2. `configuration.yaml` に以下を追記し、Home Assistant を再起動します。
   ```yaml
   ir_trigger:
   ```

### 依存関係 (Local USB 送信機を使用する場合)
`pyusb` が必要です。

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
  J-MX100RC:
    name: "スタディのテレビ"
    transmitter: tx_study_ad00020p
    buttons:
      POWER: NEC_80EA12ED
      VOL_UP: NEC_80EA1AE5

  C-RT1:
    name: "マスターリモコン"
    buttons:
      POWER: NEC_50AF17E8

# 3. ルーティングとモード設定
modes:
  always:
    repeat: ["J-MX100RC"]
  TV:
    bind: { source: C-RT1, target: J-MX100RC }
```

---

## 📡 3. 動作仕様

### デバイスとエンティティ
- **送信機**: 独立したデバイスとして登録されます。
- **家電デバイス**: `via_device` プロパティにより、送信機の下位デバイスとして表示されます。
- **ボタン**: `buttons` で定義された各機能がボタンエンティティとして自動生成されます。

### イベント
信号受信時、`ir_trigger_received` イベントが発火します。オートメーションのトリガーに利用可能です。

---

## 🛠️ 4. サービス

- **`ir_trigger.reload`**: `IR-Trigger.yaml` の内容を即座に再読み込みします。
- **`ir_trigger.send_code`**: 任意の送信機から任意のコードを直接送信します。

---

## 🔌 5. 受信機（エッジ）のセットアップ
各エッジスクリプト（ESPHome や Python デーモン）を使用して HA Webhook または API へ信号を飛ばしてください。詳細は `docs/` を参照してください。
