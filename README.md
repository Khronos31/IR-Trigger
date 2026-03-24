# IR-Trigger

Home Assistant向けの軽量・高レスポンスな赤外線(IR)トリガー統合システムです。  
リモコンの赤外線信号を受信し、それをHome Assistant上のイベントおよびセンサーとして即座に反映します。

GUIによる複雑な学習モードを排除し、**KISS原則（Keep It Simple, Stupid）** に基づいた、シンプルでハッカブルなアーキテクチャを採用しています。

---

## 🚀 特徴

1. **エッジ処理型アーキテクチャ**
   - 信号の判定・文字列正規化はエッジ（ESP32やLinuxデーモン）で行い、HA本体の負荷を極限まで減らします。
2. **KISS原則の辞書引き**
   - 受信した信号（例: `NEC_56A9718E`）をシンプルなYAML辞書 (`IR-Trigger.yaml`) と照合し、「コントローラー名」と「ボタン名」に変換してHAへ渡します。
3. **HA再起動不要**
   - 辞書ファイル (`IR-Trigger.yaml`) を変更した際は、サービス `ir_trigger.reload` を実行するだけで即座に反映されます。
4. **マルチプラットフォーム対応**
   - M5StickS3 (ESPHome)
   - Home Assistant OS 直挿し (Local USB Add-on)
   - Raspberry Pi 等の Linux機 (Pythonデーモン)

---

## 📦 1. Home Assistant カスタム統合のインストール

このリポジトリは **HACS (Home Assistant Community Store)** のカスタムリポジトリに対応しています。

1. HACS を開き、「Integration（統合）」の右上から「Custom repositories」を選択します。
2. このリポジトリのURL `https://github.com/Khronos31/IR-Trigger` を追加し、カテゴリを `Integration` にします。
3. HACSから `IR-Trigger` をダウンロードします。
4. HAの設定ディレクトリ（`configuration.yaml`があるフォルダ）に `IR-Trigger.yaml` を新規作成します。
5. `configuration.yaml` に以下を追記します。
   ```yaml
   ir_trigger:
   ```
6. Home Assistant を再起動します。

---

## 📝 2. 辞書ファイルの設定 (IR-Trigger.yaml)

HAの設定ディレクトリ（`config/` 直下）に `IR-Trigger.yaml` を作成し、以下のように受信コードとコントローラー・ボタンの対応を記述します。

```yaml
# IR-Trigger.yaml
"NEC_56A9718E":
  controller: "TV_Hitachi"
  button: "Power"

"AEHA_1234567890AB":
  controller: "Fan_Yamazen"
  button: "Swing"
```

> **💡 ヒント:**
> HAを再起動せずに辞書を更新したい場合は、HAの「開発者ツール」→「サービス」から **`ir_trigger.reload`** を実行してください。

---

## 📡 3. センサーとイベントの動作

信号を受信すると、以下の動作が自動的に行われます。

1. **デバイスの自動登録**
   - 受信元（`receiver`）ごとに、HAの「デバイスとサービス」に自動的にデバイスが生成されます。
   - 各デバイスには以下の3つのセンサーが作成され、最後に受信した信号が記録されます。
     - `sensor.<receiver>_latest_ir_signal` （値: `NEC_56A9718E` など）
     - `sensor.<receiver>_latest_ir_controller` （値: `TV_Hitachi` など）
     - `sensor.<receiver>_latest_ir_button` （値: `Power` など）

2. **イベントの発火**
   - HAのイベントバスに **`ir_trigger_received`** イベントが発火します。オートメーションのトリガーとして利用できます。
   ```json
   {
     "receiver": "LivingRoom_AD00020P",
     "controller": "TV_Hitachi",
     "button": "Power",
     "code": "NEC_56A9718E"
   }
   ```

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
