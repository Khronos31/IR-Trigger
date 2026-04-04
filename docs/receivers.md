# 受信機セットアップガイド (Receivers Setup)

IR-Trigger はエッジデバイス（受信機）側で信号を受信し、Home Assistant へ通知する仕組みです。以下のいずれかの方法でセットアップしてください。

---

## 1. Webhook 経由 (推奨)

Linux デーモンやマイコンから Webhook を飛ばす方式です。特別な設定なしで即座に連動可能です。

### Webhook エンドポイント
`http://<HA_IP>:8123/api/webhook/<receiver_id>`
※ `<receiver_id>` は `IR-Trigger.yaml` の `receivers:` セクションで定義したキー名です。

### ペイロード形式 (JSON)
Webhookは以下の2つの形式のいずれかを受け付けます。

**パターン1: デコード済みコード文字列**
```json
{
  "code": "NEC-80EA12ED"
}
```
- `code`: `送信プロトコル-HEXコード` の形式（すでにエッジデバイス側でデコードが済んでいる場合に使用）。

**パターン2: 生のパルス配列（RAW）**
```json
{
  "raw": [9000, 4500, 560, 1680, 560, 560]
}
```
- `raw`: マイクロ秒単位のON/OFFパルスの配列（すべて正の整数）。Home Assistant側で自動的にプロトコルとHEXコードにデコードされます。V2アーキテクチャでは、マイコン側の負荷を軽減するためこちらの「Dumb Pipe」方式を推奨しています。

---

## 2. ESPHome / Panopticon 経由 (M5Stick / M5Atom 等)

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
  on_raw:
    then:
      - if:
          condition:
            lambda: 'return x.size() > 20;'
          then:
            - http_request.post:
                url: "http://<HA_IP>:8123/api/webhook/rx_living_esp"
                request_headers:
                  Content-Type: application/json
                body: !lambda |-
                  // Construct raw JSON array from pulses. OFF times are normalized to positive integers for HA processing.
                  std::string payload = "{\"raw\":[";
                  for (size_t i = 0; i < x.size(); i++) {
                    payload += std::to_string(std::abs(x[i]));
                    if (i < x.size() - 1) payload += ", ";
                  }
                  payload += "]}";
                  return payload;
```
※ 詳細は `tools/esphome/AtomS3.yaml` を参照してください。

