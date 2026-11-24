# UnderWhere

衣装の下に隠れた身体の面を調べ、非表示用のマスクや、その面を削除したコピーを作る Blender Extension です。

## インストール

Blender の **Preferences → Get Extensions → Install from Disk** でこの ZIP を指定します。3D View のサイドバー（N キー）に UnderWhere タブが追加されます。

## 使い方

1. **準備**：衣装を選び、最後に素体を選んで「選択から設定」→「調べる」を押します。
2. **確認**：「次にやること」に沿って、要確認の面を「残す」か「隠す」に決めます。
3. **書き出し**：「面を削除したコピーを作る」を押すと、シェイプキーを保ったまま面を削除したコピーができます。FBX は Apply Modifiers をオフにして書き出してください。

判定は検査したポーズでの候補であり、安全を保証するものではありません。

## English

Install via **Preferences → Get Extensions → Install from Disk** and open the UnderWhere sidebar tab. Three steps: in **Set up**, select clothing and the Body (active), then **Use selection → Analyze**; in **Review**, follow **Next steps** and choose **Keep** or **Hide** for unsure faces; in **Export**, use **Create copy with faces removed** for FBX (Apply Modifiers off). Results are candidates for the inspected poses, not a guarantee.

Guide: https://github.com/marc2825/BodyOcclusionCuller

Original License (see LICENSE): free to use; what you make is yours; do not redistribute or sell the add-on / 作ったものは自由、アドオン自体の再配布・販売は不可. Copyright (c) 2026 marc2825
