from types import SimpleNamespace

from package.agents.planner import planner_node


class FakeClient:
    def chat_completion(self, **kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="""
                        {
                          "research_goal": "Investigate generative AI in higher education",
                          "queries": [
                            "generative AI higher education",
                            "ChatGPT academic performance university students"
                          ]
                        }
                        """
                    )
                )
            ]
        )


def test_planner_returns_structured_search_plan(monkeypatch):
    monkeypatch.setattr(
        "package.agents.planner.get_llm_client",
        lambda: FakeClient(),
    )

    state = {
        "research_question": "Does generative AI improve academic performance?",
        "search_cycle": 0,
    }

    result = planner_node(state)

    assert result["search_cycle"] == 1
    assert result["search_plan"].research_goal == (
        "Investigate generative AI in higher education"
    )
    assert len(result["search_plan"].queries) == 2