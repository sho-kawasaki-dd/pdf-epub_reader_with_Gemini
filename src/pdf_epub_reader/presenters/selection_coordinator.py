"""複数選択スロットの状態管理を担う Coordinator。

MainPresenter から「選択スロットの ID 採番・順序管理・世代管理」という
独立した関心ごとを切り出した純粋な状態機械である。

View や PanelPresenter には直接触らず、状態が変化したタイミングを
コールバック (`on_snapshot_changed` / `on_threshold_crossed`) で外部に通知する。
これにより、

- View / PanelPresenter なしで単体テストできる
- MainPresenter は「通知 → View/Panel への反映」のみを担当する
- 将来 selection の永続化や undo を追加する際にここだけを差し替えれば良い

という分離を実現する。
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace

from pdf_epub_reader.dto import (
    RectCoords,
    SelectionContent,
    SelectionSlot,
    SelectionSnapshot,
)


class SelectionCoordinator:
    """選択スロット集合の生成・更新・削除を一元管理する。

    重要な不変条件:
    - スロットは `OrderedDict` に挿入順で保持される
    - `display_number` は常に 1 始まりで、現在の挿入順に詰め直される
    - `selection_id` は払い出し後に決して再利用されない
    - `_generation` は「全置換」相当の操作 (非 append 予約 / 明示クリア) の
      たびに増加し、古い世代の遅延結果を破棄するためのキーになる
    """

    def __init__(
        self,
        on_snapshot_changed: Callable[[SelectionSnapshot], None],
        on_threshold_crossed: Callable[[], None],
        warning_threshold: int = 10,
    ) -> None:
        """状態変化通知を受け取るコールバックを登録する。

        Args:
            on_snapshot_changed: スロット集合が更新されるたびに呼ばれる。
                受け取った snapshot を View / PanelPresenter に伝搬する想定。
            on_threshold_crossed: スロット数が `warning_threshold` を超えた
                瞬間 (またぎ時) に 1 回だけ呼ばれる。
            warning_threshold: 警告を発火するスロット数の閾値。
        """
        self._slots: OrderedDict[str, SelectionSlot] = OrderedDict()
        self._generation: int = 0
        self._next_id: int = 1
        self._warning_threshold = warning_threshold
        self._on_snapshot_changed = on_snapshot_changed
        self._on_threshold_crossed = on_threshold_crossed

    # --- Read-only views ---

    @property
    def snapshot(self) -> SelectionSnapshot:
        """内部の順序付き状態からスナップショット DTO を構築する。"""
        return SelectionSnapshot(slots=tuple(self._slots.values()))

    @property
    def generation(self) -> int:
        """現在の世代番号を返す (主にテスト用)。"""
        return self._generation

    def has_slot(self, selection_id: str) -> bool:
        """指定 ID のスロットが現存するかを返す。"""
        return selection_id in self._slots

    def is_current(self, selection_id: str, generation: int) -> bool:
        """遅延結果が現行の選択世代に属するかを判定する。"""
        return generation == self._generation and selection_id in self._slots

    # --- Mutating operations ---

    def reserve_slot(
        self, page_number: int, rect: RectCoords, *, append: bool
    ) -> tuple[str, int]:
        """新しいスロットを確保し、その ID と世代番号を返す。

        `append=False` の場合は既存スロットを全置換するため、世代番号が増加する。
        払い出し直後に snapshot 通知を行い、閾値またぎが発生したら警告通知も行う。
        """
        previous_count = len(self._slots)
        if not append:
            self._generation += 1
            self._slots.clear()

        selection_id = f"selection-{self._next_id}"
        self._next_id += 1

        self._slots[selection_id] = SelectionSlot(
            selection_id=selection_id,
            display_number=len(self._slots) + 1,
            page_number=page_number,
            rect=rect,
            read_state="pending",
        )
        self._renumber()
        self._emit()

        current_count = len(self._slots)
        if (
            previous_count <= self._warning_threshold
            and current_count > self._warning_threshold
        ):
            self._on_threshold_crossed()

        return selection_id, self._generation

    def apply_extracted_content(
        self,
        selection_id: str,
        generation: int,
        content: SelectionContent,
    ) -> bool:
        """確保済みスロットに抽出結果を差し込む。

        Returns:
            適用に成功したら True。世代不一致やスロット削除済みのため
            破棄した場合は False。
        """
        if not self.is_current(selection_id, generation):
            return False

        self._slots[selection_id] = replace(
            self._slots[selection_id],
            read_state="ready",
            extracted_text=content.extracted_text,
            has_thumbnail=content.cropped_image is not None,
            content=content,
            error_message=None,
        )
        self._emit()
        return True

    def mark_error(
        self, selection_id: str, generation: int, message: str
    ) -> bool:
        """抽出失敗時にスロットをエラー状態に更新する。

        Returns:
            適用に成功したら True。世代不一致などで破棄した場合は False。
        """
        if not self.is_current(selection_id, generation):
            return False

        self._slots[selection_id] = replace(
            self._slots[selection_id],
            read_state="error",
            extracted_text="",
            has_thumbnail=False,
            content=None,
            error_message=message,
        )
        self._emit()
        return True

    def delete_slot(self, selection_id: str) -> bool:
        """指定スロットを削除し、表示番号を詰め直す。

        Returns:
            存在し削除した場合は True、未知 ID なら False。
        """
        if selection_id not in self._slots:
            return False
        del self._slots[selection_id]
        self._renumber()
        self._emit()
        return True

    def clear(self, *, increment_generation: bool) -> None:
        """全スロットを破棄する。

        `increment_generation=True` を指定すると、進行中の遅延結果が
        新しい状態に紛れ込まないよう世代番号を進める。
        """
        if increment_generation:
            self._generation += 1
        self._slots.clear()
        self._emit()

    # --- Internal helpers ---

    def _renumber(self) -> None:
        """挿入順に沿って表示番号を 1 始まりで振り直す。"""
        self._slots = OrderedDict(
            (
                selection_id,
                replace(slot, display_number=index),
            )
            for index, (selection_id, slot) in enumerate(
                self._slots.items(), start=1
            )
        )

    def _emit(self) -> None:
        """現在の snapshot を通知コールバックに渡す。"""
        self._on_snapshot_changed(self.snapshot)
