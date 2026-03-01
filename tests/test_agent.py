"""Tests for knowsql.agent.agent."""

import json

import pytest

from knowsql.agent.agent import run_agent, TableProposal, AGENT_TOOLS, SYSTEM_PROMPT
from knowsql.agent.navigator import IndexNavigator
from knowsql.llm.provider import LLMMessage, ToolCall


def _make_tool_response(tool_name, arguments, tool_id="tc_1"):
    """Create an LLMMessage that calls a tool."""
    return LLMMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id=tool_id, name=tool_name, arguments=arguments)],
    )


def _make_propose_response(tables, reasoning="Found the tables", joins=None):
    """Create an LLMMessage that calls propose_tables."""
    args = {"tables": tables, "reasoning": reasoning}
    if joins:
        args["joins"] = joins
    return _make_tool_response("propose_tables", args)


def test_agent_proposes_tables(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_tool_response("read_file", {"path": "INDEX.md"}, "tc_1"),
        _make_propose_response([{"table_name": "orders", "reason": "Needed for query"}]),
    ])
    result = run_agent("Show me all orders", nav, llm)
    assert isinstance(result, TableProposal)
    assert len(result.tables) == 1
    assert result.tables[0]["table_name"] == "orders"


def test_agent_reads_index_first(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_tool_response("read_file", {"path": "INDEX.md"}, "tc_1"),
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    run_agent("test query", nav, llm)
    # First LLM call should have been made
    assert len(llm.calls) == 2


def test_agent_handles_list_directory(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_tool_response("list_directory", {"path": "domains/"}, "tc_1"),
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    result = run_agent("test query", nav, llm)
    assert result.tables[0]["table_name"] == "orders"


def test_agent_text_only_response(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        LLMMessage(role="assistant", content="I cannot determine the right tables."),
    ])
    result = run_agent("test query", nav, llm)
    assert result.tables == []
    assert "cannot determine" in result.reasoning


def test_agent_max_steps_exhaustion(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    # Create enough read_file calls to exhaust max_steps
    responses = [
        _make_tool_response("read_file", {"path": "INDEX.md"}, f"tc_{i}")
        for i in range(5)
    ]
    # After exhaustion, the agent gets one more chance
    responses.append(_make_propose_response([{"table_name": "orders", "reason": "best guess"}]))
    llm = mock_llm(responses)
    result = run_agent("test", nav, llm, max_steps=3)
    assert result.exhausted is True


def test_agent_files_read_tracked(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_tool_response("read_file", {"path": "INDEX.md"}, "tc_1"),
        _make_tool_response("read_file", {"path": "domains/sales/DOMAIN.md"}, "tc_2"),
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    result = run_agent("test", nav, llm)
    assert "INDEX.md" in result.files_read
    assert "domains/sales/DOMAIN.md" in result.files_read


def test_agent_unknown_tool(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_tool_response("nonexistent_tool", {}, "tc_1"),
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    result = run_agent("test", nav, llm)
    # Should not crash, unknown tool returns error message
    assert len(result.tables) == 1


def test_agent_conversation_history(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    history = [{"question": "prev question", "tables": ["customers"], "sql": "SELECT * FROM customers"}]
    result = run_agent("follow up", nav, llm, conversation_history=history)
    # Check that history was included in messages
    messages = llm.calls[0][1]  # first call's messages
    history_msg = next(m for m in messages if m.role == "user" and "Previous questions" in m.content)
    assert "prev question" in history_msg.content


def test_agent_conversation_history_capped(sample_index_dir, mock_llm):
    """Bug #11 regression: Only last 10 entries used."""
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    history = [{"question": f"q{i}", "tables": []} for i in range(20)]
    run_agent("test", nav, llm, conversation_history=history)
    messages = llm.calls[0][1]
    history_msg = next(m for m in messages if m.role == "user" and "Previous questions" in m.content)
    # Should only contain last 10 (q10-q19)
    assert "q0" not in history_msg.content
    assert "q19" in history_msg.content


def test_agent_user_correction(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    run_agent("test", nav, llm, user_correction="Use customers table instead")
    messages = llm.calls[0][1]
    user_msgs = [m for m in messages if m.role == "user"]
    assert any("Use customers table instead" in m.content for m in user_msgs)


def test_agent_show_navigation(sample_index_dir, mock_llm, capsys):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_tool_response("read_file", {"path": "INDEX.md"}, "tc_1"),
        _make_propose_response([{"table_name": "orders", "reason": "test"}]),
    ])
    run_agent("test", nav, llm, show_navigation=True)
    captured = capsys.readouterr()
    assert "Step 1" in captured.out


def test_agent_empty_proposal(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_propose_response([], reasoning="No suitable tables found"),
    ])
    result = run_agent("test", nav, llm)
    assert result.tables == []
    assert result.reasoning == "No suitable tables found"


def test_agent_proposal_with_joins(sample_index_dir, mock_llm):
    nav = IndexNavigator(str(sample_index_dir))
    llm = mock_llm([
        _make_propose_response(
            [{"table_name": "orders", "reason": "t1"}, {"table_name": "customers", "reason": "t2"}],
            joins=[{"left": "orders.customer_id", "right": "customers.id"}],
        ),
    ])
    result = run_agent("test", nav, llm)
    assert len(result.joins) == 1
    assert result.joins[0]["left"] == "orders.customer_id"


def test_system_prompt_contains_instructions():
    assert "INDEX.md" in SYSTEM_PROMPT
    assert "propose_tables" in SYSTEM_PROMPT
    assert "RELATIONSHIPS.md" in SYSTEM_PROMPT
