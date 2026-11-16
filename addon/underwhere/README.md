# UnderWhere

衣装の下に隠れた身体の面を調べ、非表示用のマスクや、その面を削除したコピーを作る Blender Extension です。

## インストール

Blender の **Preferences → Get Extensions → Install from Disk** でこの ZIP を指定します。3D View のサイドバー（N キー）に UnderWhere タブが追加されます。

## 使い方

1. 衣装と Body を選び（Body を最後にアクティブに）、**Use Selection → Preflight → Analyze** の順に押します。
2. 結果を確認し、必要なら Edit Mode で面を選んで **Keep / Hide / Clear** で修正します。
3. Object Mode で **Create Deleted Copy** を押すと、シェイプキーを保ったまま面を削除したコピーができます。FBX は Apply Modifiers をオフにして書き出してください。

判定は検査したポーズでの候補であり、安全を保証するものではありません。

## English

Install via **Preferences → Get Extensions → Install from Disk** and open the UnderWhere sidebar tab. Select clothing and the Body (active), then **Use Selection → Preflight → Analyze**. Review the result, adjust faces with **Keep / Hide / Clear**, and use **Create Deleted Copy** for FBX export (Apply Modifiers off). Results are candidates for the inspected poses, not a guarantee.

Guide: https://github.com/marc2825/BodyOcclusionCuller

MIT License. Copyright (c) 2026 marc2825
