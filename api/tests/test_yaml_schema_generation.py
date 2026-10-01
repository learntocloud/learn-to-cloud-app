"""Tests for curriculum YAML authoring schemas."""

from scripts.generate_yaml_schemas import _topic_authoring_schema


def test_topic_schema_matches_authored_yaml_contract():
    schema = _topic_authoring_schema()

    assert "order" not in schema["properties"]
    assert "order" not in schema["required"]
    assert schema["additionalProperties"] is False


def test_topic_schema_accepts_authored_step_action_labels():
    action_values = _topic_authoring_schema()["$defs"]["StepAction"]["enum"]

    assert "practice" in action_values
    assert "Practice:" in action_values
