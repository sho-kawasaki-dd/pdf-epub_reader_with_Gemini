"""SelectionCoordinator の純粋な状態機械としての振る舞いを検証する。"""

from __future__ import annotations

from pdf_epub_reader.dto import (
    RectCoords,
    SelectionContent,
    SelectionSnapshot,
)
from pdf_epub_reader.presenters.selection_coordinator import SelectionCoordinator


class _Recorder:
    """コールバック呼び出しを記録するシンプルなヘルパー。"""

    def __init__(self) -> None:
        self.snapshots: list[SelectionSnapshot] = []
        self.threshold_count: int = 0

    def on_snapshot_changed(self, snapshot: SelectionSnapshot) -> None:
        self.snapshots.append(snapshot)

    def on_threshold_crossed(self) -> None:
        self.threshold_count += 1


def _make_coordinator(
    *, warning_threshold: int = 10
) -> tuple[SelectionCoordinator, _Recorder]:
    recorder = _Recorder()
    coordinator = SelectionCoordinator(
        on_snapshot_changed=recorder.on_snapshot_changed,
        on_threshold_crossed=recorder.on_threshold_crossed,
        warning_threshold=warning_threshold,
    )
    return coordinator, recorder


def _rect(offset: float = 0.0) -> RectCoords:
    return RectCoords(
        x0=offset, y0=offset, x1=offset + 10.0, y1=offset + 10.0
    )


class TestReserveSlot:
    def test_first_reserve_emits_pending_snapshot(self) -> None:
        coord, rec = _make_coordinator()

        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)

        assert sel_id == "selection-1"
        assert gen == 1
        assert len(rec.snapshots) == 1
        slots = rec.snapshots[-1].slots
        assert len(slots) == 1
        assert slots[0].selection_id == sel_id
        assert slots[0].display_number == 1
        assert slots[0].read_state == "pending"

    def test_append_keeps_existing_slots_and_increments_display_numbers(
        self,
    ) -> None:
        coord, rec = _make_coordinator()
        coord.reserve_slot(0, _rect(0), append=False)
        first_gen = coord.generation

        sel_id, gen = coord.reserve_slot(1, _rect(20), append=True)

        # append=True なら世代は変わらない
        assert gen == first_gen
        slots = rec.snapshots[-1].slots
        assert [s.page_number for s in slots] == [0, 1]
        assert [s.display_number for s in slots] == [1, 2]
        assert sel_id == "selection-2"

    def test_non_append_replaces_and_bumps_generation(self) -> None:
        coord, rec = _make_coordinator()
        _id1, gen1 = coord.reserve_slot(0, _rect(), append=False)

        _id2, gen2 = coord.reserve_slot(2, _rect(30), append=False)

        assert gen2 == gen1 + 1
        slots = rec.snapshots[-1].slots
        assert len(slots) == 1
        assert slots[0].page_number == 2
        assert slots[0].display_number == 1

    def test_selection_ids_are_never_reused(self) -> None:
        coord, _rec = _make_coordinator()
        ids = [
            coord.reserve_slot(i, _rect(i), append=(i > 0))[0]
            for i in range(3)
        ]
        # 全置換しても新しい ID が払い出される
        new_id, _ = coord.reserve_slot(99, _rect(), append=False)
        assert new_id not in ids
        assert len(set(ids + [new_id])) == 4


class TestThresholdWarning:
    def test_warning_fires_once_when_crossing_threshold(self) -> None:
        coord, rec = _make_coordinator(warning_threshold=3)

        for i in range(5):
            coord.reserve_slot(i, _rect(i), append=(i > 0))

        # 4 件目を追加した瞬間に 1 回だけ発火
        assert rec.threshold_count == 1

    def test_warning_does_not_fire_below_threshold(self) -> None:
        coord, rec = _make_coordinator(warning_threshold=3)

        for i in range(3):
            coord.reserve_slot(i, _rect(i), append=(i > 0))

        assert rec.threshold_count == 0


