#pragma once

#include <M5Unified.h>
#include <vector>

// Forward declarations
class IRsend;
class IRrecv;

// 汎用アプリの抽象基底インターフェース
// これを継承することで、main.cppは具体的なクラス名を知らなくても
// アプリをメニューに登録し、実行できるようになる。
class AppInterface {
public:
    virtual ~AppInterface() {}

    // アプリの表示名 (例: "1. Dumb Pipe")
    virtual const char* getName() const = 0;

    // ハードウェア（送信と受信）へのポインタを受け取る
    // 送信時に自爆受信を防ぐために rx も必要
    virtual void init(IRsend* tx, IRrecv* rx) = 0;

    // アプリが選択された時の初期化処理
    virtual void setup() = 0;

    // 画面描画処理 (fullDraw=true で背景から全再描画)
    virtual void draw(bool fullDraw = false) = 0;

    // アプリのメインループ (returnToMenu に true を入れるとメニューに戻る)
    virtual void loop(bool& returnToMenu) = 0;

    // 赤外線信号を受信したときのコールバック
    // デフォルト実装は空にしておく（受信不要なアプリ用）
    virtual void onIrReceived(const String& hexCode, const String& rawJson, const std::vector<uint16_t>& rawVector, uint32_t ts) {}

    // HAからWebhooks経由で赤外線送信命令(TX)を受け取ったときのコールバック
    virtual void onTxReceived(const std::vector<uint16_t>& raw, const String& displayCode) {}
};
