# UnderWhere 動作確認（1.1.0）

検証日：2026-11-18。公開リポジトリ：BodyOcclusionCuller。

## 環境

- Blender 5.2.3 LTS（Windows）
- テストの実行：Windows、CPython 3.11（GitHub Actions では Linux 版 Blender 5.2.3 で同じテストを実行）

これ以外のバージョンの Blender、Linux・macOS 版 Blender、Unity / VRChat SDK では確認していません。

## 自動テスト

| 項目 | 結果 |
|---|---|
| 単体テスト（判定規則、修復方針、共有レポート、ベンダーコードの固定） | 14 件成功 |
| Blender 統合テスト（バックグラウンド実行） | 71 件成功（旧名称からの保存設定移行・読み取り専用データの保護を含む） |
| 公式ツールによる ZIP の検証・インストール・無効化・アンインストール | 9 項目成功 |
| デモファイルの生成と個人情報の混入検査 | 成功 |
| GUI 操作テスト | 自動スモーク 15 項目成功 |
| 人による操作確認 | 確認済み |

パネルの表示は、統合テストで全パネルを描画し、アイコン名・プロパティ・オペレーターがすべて存在することを確かめています。実際の画面での見た目や Box・Lasso・Brush のドラッグ操作は、人が操作して確認しました。

テストで使ったのはすべて合成した形状です。主に次の場面を確認しています。

- 閉じた衣装、両端が開いた筒、細い隙間（Solidify あり・なし、メートル単位と cm 単位）
- 透明・不明な素材、裏面カリング、Assume opaque
- 身体と衣装の交差・接触
- 既存マスクのしきい値・反転・モディファイアの順序
- シェイプキー、ウェイト、UV、Armature の変形
- 現在のポーズと指定フレームの組み合わせ
- 既存マスクの修復方針の切り替えと、Before / After の比較表示
- 比較メッシュが、変更を監視する処理によって消されないこと
- 比較メッシュ上の範囲選択が元の Body の面に対応すること、Only change Review faces が判定済みの面を変えないこと、Keep / Hide の後も比較メッシュで選択を続けられること
- 身長 1.7 m の曲面の身体と 6 パーツの衣装
- 複数のオブジェクトに分かれた Body の検査、Body 上の一括選択、オブジェクトごとの出力
- Keep / Hide で指定した面の色分けと、色ごとの表示切り替え
- 複数フレームで各面が隠れていた割合（Poses 表示）
- FBX の書き出しと読み込みで、シェイプキー・UV・ボーン・スキンウェイトが残ること
- キャンセル、Undo / Redo、ファイルの再読み込み

1 万頂点・シェイプキー 61 個の合成メッシュで、入力の取得にかかる時間は約 0.19 秒でした。実際のアバターでの処理時間ではありません。

## 未確認の項目

- 実際のアバターでの有用性と処理時間
- Unity / VRChat SDK での表示

## テストの実行方法

```bash
python3 scripts/extension/run_tests.py --blender "$BLENDER"
"$BLENDER" --factory-startup --offline-mode --python tests/extension/gui_smoke.py
python3 scripts/extension/package_extension.py --blender "$BLENDER"
"$BLENDER" -b --factory-startup --offline-mode --python-exit-code 1 --python tests/extension/install_zip.py
"$BLENDER" -b --factory-startup --offline-mode --python-exit-code 1 --python scripts/extension/create_sample.py
```

GUI 操作テストは Blender のウィンドウを開きます。

## 正式名称と保存設定

Extension ID・Pythonパッケージは `underwhere`、サイドバー名は UnderWhere です。
旧名称で保存した Body・衣装・フレーム・選択設定と明示的な素材仮定は移行し、
古い解析結果は引き継がず再解析を必要とします。

配布物は `underwhere-1.1.0.zip`、その SHA-256（`underwhere-1.1.0.zip.sha256`）、`underwhere_demo.blend` です。
