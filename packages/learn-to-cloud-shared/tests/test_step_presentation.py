"""Unit tests for StepAction + TipType presentation enums."""

from uuid import uuid4

import pytest

from learn_to_cloud_shared.schemas import (
    LearningStep,
    StepAction,
    TipItem,
    TipType,
)


@pytest.mark.unit
class TestStepAction:
    def test_label_capitalizes(self):
        assert StepAction.PRACTICE.label == "Practice"
        assert StepAction.WATCH.label == "Watch"

    def test_badge_classes_defined_for_every_member(self):
        for action in StepAction:
            assert action.badge_classes, f"missing badge classes for {action!r}"

    def test_explore_practice_reflect_get_distinct_colors(self):
        # The three "highlighted" actions must not collapse into the gray
        # bucket — the original template explicitly singled them out.
        colors = {
            StepAction.EXPLORE.badge_classes,
            StepAction.PRACTICE.badge_classes,
            StepAction.REFLECT.badge_classes,
        }
        assert len(colors) == 3


@pytest.mark.unit
class TestNormalizeStepActionOnLearningStep:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Practice:", StepAction.PRACTICE),
            ("practice", StepAction.PRACTICE),
            ("PRACTICE:", StepAction.PRACTICE),
            ("  Watch:  ", StepAction.WATCH),
            ("Build:", StepAction.BUILD),
        ],
    )
    def test_yaml_style_input_normalizes(self, raw, expected):
        step = LearningStep(uuid=uuid4(), slug="s", order=0, action=raw)
        assert step.action is expected

    def test_none_passes_through(self):
        step = LearningStep(uuid=uuid4(), slug="s", order=0, action=None)
        assert step.action is None

    def test_empty_string_becomes_none(self):
        step = LearningStep(uuid=uuid4(), slug="s", order=0, action="")
        assert step.action is None

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError, match="Unknown step action"):
            LearningStep(uuid=uuid4(), slug="s", order=0, action="frobnicate")


@pytest.mark.unit
class TestTipType:
    def test_default_is_tip(self):
        item = TipItem(text="hello")
        assert item.type is TipType.TIP

    def test_string_value_normalizes_to_enum(self):
        item = TipItem(type="warning", text="hi")
        assert item.type is TipType.WARNING

    def test_every_member_has_presentation(self):
        for t in TipType:
            assert t.icon
            assert t.container_classes
            assert t.text_classes

    def test_per_type_colors_differ(self):
        containers = {t.container_classes for t in TipType}
        assert len(containers) == len(TipType)
