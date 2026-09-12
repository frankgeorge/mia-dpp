"""Tests for offline chat orchestration and explainable review states."""

from mia_dpp.chat import demo_turn
from mia_dpp.domain.mappings import GraphEntry, MappingStatus
from mia_dpp.llm.chat import ChatMessage, ChatRequest


def test_demo_turn_returns_official_targets_and_explainable_scores() -> None:
    response = demo_turn(
        ChatRequest(
            messages=(
                ChatMessage(
                    role="user",
                    content=(
                        "AFRISO gauge, model RF100-16, serial number 2024-8871, "
                        "built 2024, IP65, 0-16 bar, material number 63820."
                    ),
                ),
            )
        )
    )

    assert response.mode == "demo"
    assert response.proposal is not None
    serial = next(
        item for item in response.proposal.mappings if item.target_element == "SerialNumber"
    )
    order_code = next(
        item
        for item in response.proposal.mappings
        if item.target_element == "OrderCodeOfManufacturer"
    )
    assert serial.status is MappingStatus.AUTO
    assert order_code.status is MappingStatus.REVIEW
    assert serial.semantic_id == "0112/2///61987#ABA951#009"
    assert len(serial.confidence_assessment.factors) == 5
    assert serial.confidence_assessment.remaining_uncertainty == (
        "The current value appears in only one source and is not corroborated.",
    )


def test_history_reduces_target_ambiguity_but_does_not_corroborate_value() -> None:
    request = ChatRequest(
        messages=(
            ChatMessage(
                role="user",
                content="SCHUNK module, order code JGZ-100-1, 2022.",
            ),
        ),
        graph=(
            GraphEntry(
                source_field="MATNR",
                target_element="OrderCodeOfManufacturer",
                semantic_id="legacy-browser-value-is-not-trusted",
                verified_at="2026-01-02T03:04:05Z",
                corrections=4,
            ),
        ),
    )

    response = demo_turn(request)

    assert response.proposal is not None
    order_code = next(
        item
        for item in response.proposal.mappings
        if item.target_element == "OrderCodeOfManufacturer"
    )
    factors = {item.code: item for item in order_code.confidence_assessment.factors}
    assert order_code.from_graph
    assert factors["destination_ambiguity"].awarded == 0.22
    assert factors["independent_corroboration"].awarded == 0.0
    assert "not corroborated" in order_code.confidence_assessment.remaining_uncertainty[-1]
    assert order_code.semantic_id != request.graph[0].semantic_id


def test_generate_command_keeps_the_workspace_contract() -> None:
    response = demo_turn(
        ChatRequest(messages=(ChatMessage(role="user", content="generate passport"),))
    )

    assert response.generate
    assert response.proposal is None
    assert response.nameplate_elements
    assert response.nameplate_elements[0].target.template_release == "3.0.1"
