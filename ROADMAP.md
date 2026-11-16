# UnderWhere ロードマップ

今後の予定です。時期や内容を約束するものではなく、実際のアバターでの検証結果や要望によって変わります。

## 次の版で取り組むこと

- **実際のアバターでの検証**：判定の妥当性と処理時間を確かめ、結果を文書に反映します。
- **処理の高速化**：CPU のまま、サンプリングの計算をまとめて速くします。
- **日本語の UI**：ボタン名、判定の理由、警告を日本語で表示します。
- **見えてしまう理由の表示**：隠すと欠けて見える視点へ View Ray で移動し、比較メッシュと並べて示します。
- **複数オブジェクトの Body**：頭と胴体など、分かれた Body をまとめて検査します。

## 検討中

- 身体と衣装が同じメッシュに入ったモデルへの対応（部位の指定が必要）
- 面単位の出力による、頂点の共有で残る面の削減
- アルファクリップ（切り抜き）素材の判定
- GPU による高速なプレビュー（判定の根拠には使いません）
- 衣装を突き抜ける身体の修正。身体の形を変える操作なので、非表示の判定とは別の機能として扱います。

## 新しい判定方式

現在の判定は、検査したポーズでの有限個のサンプルに基づく候補です。これとは別に、次のような方式を検討しています。採用するかどうかは、合成データと実際のアバターでの比較で決めます。

- カメラの距離などで視点の範囲を指定し、その範囲から見えないことを確かめられた面だけを隠す
- ポーズの範囲を指定し、検査していないポーズで見える可能性がある面を事前に示す
- 細い開口部から見える面を、少ない計算で見つける

## 予定していないこと

- Review の面を自動で隠す設定。判断できなかった面は、利用者が確認して決めます。
- あらゆるポーズや視点での安全を保証すること

---

## Roadmap (English)

Plans, not commitments; they will change with real-avatar testing and feedback.

- **Next:** testing on real avatars, faster CPU sampling, Japanese UI, showing the view in which a hidden face would be seen, and Bodies split into several objects.
- **Considering:** body and clothing in one mesh, per-face output, alpha-clip materials, a GPU preview (not used for decisions), and a separate tool for body parts poking through clothing.
- **New decision modes:** hiding only faces shown to be unseen from a declared range of camera positions, flagging faces that may appear in poses you did not inspect, and finding faces visible through narrow openings with less computation.
- **Not planned:** automatically hiding Review faces, or claiming safety for every pose and view.
