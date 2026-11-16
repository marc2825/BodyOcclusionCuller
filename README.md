# UnderWhere

[![Version](https://img.shields.io/github/v/release/marc2825/BodyOcclusionCuller?label=version)](https://github.com/marc2825/BodyOcclusionCuller/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[日本語](README.md) | [English](README_EN.md)


衣装の下に隠れている身体メッシュの面を調べ、非表示用のマスクや、その面を削除したコピーを作る Blender Extension です。元の Body には手を加えず、隠すと見えてしまう面や判断できなかった面を表示します。オフラインで動作します。

> 動作確認は Windows 版 Blender 5.2.3 LTS で行っています。

## インストール

[GitHub Releases](https://github.com/marc2825/BodyOcclusionCuller/releases) から Extension の ZIP を入手し、Blender の **Preferences → Get Extensions → Install from Disk** で読み込みます。ZIP は展開しないでください。3D View で N キーを押し、UnderWhere タブを開きます。

## 使い方の概要

1. 衣装と Body を選択し（Body は最後に選んでアクティブにする）、**Use Selection** を押します。
2. **Preflight** で入力を確認し、**Analyze** を実行します。
3. 判定結果と実際に隠れる面数を確認し、必要なら **Keep / Hide / Clear** で修正します。
4. **Apply to New Copy**（マスク付きのコピー）か **Create Deleted Copy**（面を削除したコピー）で出力します。VRChat 向けに FBX で書き出す場合は後者を使います。

詳しくは[操作ガイド](docs/user/QUICKSTART_JA.md)を参照してください。English: [overview](docs/user/OVERVIEW_EN.md)

## 注意

判定は、検査したポーズでの有限個のサンプルに基づく候補です。細い隙間、検査していないポーズやフレームの間、影・反射・物理演算については保証しません。出力したモデルは、実際に使うポーズで確認してください。

不具合を報告するときは **Export Shareable Report** で書き出したレポートを添付してください。メッシュの形状やオブジェクト名は含まれません。完全な診断データ（Private full diagnostics）や購入したモデルは公開しないでください。

## 関連文書

- [操作ガイド](docs/user/QUICKSTART_JA.md)
- [English overview](docs/user/OVERVIEW_EN.md)
- [動作確認](docs/testing/VERIFICATION.md)
- [変更履歴](CHANGELOG.md)
- [ロードマップ](ROADMAP.md)

※ **UnderWhere** はアドオンの正式名称、**BodyOcclusionCuller** はソースコードを公開するリポジトリ名です。

## 開発

Python の標準ライブラリと、Blender に同梱されたモジュールだけを使っています。

```bash
python3 scripts/extension/run_tests.py --blender /path/to/blender        # テスト
python3 scripts/extension/package_extension.py --blender /path/to/blender # ZIP の作成
blender -b --factory-startup --python scripts/extension/create_sample.py  # デモの生成
```

## ライセンス

MIT License. Copyright (c) 2026 marc2825
