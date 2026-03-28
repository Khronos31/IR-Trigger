# 受信機セットアップガイド (Receivers Setup)

IR-Trigger はエッジデバイス（受信機）側で信号を受信し、Home Assistant へ通知する仕組みです。以下のいずれかの方法でセットアップしてください。

---

## 1. Webhook 経由 (推奨)

Linux デーモンやマイコンから Webhook を飛ばす方式です。特別な設定なしで即座に連動可能です。

### Webhook エンドポイント
`http://<HA_IP>:8123/api/webhook/ir_trigger_webhook`

### ペイロード形式 (JSON)
```json
{
  "receiver": "living_room",
  "code": "NEC_80EA12ED"
}
```
- `receiver`: `IR-Trigger.yaml` で定義した `local_receivers` と一致させる必要があります（ループ防止のため）。
- `code`: `送信プロトコル_コード内容` の形式。

---

## 2. Linux + AD00020P (`ir_daemon.py`)

Bit Trade One 社の AD00020P を Linux マシン（Raspberry Pi等）に接続して使用する場合のセットアップ手順です。

### 2.1. 事前準備 (venv の使用推奨)
最新の OS ではシステム Python への直接インストールが制限されているため、仮想環境を使用します。

```bash
# 必要パッケージのインストール
sudo apt update
sudo apt install libusb-1.0-0-dev python3-venv python3-pip

# プロジェクトディレクトリへ移動
cd edge_scripts

# 仮想環境の作成と有効化
python3 -m venv venv
source venv/bin/activate

# 依存ライブラリのインストール
pip install pyusb requests aiohttp
```

### 2.2. デーモンの実行
```bash
python3 ir_daemon.py \
  --url http://<HA_IP>:8123/api/webhook/ir_trigger_webhook \
  --receiver living_room
```

---

## 3. ESPHome 経由 (M5Stick / M5Atom 等)

ESPHome デバイスを使用する場合、`remote_receiver` で取得した信号を直接 Home Assistant イベントとして発行します。

### 設定例 (`esphome.yaml`)
```yaml
remote_receiver:
  pin: 
    number: GPIO35
    inverted: true
  dump: all

# 受信時に HA イベントを発行
on_ir_receive:
  then:
    - homeassistant.event:
        event: ir_trigger_received
        data:
          receiver: "study_room"
          code: !lambda 'return x.protocol + "_" + x.code;'
```
※ 詳細は `edge_scripts/m5stick_s3_ir.yaml` (もしあれば) を参照してください。

---

## 4. 安定運用のための systemd 設定

Linux でデーモンをバックグラウンド実行し、自動起動させるための設定例です。

`ir-daemon.service` を `/etc/systemd/system/` に作成：
```ini
[Unit]
Description=IR-Trigger Receiver Daemon
After=network.target

[Service]
ExecStart=/path/to/edge_scripts/venv/bin/python /path/to/edge_scripts/ir_daemon.py --url ... --receiver ...
WorkingDirectory=/path/to/edge_scripts
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

作成後、以下のコマンドで有効化します：
```bash
sudo systemctl daemon-reload
sudo systemctl enable ir-daemon
sudo systemctl start ir-daemon
```

