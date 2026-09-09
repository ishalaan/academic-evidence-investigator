from types import SimpleNamespace

from package.agents.critic import critic_node
from package.schemas import Paper


class FakeClient:
    def chat_completion(self, **kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="""
                        {
                          "sufficient": false,
                          "reason": "The evidence is too limited.",
                          "suggested_queries": [
                            "additional academic performance evidence"
                          ]
                        }
                        """
                    )
                )
            ]
        )


def test_critic_returns_structured_decision(monkeypatch):
    monkeypatch.setattr(
        "package.agents.critic.get_llm_client",
        lambda: FakeClient(),
    )

    state = {
        "research_question": "Does generative AI improve academic performance?",
        "processed_papers": [
            Paper(
                title="Example Paper",
                authors=["A. Author"],
                abstract="An example abstract.",
                year=2025,
                source="Semantic Scholar",
            )
        ],
    }

    result = critic_node(state)

    decision = result["critic_decision"]

    assert decision.sufficient is False
    assert decision.reason == "The evidence is too limited."
    assert len(decision.suggested_queries) == 1