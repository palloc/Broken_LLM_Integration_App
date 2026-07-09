# student_workspace

受講者向けの作業領域です。通常はこのフォルダ配下だけを見て演習します。

- `notebooks/` : 演習ノートブック（最初は `10_prompt_leaking.ipynb`）
- `edit_targets/` : 受講者が編集する防御コード

## 使い方

1. `notebooks/10_prompt_leaking.ipynb` を開く
2. セルを上から実行して `launcher.start()` まで進める
3. 防御コードを編集したら `launcher.sync_edit_targets()` を実行して反映する

## 初期状態へ戻す

ノートブックで次を実行すると、`edit_targets/` を初期状態へ戻してアプリに再同期します。

```python
from broken_handson import launcher
launcher.reset_edit_targets()
```
