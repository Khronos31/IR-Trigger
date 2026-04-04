# 送信機セットアップガイド (Transmitters Setup)

IR-Trigger では、Home Assistant 上の仮想エンティティ（テレビ、ライト等）の操作に応じて、設定されたエッジデバイス（送信機）に対して赤外線発射の指示を送ります。

以下のいずれかの方式でセットアップしてください。

---

## 1. Webhook 経由 (推奨)

マイコン等で動作する任意の Web サーバに対して POST リクエストを飛ばす方式です。
HA側でプロトコルからパルス長（Raw）への変換までを行うため、マイコン側（Panopticon など）は送られてきた配列をそのまま発射するだけの非常に軽量な構成（Dumb Pipeアーキテクチャ）にできます。

### 設定例 (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_webhook:
    name: "Webhook Transmitter"
    type: webhook
    url: "http://<ESP32_IP>:80/tx"
```

### ネットワーク・ペイロード仕様 (JSON)
Home Assistant からは、指定された URL に以下の形式の JSON ペイロードが POST されます。

```json
{
  "code": "NEC-80EA12ED",
  "raw": [9000, 4500, 560, 1680, 560, 560, ...]
}
```

- **`code`**: 送信プロトコル名と HEX コードを結合した文字列。エッジデバイス側で画面に「何を送信しているか」を表示するためのメタデータとして活用できます。
- **`raw`**: 赤外線LEDをON/OFFさせるためのマイクロ秒（μs）単位のパルス時間の配列（必ず正の整数）。これを使って `delayMicroseconds` や RMT ペリフェラルで直接赤外線を発射できます。

---

## 2. ESPHome 経由

Home Assistant の ESPHome 統合を利用して赤外線を送信する方式です。
内部的には、`esphome.<node_name>_send_raw` というカスタムサービスを呼び出します。

### 設定例 (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_study:
    name: "Study Transmitter"
    type: esphome
    node_name: "atom_s3_study"
```

### 設定例 (`esphome.yaml`)
ESPHome デバイス側には、`send_raw` アクションを受け付けるための `api` サービスを定義しておく必要があります。

```yaml
api:
  services:
    - service: send_raw
      variables:
        command: int[]
      then:
        - remote_transmitter.transmit_raw:
            carrier_frequency: 38kHz
            code: !lambda "return command;"
```

---

## 3. Nature Remo (Local API) 経由

Nature Remo デバイスのローカル API を叩いて直接赤外線を送信する方式です。
クラウドを経由しないため、非常に高速で安定しています。

### 設定例 (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_living:
    name: "Living Room Transmitter"
    type: nature_remo
    ip: "192.168.1.30"
```
※ `ip` には Nature Remo のローカル IP アドレスを指定してください。

---

## 4. テスト・デバッグ用 (Mock)

実際のデバイスに赤外線を送信せず、Home Assistant のログ上に「どのコードが送信されるはずだったか」を出力するだけの仮想送信機です。
新しいデバイスやルーティングの設定をテストする際に、実際の家電を動かすことなく安全に動作確認を行うことができます。

### 設定例 (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_debug:
    name: "Debug Transmitter"
    type: mock
```

送信を実行すると、HAのログに以下のように出力されます：
```text
[MOCK] Sending: NEC-80EA12ED
```
