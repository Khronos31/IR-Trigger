#pragma once

#include <M5Unified.h>
#include <IRsend.h>
#include <vector>

// 汎用アプリの抽象基底インターフェース
// これを継承することで、main.cppは具体的なクラス名を知らなくても
// アプリをメニューに登録し、実行できるようになる。
class AppInterface {
public:
    virtual ~AppInterface() {}

    // アプリの表示名 (例: "1. Dumb Pipe")
    virtual const char* getName() const = 0;

    // ハードウェア（送信）へのポインタを受け取る
    virtual void init(IRsend* tx) = 0;

    // アプリが選択された時の初期化処理
    virtual void setup() = 0;

    // 画面描画処理 (fullDraw=true で背景から全再描画)
    virtual void draw(bool fullDraw = false) = 0;

    // アプリのメインループ (returnToMenu に true を入れるとメニューに戻る)
    virtual void loop(bool& returnToMenu) = 0;

    // 赤外線信号を受信したときのコールバック
    // デフォルト実装は空にしておく（受信不要なアプリ用）
    virtual void onIrReceived(const String& hexCode, const String& rawJson, const std::vector<uint16_t>& rawVector, uint32_t ts) {}
};
