# student_workspace

本ディレクトリは、ハンズオンを実施するためのものです。

- `notebooks/` : 演習ノートブック（ `10_prompt_leaking.ipynb` から実行していきましょう。）
- `edit_targets/` : 防御の実践を行うファイル群


## 初期状態へ戻す方法

ノートブックで次を実行すると、`edit_targets/` を初期状態へ戻してアプリに再同期します。

```python
from broken_handson import launcher
launcher.reset_edit_targets()
```
