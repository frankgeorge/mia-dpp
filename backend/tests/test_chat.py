"""Tests for the chat behavior moved out of the Next.js API route."""

from mia_dpp.chat import demo_turn
from mia_dpp.models import ChatMessage, ChatRequest, GraphEntry, MappingStatus


def test_demo_turn_proposes_the_same_mappings_and_review_states() -> None:
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
    statuses = {
        mapping.target_element: mapping.status for mapping in response.proposal.mappings
    }
    assert statuses["ManufacturerName"] is MappingStatus.AUTO
    assert statuses["OrderCode"] is MappingStatus.REVIEW


def test_verified_graph_mapping_is_reused() -> None:
    response = demo_turn(
        ChatRequest(
            messages=(
                ChatMessage(
                    role="user",
                    content="SCHUNK module, order code JGZ-100-1, 2022.",
                ),
            ),
            graph=(
                GraphEntry(
                    source_field="MATNR",
                    target_element="OrderCode",
                    semantic_id="0173-1#02-AAO227#002",
                    verified_at="2026-01-02T03:04:05Z",
                    corrections=1,
                ),
            ),
        )
    )

    assert response.proposal is not None
    order_code = next(
        item for item in response.proposal.mappings if item.target_element == "OrderCode"
    )
    assert order_code.from_graph
    assert order_code.confidence == 0.99
    assert order_code.status is MappingStatus.AUTO


def test_generate_command_keeps_the_existing_chat_contract() -> None:
    response = demo_turn(
        ChatRequest(messages=(ChatMessage(role="user", content="generate passport"),))
    )

    assert response.generate
    assert response.proposal is None
