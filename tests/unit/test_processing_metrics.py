from package.processing.pipeline import process_papers
from package.schemas import Paper


def test_metrics_distinguish_relevance_from_evidence_limit():
    papers = [Paper(title=f"Large language models in education study {i}",
                    abstract="Large language models in teaching and education", doi=f"10.1/{i}")
              for i in range(12)]
    metrics = {}
    result = process_papers(papers, "Large language models in education", metrics=metrics)
    assert len(result) == metrics["final_evidence_count"] == 10
    assert metrics["valid_papers_retained"] == metrics["relevant_papers_retained"] == 12
    assert metrics["evidence_limit_removed"] == 2
    assert metrics["duplicates_removed"] == metrics["noisy_records_removed"] == 0


def test_empty_processing_records_zero_counts():
    metrics = {}
    assert process_papers([], "Question", metrics=metrics) == []
    assert metrics and all(value == 0 for value in metrics.values())
