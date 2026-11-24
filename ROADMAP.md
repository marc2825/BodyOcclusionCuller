# UnderWhere ロードマップ

今後の予定です。時期や内容を約束するものではなく、実際のアバターでの検証結果や要望によって変わります。

## 次の版で取り組むこと

- **様々な実アバターでの検証**：判定の妥当性と処理時間を確かめ、頑健性の向上を目指します。
- **処理の高速化**：CPU のまま、サンプリングの計算をまとめて速くします。
- **素体への色の重ね表示**：横に比較メッシュを置く代わりに、素体そのものに判定の色を重ねて、衣装を着た状態のまま確認できるようにします。
- **残す根拠の可視化**：残すと判定した面が実際に見える視点へ View Ray で移動し、比較メッシュと並べて確認できるようにします。
- **更新の通知**：拡張機能リポジトリから配布し、新しい版が出たら Blender の Get Extensions に表示して、そこから更新できるようにします。（案：GitHub Pages に専用のリポジトリを用意します。更新の確認は、Allow Online Access がオンのときに Blender 本体が行います。UnderWhere 自体はこれまでどおりネットワークに接続しません。）
- **BOOTH での頒布**：GitHub Releases に加えて、BOOTH でも入手できるようにします。
- **デモ動画の撮影**：操作方法を中心に、使い方を紹介する動画を作ります。

## 検討中

- 身体と衣装が同じメッシュに入ったモデルへの対応（部位の指定が必要）
- 面単位の出力による、頂点の共有で残る面の削減
- アルファクリップ（切り抜き）素材の判定
- GPU による高速なプレビュー（判定の根拠には使いません）
- 衣装を突き抜ける身体の修正。身体の形を変える操作なので、非表示の判定とは別の機能として扱います。
- 判定の根拠の説明可能性
- extensions.blender.org での公開。同プラットフォームは add-on に GPL-3.0-or-later を求めるため、当面は Original License のまま GitHub と BOOTH で配布し、完成度が高まった段階でライセンスと合わせて検討します。

## 新しい判定方式

現在の判定は、検査したポーズでの有限個のサンプルに基づく候補です。これとは別に、次のような方式を検討しています。採用するかどうかは、合成データと実際のアバターでの比較で決めます。

- カメラの距離などで視点の範囲を指定し、その範囲から見えないことを確かめられた面だけを隠す
- ポーズの範囲を指定し、検査していないポーズで見える可能性がある面を事前に示す
- 細い開口部から見える面を、少ない計算で見つける

## 予定していないこと

- Review の面を自動で隠す設定。判断できなかった面は、利用者が確認して決めます。
- あらゆるポーズや視点での安全を保証すること（研究中）

---

## Roadmap (English)

These are future plans, not promises about timing or content. They will change with the results of testing on real avatars and with requests.

### Next version

- **Testing on a variety of real avatars:** check that the verdicts hold up and how long processing takes, and make the analysis more robust.
- **Faster processing:** still on the CPU, speed up sampling by batching its calculations.
- **Colours on the Body itself:** instead of a comparison beside it, overlay the verdict colours on the Body, so you can check while it wears the clothing.
- **Showing why a face is kept:** for a face judged to be kept, jump with View Ray to a viewpoint from which it is actually seen, and check it side by side with the comparison mesh.
- **Update notifications:** distribute through an extension repository, so that new versions appear in Blender's Get Extensions and can be updated from there. (Plan: a dedicated repository on GitHub Pages. Blender itself checks for updates, only while Allow Online Access is on; UnderWhere itself still never connects to the network.)
- **Distribution on BOOTH:** make the add-on available on BOOTH as well as on GitHub Releases.
- **Demo video:** record a video that introduces the add-on, focusing mainly on how to operate it.

### Under consideration

- Support for models whose body and clothing are in the same mesh (the parts would need to be specified)
- Per-face output, to reduce the faces that remain because they share vertices
- Judging alpha-clip (cutout) materials
- A fast GPU preview (never used as evidence for verdicts)
- Fixing a body that pokes through clothing. This changes the shape of the body, so it will be a separate feature from the hiding verdicts.
- Making the evidence behind verdicts explainable
- Publishing on extensions.blender.org. The platform requires GPL-3.0-or-later for add-ons, so for now the add-on stays under the Original License and is distributed on GitHub and BOOTH; publishing there, together with the license, will be considered once the add-on is more mature.

### New decision methods

The current verdicts are candidates based on a finite number of samples in the inspected poses. Separately, the following methods are being considered. Whether to adopt them will be decided by comparing them on synthetic data and on real avatars.

- Specify a range of viewpoints, for example by camera distance, and hide only faces confirmed to be unseen from that range
- Specify a range of poses, and show in advance the faces that may become visible in poses that were not inspected
- Find faces visible through narrow openings with less computation

### Not planned

- A setting that hides Review faces automatically. Faces that could not be decided are checked and decided by the user.
- Guaranteeing safety for every pose and viewpoint (under research)