class TestApplyExtractedContent:
    def test_apply_content_marks_slot_ready(self) -> None:
        coord, rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)

        applied = coord.apply_extracted_content(
            sel_id,
            gen,
            SelectionContent(
                page_number=0,
                rect=_rect(),
                extracted_text="hello",
                cropped_image=b"img",
            ),
        )

        assert applied is True
        slot = rec.snapshots[-1].slots[0]
        assert slot.read_state == "ready"
        assert slot.extracted_text == "hello"
        assert slot.has_thumbnail is True

    def test_apply_to_old_generation_is_discarded(self) -> None:
        coord, _rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)
        # 世代を進める (= 全置換)
        coord.reserve_slot(1, _rect(20), append=False)

        applied = coord.apply_extracted_content(
            sel_id,
            gen,
            SelectionContent(
                page_number=0, rect=_rect(), extracted_text="late"
            ),
        )

        assert applied is False

    def test_apply_to_deleted_slot_is_discarded(self) -> None:
        coord, _rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)
        coord.delete_slot(sel_id)

        applied = coord.apply_extracted_content(
            sel_id,
            gen,
            SelectionContent(
                page_number=0, rect=_rect(), extracted_text="late"
            ),
        )

        assert applied is False


class TestMarkError:
    def test_mark_error_updates_slot(self) -> None:
        coord, rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)

        applied = coord.mark_error(sel_id, gen, "boom")

        assert applied is True
        slot = rec.snapshots[-1].slots[0]
        assert slot.read_state == "error"
        assert slot.error_message == "boom"
        assert slot.has_thumbnail is False

    def test_mark_error_for_old_generation_is_discarded(self) -> None:
        coord, _rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)
        coord.reserve_slot(1, _rect(20), append=False)  # bump generation

        applied = coord.mark_error(sel_id, gen, "boom")

        assert applied is False


class TestDeleteSlot:
    def test_delete_renumbers_remaining_slots(self) -> None:
        coord, rec = _make_coordinator()
        id1, _ = coord.reserve_slot(0, _rect(0), append=False)
        coord.reserve_slot(1, _rect(20), append=True)
        coord.reserve_slot(2, _rect(40), append=True)

        deleted = coord.delete_slot(id1)

        assert deleted is True
        slots = rec.snapshots[-1].slots
        assert len(slots) == 2
        assert [s.page_number for s in slots] == [1, 2]
        assert [s.display_number for s in slots] == [1, 2]

    def test_delete_unknown_id_returns_false_and_does_not_emit(self) -> None:
        coord, rec = _make_coordinator()
        coord.reserve_slot(0, _rect(), append=False)
        emit_count_before = len(rec.snapshots)

        result = coord.delete_slot("unknown-id")

        assert result is False
        assert len(rec.snapshots) == emit_count_before


class TestClear:
    def test_clear_with_increment_bumps_generation(self) -> None:
        coord, rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)

        coord.clear(increment_generation=True)

        assert coord.generation == gen + 1
        assert rec.snapshots[-1].is_empty
        # クリア後の遅延結果は破棄されるべき
        assert (
            coord.apply_extracted_content(
                sel_id,
                gen,
                SelectionContent(
                    page_number=0, rect=_rect(), extracted_text="late"
                ),
            )
            is False
        )

    def test_clear_without_increment_keeps_generation(self) -> None:
        coord, _rec = _make_coordinator()
        _sel_id, gen = coord.reserve_slot(0, _rect(), append=False)

        coord.clear(increment_generation=False)

        assert coord.generation == gen


class TestIsCurrent:
    def test_is_current_true_for_live_slot_in_same_generation(self) -> None:
        coord, _rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)
        assert coord.is_current(sel_id, gen) is True

    def test_is_current_false_after_generation_bump(self) -> None:
        coord, _rec = _make_coordinator()
        sel_id, gen = coord.reserve_slot(0, _rect(), append=False)
        coord.reserve_slot(1, _rect(20), append=False)
        assert coord.is_current(sel_id, gen) is False
