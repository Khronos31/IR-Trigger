# 受信機セットアップガイド (Receivers Setup)

IR-Trigger はエッジデバイス（受信機）側で信号を受信し、Home Assistant へ通知する仕組みです。以下のいずれかの方法でセットアップしてください。

---

## 1. Webhook 経由 (推奨)

Linux デーモンやマイコンから Webhook を飛ばす方式です。特別な設定なしで即座に連動可能です。

### Webhook エンドポイント
`http://<HA_IP>:8123/api/webhook/<receiver_id>`
※ `<receiver_id>` は `IR-Trigger.yaml` の `receivers:` セクションで定義したキー名です。

### ペイロード形式 (JSON)
```json
{
  "code": "NEC_80EA12ED"
}
```
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

# プロジェクト内 tools/scripts へ移動
cd tools/scripts

# 仮想環境の作成と有効化
python3 -m venv venv
source venv/bin/activate

# 依存ライブラリのインストール
pip install pyusb requests aiohttp
```

### 2.2. デーモンの実行
```bash
python3 ir_daemon.py --url http://<HA_IP>:8123/api/webhook/rx_study_usb
```

---

## 3. ESPHome 経由 (M5Stick / M5Atom 等)

ESPHome デバイスを使用する場合、`http_request` コンポーネントを使用して信号を Home Assistant へ Post します。

### 設定例 (`esphome.yaml`)
```yaml
http_request:
  timeout: 5s

remote_receiver:
  pin: 
    number: GPIO33
    inverted: true
  dump: all
  on_nec:
    then:
      - http_request.post:
          url: "http://<HA_IP>:8123/api/webhook/rx_living_esp"
          json: !lambda |-
            char buffer[64];
            sprintf(buffer, "{\"code\": \"NEC_%04X%04X\"}", x.address, x.command);
            return std::string(buffer);
```
※ 詳細は `tools/esphome/m5stick_s3_ir.yaml` を参照してください。

---

## 4. 安定運用のための systemd 設定

Linux でデーモンをバックグラウンド実行し、自動起動させるための設定例です。

`ir-daemon.service` を `/etc/systemd/system/` に作成：
```ini
[Unit]
Description=IR-Trigger Receiver Daemon
After=network.target

[Service]
ExecStart=/path/to/venv/bin/python /path/to/ir_daemon.py --url http://<HA_IP>:8123/api/webhook/<receiver_id>
WorkingDirectory=/path/to/tools/scripts
StandardOutput=inherit
StandardError=inherit
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

作成後、以下のコマンドで有効化します：
```bash
sudo systemctl daemon-reload
sudo systemctl enable ir-daemon
sudo systemctl start ir-daemon
```
