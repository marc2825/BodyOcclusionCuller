"""Japanese UI text, keyed by the English message id used in the code.

Pure data so that the unit tests can check it without Blender. Placeholders
such as {count} must appear in both languages. Terms:
Body 素体, clothing 衣装, Hideable 隠せる, Visible 見える, Unsure 要確認,
Keep 残す, Hide 隠す, Analyze 調べる, comparison 比較メッシュ."""

JA = {
    # Steps and panels
    "Set up": "準備",
    "Review": "確認",
    "Export": "書き出し",
    "Step": "段階",
    "Choose the Body and its clothing, then analyze": "素体と衣装を選んで調べます",
    "See the result and decide the unsure faces": "結果を見て、要確認の面を決めます",
    "Create the output copy": "出力用のコピーを作ります",
    "Body and clothing": "素体と衣装",
    "Analysis": "調べる",
    "Poses and purpose": "ポーズと目的",
    "Clothing materials": "衣装の素材",
    "Sampling values": "サンプリングの数値",
    "Result": "結果",
    "Check and decide": "確認して決める",
    "Select by reason": "理由ごとに選ぶ",
    "One face at a time": "1面ずつ見る",
    "Go to step": "段階を移動",
    "Switch the sidebar to this step": "サイドバーをこの段階に切り替えます",
    "Go to Export": "書き出しへ進む",
    "Go to Set up": "準備に戻る",
    "Go to Review": "確認に戻る",
    "Analyze first to see a result here.": "結果を見るには、先に調べてください。",

    # Status box
    "Choose the Body and its clothing.": "素体と衣装を選んでください。",
    "Select the clothing, then the Body last, and press Use selection.":
        "衣装を選び、最後に素体を選んでから「選択から設定」を押します。",
    "Ready to analyze.": "調べる準備ができました。",
    "Press Analyze below.": "下の「調べる」を押してください。",
    "Analyzing…": "調べています…",
    "The analysis was cancelled. Nothing was changed.": "中断しました。何も変更していません。",
    "The inputs changed. They are checked again at the next step.":
        "入力が変わりました。次の操作のときに確認し直します。",
    "Inputs look fine.": "入力に問題はありません。",
    "Body size: {size} m": "素体の大きさ: {size} m",
    "The Body is {size} m in scene units; it was analyzed as {scaled} m.":
        "素体はシーンの単位で {size} m あるため、{scaled} m として調べました。",
    "Materials not confirmed opaque: {count}": "不透明か確認できない素材: {count}",
    "Removable faces: {count} ({percent}%)": "削除できる面: {count}（{percent}%）",
    "This result no longer matches the scene.": "この結果は、今のシーンと合っていません。",
    "Results are not saved in .blend files.": "結果は .blend ファイルに保存されません。",
    "Results were cleared when the add-on was enabled.": "アドオンを有効にしたため、結果が消えました。",
    "The Body, clothing, materials or frames changed.": "素体・衣装・素材・フレームのどれかが変わりました。",
    "Your Keep and Hide choices are kept. Analyze again to continue.":
        "「残す」「隠す」の指定は残っています。調べ直すと続けられます。",
    "Analyze again to continue.": "調べ直すと続けられます。",
    "Analyze again": "調べ直す",
    "Out of date. Use Analyze again at the top.": "結果が古くなっています。上の「調べ直す」を押してください。",

    # Set up
    "Use selection": "選択から設定",
    "Set the active mesh as the Body and the other selected meshes as clothing. Select the Body last":
        "アクティブなメッシュを素体に、ほかの選択中のメッシュを衣装にします。素体は最後に選んでください",
    "Body": "素体",
    "The avatar's body mesh. It is never changed": "アバターの身体のメッシュです。変更はしません",
    "Body has several objects": "素体が複数のオブジェクトに分かれている",
    "Also inspect separate Body objects such as a head; each gets its own output copy. "
    "Body objects do not hide each other, only the clothing does":
        "頭など、分かれた素体のオブジェクトも一緒に調べます。出力はオブジェクトごとに作ります。"
        "素体どうしは互いを隠すものとして扱わず、隠すのは衣装だけです",
    "+ adds the selected meshes.": "＋で、選択中のメッシュを追加します。",
    "Edit Body parts": "素体のパーツを編集",
    "Add the selected meshes that are not used yet (or an empty slot) as Body parts, or remove the chosen one":
        "まだ使っていない選択中のメッシュ（なければ空の枠）を素体のパーツに追加するか、選んだものを外します",
    "Clothing": "衣装",
    "Edit clothing list": "衣装の一覧を編集",
    "Add a clothing slot, or remove the chosen one": "衣装の枠を追加するか、選んだものを外します",
    "Detail": "細かさ",
    "Fast": "速い",
    "Coarse sampling for a quick first look": "粗く調べて、すばやく様子を見ます",
    "Standard": "標準",
    "Recommended sampling": "おすすめの細かさです",
    "Fine": "細かい",
    "Finer sampling; slower": "細かく調べます。時間がかかります",
    "Custom": "カスタム",
    "Your own sampling values": "自分で決めた数値を使います",
    "Analyze": "調べる",
    "Find the Body faces that the clothing covers. Press Esc over this view, or Cancel, to stop":
        "衣装に隠れている素体の面を探します。このビューの上で Esc を押すか「中止」で止められます",
    "Check inputs only": "入力チェックだけ行う",
    "Check inputs": "入力チェック",
    "Check the Body, clothing, modifiers and materials without analyzing":
        "調べる前に、素体・衣装・モディファイア・素材を確認します",
    "Cancel": "中止",
    "Stop the analysis. Nothing is changed": "調べるのを止めます。何も変更しません",
    "Checking the existing mask {mask}": "既存マスク {mask} を検査します",
    "Also inspecting frames {frames}": "フレーム {frames} も調べます",
    "Poses": "ポーズ",
    "Current pose": "現在のポーズ",
    "Inspect only the pose on the current frame": "現在のフレームのポーズだけを調べます",
    "Current pose and listed frames": "現在のポーズと指定したフレーム",
    "Also inspect the listed frames. A face is hideable only if every inspected frame hides it; "
    "poses between frames are not checked":
        "指定したフレームも調べます。すべてのフレームで隠れている面だけが「隠せる」になります。"
        "フレームの間のポーズは調べません",
    "Frames": "フレーム",
    "Frame numbers separated by commas": "フレーム番号をカンマで区切って入力します",
    "Purpose": "目的",
    "Find hideable faces": "隠せる面を探す",
    "Find the Body faces that the clothing covers": "衣装に隠れている素体の面を探します",
    "Check an existing mask": "既存のマスクを検査する",
    "Check a vertex-group Mask modifier that already hides faces":
        "すでに面を隠している頂点グループ方式の Mask モディファイアを検査します",
    "Existing mask": "既存のマスク",
    "The clothing has no materials.": "衣装に素材がありません。",
    "Opaque is your own statement that the whole material blocks the view.":
        "「不透明」は、素材全体が向こうを通さないというあなた自身の判断として扱います。",
    "Opaque": "不透明",
    "Your statement that this whole material is opaque on both sides, with no transmission or displacement. "
    "Recorded in reports; not an automatic proof":
        "この素材全体が表裏とも不透明で、透過やディスプレイスメントがないというあなたの判断です。"
        "レポートに記録され、自動の確認ではありません",
    "Confirmed opaque automatically": "自動で不透明と確認できました",
    "Backface culling is on, so it cannot be marked opaque": "裏面カリングが有効なため、不透明にできません",
    "Sample spacing (metres)": "サンプルの間隔（メートル）",
    "Direction step (degrees)": "方向の刻み（度）",
    "Contact tolerance (metres)": "接触とみなす距離（メートル）",
    "Advanced": "詳細",
    "Scene scale: {scale} m per unit": "シーンの単位: 1 あたり {scale} m",

    # Review: summary and next steps
    "{hidden} of {total} faces": "{total} 面中 {hidden} 面",
    "Hideable": "隠せる",
    "Visible": "見える",
    "Unsure": "要確認",
    "Earlier choices kept: {count}": "引き継いだ指定: {count}",
    "Clear": "消す",
    "Faces the existing mask hides: {count}": "既存マスクが隠している面: {count}",
    "Shown again: {restored}. Newly hidden: {added}.": "再表示 {restored} 面、新たに隠す {added} 面",
    "Next steps": "次にやること",
    "Visible faces hidden by the existing mask: {count}. Choose a repair policy under Check and decide.": "既存マスクが隠している見える面: {count}。「確認して決める」で修復方針を選んでください。",
    "{object}: {reasons}. Faces it covers stay unsure.": "{object}: {reasons}。この衣装に隠れる面は要確認になります。",
    "Faces you hid that were judged visible or unsure: {count}. Check them before you export.": "自分で隠した面のうち、見える・要確認と判定された面: {count}。書き出す前に確かめてください。",
    "Unsure faces still hidden by the existing mask: {count}": "既存マスクで隠れたままの要確認の面: {count}",
    "{material} is not confirmed opaque. Unsure faces because of it: {count}": "{material} が不透明か確認できません。これによる要確認の面: {count}",
    "Clothing without a material. Unsure faces because of it: {count}": "素材のない衣装があります。これによる要確認の面: {count}",
    "Unsure faces left: {count}. Look at them and choose Keep or Hide.": "残っている要確認の面: {count}。見て「残す」か「隠す」を選んでください。",
    "Hideable faces kept because they share vertices with visible faces: {count}. No action is needed.": "見える面と頂点を共有しているため残る、隠せる面: {count}。対応は不要です。",
    "Hideable faces that rely on your Opaque setting: {count}": "あなたの「不透明」の設定に基づく、隠せる面: {count}",
    "Nothing is left to decide. You can export now.": "決めることは残っていません。書き出せます。",
    "Pick on the comparison": "比較メッシュで選ぶ",
    "Select all on the Body": "素体ですべて選ぶ",

    # Review: comparison and decisions
    "Show": "表示",
    "Verdicts": "判定",
    "Colour each face by its verdict": "面を判定の色で塗り分けます",
    "Without mask": "マスクなし",
    "Show the Body without any mask": "マスクをかけない素体を表示します",
    "After output": "出力後",
    "Show the Body as the output will look": "出力後の見た目を表示します",
    "Before / After": "既存マスクとの差",
    "Colour faces by how the output changes the existing mask": "出力で既存マスクがどう変わるかを色で示します",
    "Colour faces by the share of inspected frames that hide them": "各面が何割のフレームで隠れていたかを色で示します",
    "Off": "表示しない",
    "Remove the coloured copy": "色分けしたコピーを消します",
    "Colours shown": "表示する色",
    "Show hideable faces": "隠せる面を表示します",
    "Show faces seen in an inspected pose": "調べたポーズで見えた面を表示します",
    "Show unsure faces": "要確認の面を表示します",
    "Show visible faces that the existing mask hides": "既存マスクが隠している、見える面を表示します",
    "Show unsure faces that the existing mask hides": "既存マスクが隠している、要確認の面を表示します",
    "Show faces you chose to hide": "自分で隠した面を表示します",
    "Show faces you chose to keep": "自分で残した面を表示します",
    "Mask hides visible": "マスクが見える面を隠す",
    "Mask hides unsure": "マスクが要確認の面を隠す",
    "Hidden by you": "自分で隠した",
    "Kept by you": "自分で残した",
    "Newly hidden": "新たに隠れる",
    "Shown again": "再び表示される",
    "Still hidden": "隠れたまま",
    "Hidden in all": "すべてで隠れる",
    "Hidden in 75%+": "75%以上で隠れる",
    "Hidden in 50%+": "50%以上で隠れる",
    "Hidden in some": "一部で隠れる",
    "Never hidden": "一度も隠れない",
    "Undecided": "判断できない",
    "Update": "更新",
    "Update comparison": "比較メッシュを更新",
    "Redraw the coloured copy beside the Body": "素体の横の色分けしたコピーを描き直します",
    "Click a colour to show or hide it.": "色を押すと、表示・非表示を切り替えます。",
    "Inspect several frames to see shades.": "段階で見るには、複数のフレームを調べてください。",
    "Share of {count} inspected frames": "調べた {count} フレームに対する割合",
    "Show colours in this view": "このビューで色を表示する",
    "Show colours": "色を表示",
    "Show material colours in this 3D View, so the verdict colours appear":
        "この 3D ビューで素材の色を表示し、判定の色が見えるようにします",
    "Choose faces": "面を選ぶ",
    "Select on": "選ぶ場所",
    "Comparison": "比較メッシュ",
    "Select on the coloured copy beside the Body": "素体の横の色分けしたコピーの上で選びます",
    "Select on the Body itself": "素体そのものの上で選びます",
    "Box": "囲む",
    "Lasso": "投げ縄",
    "Brush": "なぞる",
    "Drag a rectangle": "四角形で囲みます",
    "Draw a free-form outline": "自由な形で囲みます",
    "Paint over faces with a circle brush (the mouse wheel changes its size)":
        "円のブラシでなぞります（マウスホイールで大きさを変えます）",
    "Current tool": "今のツール",
    "Keep the active selection tool": "今の選択ツールのまま使います",
    "Press Box, Lasso or Brush to start.": "「囲む」「投げ縄」「なぞる」のどれかを押して始めます。",
    "Selected: {count}": "選択中: {count}",
    "Drag over faces": "面の上をドラッグします",
    "Shift adds, Ctrl removes": "Shift で追加、Ctrl で除外",
    "Decide": "決める",
    "Only change unsure faces": "要確認の面だけ変える",
    "Keep and Hide change only the unsure faces in your selection (and faces an existing mask hides wrongly), "
    "so a rough selection never changes decided faces":
        "「残す」「隠す」は、選んだ範囲のうち要確認の面（と既存マスクが誤って隠している面）だけを変えます。"
        "大まかに選んでも、判定済みの面は変わりません",
    "Keep": "残す",
    "Hide": "隠す",
    "Clear choice": "取り消す",
    "Done": "完了",
    "Stop selecting faces and return to Object Mode": "面の選択を終えて、オブジェクトモードに戻ります",
    "Select faces": "面を選ぶ",
    "Start selecting faces with this tool, on the coloured copy or on the Body. "
    "Switching tools keeps the selection":
        "このツールで、色分けしたコピーまたは素体の上の面を選び始めます。ツールを切り替えても選択は残ります",
    "Drag over faces. Shift adds, Ctrl removes. Then choose Keep or Hide.":
        "面の上をドラッグします。Shift で追加、Ctrl で除外し、「残す」か「隠す」を選びます。",
    "Keep or hide faces": "面を残す・隠す",
    "Change the output for the selected faces. The original verdicts stay recorded":
        "選んだ面の出力を変えます。元の判定は記録に残ります",
    "Use selected faces": "選択中の面を使う",
    "Always keep the selected faces in the output": "選んだ面を必ず出力に残します",
    "Hide the selected faces in the output. Asks first; Ctrl+Z undoes it":
        "選んだ面を出力で隠します。実行前に確認し、Ctrl+Z で元に戻せます",
    "Remove your choice from the selected faces and use the automatic verdict":
        "選んだ面の指定を取り消し、自動の判定に戻します",
    "Hide these faces?": "これらの面を隠しますか？",
    "Hide can cover a face that was seen or unsure. Ctrl+Z undoes it.":
        "見えた面や要確認の面も隠せてしまいます。Ctrl+Z で元に戻せます。",
    "{action}: {count}": "{action}: {count}",
    "Select more, or press Done.": "続けて選ぶか、「完了」を押します。",
    "Clear all choices": "すべての指定を消す",
    "Remove every Keep and Hide you chose, and use the automatic verdicts again":
        "自分で選んだ「残す」「隠す」をすべて消し、自動の判定に戻します",
    "Clear all choices?": "すべての指定を消しますか？",
    "Every Keep and Hide you chose is removed. Ctrl+Z undoes it.":
        "自分で選んだ「残す」「隠す」がすべて消えます。Ctrl+Z で元に戻せます。",
    "Select faces at once": "まとめて選ぶ",
    "Select every matching face on the Body, then choose Keep or Hide for all of them":
        "当てはまる面を素体の上ですべて選びます。そのあと「残す」か「隠す」を選びます",
    "All unsure": "要確認すべて",
    "Every face that could not be decided": "判断できなかったすべての面",
    "Mask issues": "マスクの問題",
    "Faces the existing mask hides although they are visible or unsure":
        "見える・要確認なのに、既存マスクが隠している面",
    "By reason": "理由ごと",
    "Unsure or mask-issue faces with one reason": "同じ理由の要確認の面やマスクの問題の面",
    "Selected: {count}. Keep or Hide applies to all of them.": "選択: {count}。「残す」「隠す」はすべてに適用されます。",
    "Selects on the Body; then choose Keep or Hide.": "素体の上で選びます。そのあと「残す」か「隠す」を選びます。",
    "No unsure faces": "要確認の面はありません",
    "Face": "面",
    "Face {index}": "面 {index}",
    "{part} face {index}": "{part} の面 {index}",
    "Material: {name}": "素材: {name}",
    "Inspect face": "面を見る",
    "Select a face on the Body, go to the next unsure face, or look along the ray that saw it":
        "素体の上で面を選ぶ、次の要確認の面に移る、または面を見た光線の向きから見ます",
    "Select": "選ぶ",
    "Next": "次へ",
    "View ray": "光線から見る",
    "Repair the existing mask": "既存マスクの修復",
    "Repair policy": "修復方針",
    "Choose which faces hidden by the existing mask are shown again. The verdicts do not change":
        "既存マスクが隠している面のうち、どれを再び表示するかを選びます。判定は変わりません",
    "Show visible and unsure faces again": "見える面と要確認の面を再表示",
    "Keep only faces confirmed hidden under the mask (strict)": "隠れていると確認できた面だけをマスクに残します（厳しめ）",
    "Show visible faces again": "見える面だけを再表示",
    "Keep the existing mask wherever no face was seen; unsure faces stay hidden":
        "見えなかった部分は既存マスクのままにします。要確認の面は隠れたままです",

    # Export
    "Faces the output hides: {count} ({percent}%)": "出力で隠す面: {count}（{percent}%）",
    "Some points still need attention. See Review.": "まだ注意が必要な点があります。「確認」を見てください。",
    "Create masked copy": "マスクで隠したコピーを作る",
    "Hides the faces with a Mask modifier. Easy to undo.": "Mask モディファイアで面を隠します。元に戻しやすい方法です。",
    "Create copy with faces removed": "面を削除したコピーを作る",
    "Deletes the faces but keeps shape keys, UVs and weights. Use this for FBX (VRChat).":
        "面を削除し、シェイプキー・UV・ウェイトは残します。FBX（VRChat）にはこちらを使います。",
    "Created: {names}": "作成: {names}",
    "Select the copy": "コピーを選択",
    "Select the copies made by the last output, ready to export": "直前に作ったコピーを選択し、書き出せる状態にします",
    "For FBX, select the copy and its Armature, then export with Selected Objects on and Apply Modifiers off.":
        "FBX では、コピーと Armature を選び、Selected Objects をオン、Apply Modifiers をオフにして書き出します。",
    "Export shareable report": "共有用レポートを書き出す",
    "Save a summary without mesh coordinates, connectivity, object or material names, or personal paths":
        "形状・面のつながり・オブジェクト名や素材名・個人のパスを含まない要約を保存します",
    "Include full diagnostics (contains mesh data)": "完全な診断データを含める（形状データを含みます）",
    "Includes purchased mesh geometry and names; never attach it to a public issue":
        "購入したモデルの形状や名前を含みます。公開の Issue には絶対に添付しないでください",
    "The original Body is never changed.": "元の素体は変更しません。",
    "Create output copy": "出力用のコピーを作る",
    "Create a copy of the Body that hides the hideable faces. The original is not changed":
        "隠せる面を隠した素体のコピーを作ります。元の素体は変更しません",
    "Remove the faces": "面を削除する",
    "Delete the faces on the copy instead of masking them, keeping shape keys, weights and UVs (for FBX)":
        "マスクで隠す代わりにコピーから面を削除し、シェイプキー・ウェイト・UV は残します（FBX 向け）",
    "Faces hidden: {faces} ({triangles} triangles)": "隠す面: {faces}（三角形 {triangles}）",
    "The copy is placed where the Body is. The original is not changed.":
        "コピーは素体と同じ位置に作ります。元の素体は変更しません。",
    "Inspected frames: {frames}": "調べたフレーム: {frames}",
    "Faces you hid that were judged visible or unsure: {count}": "自分で隠した面のうち、見える・要確認と判定された面: {count}",
    "Created {names}. The original is unchanged.": "{names} を作りました。元の素体は変わっていません。",

    # Reasons a face is unsure, and what to do
    "Seen along a sampled ray": "調べた光線で見えた",
    "Hidden in every sample": "すべてのサンプルで隠れている",
    "Body and clothing intersect": "素体と衣装が交差している",
    "Touching the clothing, or depth unclear": "衣装に接している、または前後が不明確",
    "Clothing shape could not be resolved": "衣装の形を判定しきれない",
    "Clothing has too many openings": "衣装の開口部が多すぎる",
    "Clothing mesh is non-manifold": "衣装のメッシュが非多様体",
    "Opening in Solidify clothing": "厚みを付けた衣装の開口部",
    "Sampling too coarse, or a degenerate face": "サンプルが粗い、または面が潰れている",
    "Material may be see-through": "素材が透けるかもしれない",
    "Shader not supported": "未対応のシェーダー",
    "Clothing has no material": "衣装に素材がない",
    "Material needs a node surface": "素材にノードの表面出力が必要",
    "Material is animated": "素材にアニメーションがある",
    "Backface culling is on": "裏面カリングが有効",
    "Not enough evidence": "判定の根拠が足りない",
    "Mask hides a visible face": "マスクが見える面を隠している",
    "Mask hides an unsure face": "マスクが要確認の面を隠している",
    "The existing mask is turned off": "既存マスクが無効になっている",
    "The existing mask hides nothing": "既存マスクは何も隠していない",
    "The existing mask hides every face (check Invert)": "既存マスクがすべての面を隠している（Invert を確認）",
    "If it is fully opaque, mark it Opaque and analyze again": "完全に不透明なら「不透明」にして調べ直します",
    "Look at it, and choose Hide if it is covered": "目で見て、隠れていれば「隠す」を選びます",
    "Fix the fit or weights; choose Hide only to hide poke-through":
        "衣装の位置やウェイトを直します。突き抜けを隠すだけなら「隠す」を選びます",
    "Give the clothing a material and analyze again": "衣装に素材を割り当てて調べ直します",
    "Turn culling off and analyze again, or decide by eye": "カリングを切って調べ直すか、目で見て決めます",
    "Fix the named clothing mesh, or decide by eye": "表示された衣装のメッシュを直すか、目で見て決めます",
    "Choose Fine and analyze again; if every face shows this, check the Body's scale":
        "細かさを「細かい」にして調べ直します。全面がこれなら、素体の大きさ（単位）を確認します",

    # Errors: what happened and how to fix it
    "Switch to Object Mode first.": "先にオブジェクトモードに切り替えてください。",
    "Choose a mesh as the Body.": "素体にメッシュを選んでください。",
    "Remove the empty entries from the Body parts.": "素体のパーツから空の項目を外してください。",
    "Add at least one clothing mesh, and remove empty entries.": "衣装のメッシュを1つ以上追加し、空の項目を外してください。",
    "An object is listed twice. The Body and its parts cannot also be clothing.":
        "同じオブジェクトが2回指定されています。素体とそのパーツは衣装にできません。",
    "Checking an existing mask works on one Body object at a time.":
        "既存マスクの検査は、素体のオブジェクト1つずつ行います。",
    "{name} is not a mesh with faces.": "{name} は面を持つメッシュではありません。",
    "{name} is linked or read-only. Make a local copy first.":
        "{name} はリンクされているか、読み取り専用です。ローカルのコピーを作ってください。",
    "{name} is hidden. Show it in this view layer.": "{name} が非表示です。このビューレイヤーで表示してください。",
    "{name} is hidden in renders. Turn rendering on for it.": "{name} はレンダーで非表示です。レンダーに表示してください。",
    "{name} is invisible to the camera, a holdout or a shadow catcher.":
        "{name} はカメラから見えない、ホールドアウト、またはシャドウキャッチャーです。",
    "A collection of {name} is excluded from rendering, a holdout or indirect only.":
        "{name} のコレクションが、レンダー対象外・ホールドアウト・間接のみのどれかになっています。",
    "{name} uses instancing, which is not supported.": "{name} はインスタンス化を使っていますが、対応していません。",
    "{name} has a zero or flattened scale. Fix the scale, or apply it (Ctrl+A > Scale) on a working copy.":
        "{name} のスケールが 0 か潰れています。スケールを直すか、作業用コピーで適用（Ctrl+A > Scale）してください。",
    "Choose the vertex-group Mask modifier to check.": "検査する、頂点グループ方式の Mask モディファイアを選んでください。",
    "Turn off Smooth on the Mask modifier, on a working copy.": "作業用コピーで、Mask モディファイアの Smooth をオフにしてください。",
    "The vertex group of the Mask modifier is missing.": "Mask モディファイアの頂点グループが見つかりません。",
    "Give the Mask modifier the same viewport and render visibility.":
        "Mask モディファイアのビューポートとレンダーの表示設定をそろえてください。",
    "Move the Mask modifier to the bottom of the stack.": "Mask モディファイアをスタックの一番下に移してください。",
    "The modifier {name} is not supported. Use a working copy with it applied.":
        "モディファイア {name} には対応していません。適用済みの作業用コピーを使ってください。",
    "The modifier {name} has different viewport and render visibility.":
        "モディファイア {name} のビューポートとレンダーの表示設定が違います。",
    "{name} changes its faces when evaluated. Use a working copy with its modifiers applied.":
        "{name} はモディファイアで面の構成が変わります。モディファイアを適用した作業用コピーを使ってください。",
    "{name} has no faces after its modifiers.": "{name} はモディファイアのあとに面が残りません。",
    "{name} has invalid vertex positions.": "{name} の頂点の位置が不正です。",
    "Blender's result did not match the plan, so nothing was changed. Please report this.":
        "Blender の結果が計画と一致しなかったため、何も変更していません。不具合として報告してください。",
    "Enter the frames as numbers separated by commas, for example 1, 10, 20.":
        "フレームはカンマ区切りの数字で入力してください（例: 1, 10, 20）。",
    "Choose between 1 and 32 valid frames.": "有効なフレームを 1〜32 個選んでください。",
    "The Body's faces or the existing mask change between frames, which is not supported.":
        "フレームによって素体の面や既存マスクが変わります。これには対応していません。",
    "Something changed during the analysis. Analyze again.": "調べている間に何かが変わりました。調べ直してください。",
    "An analysis is already running.": "すでに調べている最中です。",
    "Analyze first.": "先に調べてください。",
    "Leave Edit Mode on {name} first (Tab).": "先に {name} の編集モードを終えてください（Tab）。",
    "Switch {name} back to Object Mode first.": "先に {name} をオブジェクトモードに戻してください。",
    "Wait for the analysis to finish, or cancel it.": "調べ終わるまで待つか、中止してください。",
    "Select the Body last, so that it is the active mesh.": "素体を最後に選び、アクティブなメッシュにしてください。",
    "No faces selected: drag over the comparison first": "面が選ばれていません。先に比較メッシュの上をドラッグしてください",
    "No faces selected: press Box, Lasso or Brush, then drag over faces":
        "面が選ばれていません。「囲む」「投げ縄」「なぞる」を押して、面の上をドラッグしてください",
    "No unsure faces in the selection. Turn off Only change unsure faces to change others.":
        "選んだ範囲に要確認の面がありません。ほかの面を変えるには「要確認の面だけ変える」をオフにします。",
    "No matching faces": "当てはまる面がありません",
    "Face index out of range": "面の番号が範囲外です",
    "No ray was recorded for this face.": "この面には光線の記録がありません。",
    "Use View ray from a 3D View.": "「光線から見る」は 3D ビューから使ってください。",
    "The repair policy applies only when checking an existing mask.": "修復方針は、既存マスクを検査したときだけ使えます。",
    "The copy no longer exists.": "コピーが見つかりません。",
    "The comparison mesh was edited. Press Update and select again.":
        "比較メッシュが編集されています。「更新」を押して選び直してください。",
    "Choose a .json report filename": "レポートのファイル名は .json にしてください",
    "Do not write reports inside the installed Extension": "インストール済みのアドオンの中にはレポートを書き出せません",
}
