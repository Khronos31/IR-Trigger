# IR-Trigger

Home Assistant向けの軽量・高レスポンスな赤外線(IR)双方向統合システムです。  
リモコンの赤外線信号を受信してオートメーションのトリガーにするだけでなく、Home Assistant上のボタンエンティティから赤外線を送信し、家電を直接操作することが可能です。

---

## 🚀 特徴

1.  **双方向 IR 通信**
    -   **受信**: 信号を正規化し、HAイベントおよびセンサーに即座に反映。
    -   **送信**: `pyusb`（Local USB）や ESPHome 経由で、HA上のボタンから赤外線を送信。
2.  **ハブ＆スポーク構造 (via_device)**
    -   送信機（ハブ）と家電デバイス（スポーク）をHAのデバイスレジストリ上で紐付け、直感的な管理を実現。
3.  **動的ルーティングとバインディング**
    -   リモコンと家電をYAMLで「バインド」するだけで、ボタン1つで自動的な中継や remapping が可能。
4.  **自動リピーター (Auto-Repeater)**
    -   受信した信号を別の送信機から自動的に再送信。無限ループ防止機能（`local_receivers`）を搭載。
5.  **HA再起動不要の動的更新**
    -   サービス `ir_trigger.reload` で、YAML設定をダウンタイムなしで即座に反映。

---

## 📦 1. インストール

### カスタム統合のインストール
1.  HACSから、カスタムリポジリ `https://github.com/Khronos31/IR-Trigger` を追加し、ダウンロードします。
2.  `configuration.yaml` に以下を追記し、Home Assistant を再起動します。
    ```yaml
    ir_trigger:
    ```

### 依存関係 (Local USB 送信機を使用する場合)
`pyusb` が必要です（HACSインストール時に自動的に含まれますが、OSレベルで `libusb` が必要です）。

---

## 📝 2. 設定 (IR-Trigger.yaml)

HAの設定ディレクトリ（`config/` 直下）に `IR-Trigger.yaml` を作成します。

```yaml
# IR-Trigger.yaml
---

## 🔌 4. 受信機（エッジ）のセットアップ

環境に合わせて以下のいずれかの方法で受信機をセットアップします。

### パターンA: Home Assistant OSに直挿しする場合 (AD00020P用 アドオン)
Bit Trade One AD00020P をHAOSホストマシンに直接USB接続する場合の設定です。

1. Home Assistant の「アドオンストア」を開き、右上のメニューから「リポジトリ」を選択。
2. このリポジトリのURL `https://github.com/Khronos31/IR-Trigger` を追加します。
3. リストに表示される **`IR-Trigger USB Daemon`** をインストールします。
4. アドオンの「設定」タブを開き、以下のオプションを設定します。
   - `webhook_url`: `http://homeassistant:8123/api/webhook/ir_trigger_webhook`
   - `receiver_name`: 任意の識別名（例: `LivingRoom_AD00020P`）
5. アドオンを「起動」します。

### パターンB: M5StickS3 / M5StickC Plus を使う場合 (ESPHome)
M5Stick等のGroveポート(GPIO33)に赤外線レシーバーユニットを接続して使用する場合の設定です。

1. `edge_scripts/m5stick_s3_ir.yaml` を参考に、ESPHomeのYAMLを作成します。
2. ESPHomeがネイティブにHAの `ir_trigger_received` イベントを発火させるため、Webhookの設定は不要です。

### パターンC: Raspberry Pi などの Linux機を使う場合 (Python デーモン)
Linux機にAD00020Pを接続し、ネットワーク経由でHAに信号を送信する場合の設定です。

1. 依存ライブラリをインストールします。
   ```bash
   sudo apt install python3-pip libusb-1.0-0
   pip3 install pyusb requests --break-system-packages
   ```
2. スクリプトを実行します。
   ```bash
   python3 edge_scripts/ir_daemon.py \
     --url http://<HAのIPアドレス>:8123/api/webhook/ir_trigger_webhook \
     --receiver Bedroom_AD00020P
   ```
3. バックグラウンドで自動起動させる場合は、同梱の `edge_scripts/ir-daemon.service` を `/etc/systemd/system/` にコピーし、`systemctl enable ir-daemon.service` で登録してください。
