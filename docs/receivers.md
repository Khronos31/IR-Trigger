# 受信機セットアップガイド (Receivers Setup)

IR-Trigger はエッジ側での信号受信を前提としています。以下のいずれかの方法でセットアップしてください。

---

## 1. Webhook 経由 (Bit Trade One AD00020P 等)

Linux デーモンやアドオン経由で Webhook を飛ばす方式です。

### Webhook URL
`http://<HA_IP>:8123/api/webhook/ir_trigger_webhook`

### ペイロード形式 (JSON)
```json
{
  "receiver": "rx_study_ad00020p",
  "code": "NEC_56A912ED"
}
```

---

## 2. ESPHome 経由 (M5StickS3 / M5Atom 等)

ESPHome の `remote_receiver` を使用し、HA内蔵のイベントバスに直接 `ir_trigger_received` を流す方式です。詳細は `edge_scripts/m5stick_s3_ir.yaml` を参照してください。

---

## 3. Python デーモン (`ir_daemon.py`)

Linux マシンに直接 AD00020P を接続して使用する場合のスクリプトです。

### 必要パッケージ (Prerequisites)
以下のパッケージをあらかじめインストールしておいてください。

```bash
# Ubuntu/Debian の場合
sudo apt update
sudo apt install libusb-1.0-0-dev python3-pip

# Python ライブラリ
pip3 install pyusb requests aiohttp
```

1. `edge_scripts/ir_daemon.py` を任意の場所に配置。
2. 以下の引数で実行：
   - `--url`: Webhook URL
   - `--receiver`: 受信機名

```bash
python3 ir_daemon.py --url http://192.168.1.100:8123/api/webhook/ir_trigger_webhook --receiver living_room
```
