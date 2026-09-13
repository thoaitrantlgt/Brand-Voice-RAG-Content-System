import json

from app.tools.search_tracker import TrackingSearchTool


class SearchTool:
    def _run(self, *, query):
        return json.dumps(
            {
                "organic": [
                    {
                        "title": "Google helpful content",
                        "link": "https://developers.google.com/search/docs/helpful",
                        "snippet": "Create helpful, reliable, people-first content.",
                    },
                    {
                        "title": "Duplicate",
                        "link": "https://developers.google.com/search/docs/helpful",
                        "snippet": "Same URL should be deduplicated.",
                    },
                ]
            }
        )


def test_search_tracker_returns_structured_provenance_and_deduplicates_urls():
    tracker = TrackingSearchTool(inner_tool=SearchTool())

    tracker._run("people first SEO")
    report = tracker.research_report()

    assert report == {
        "query_variations": ["people first SEO"],
        "sources": [
            {
                "query": "people first SEO",
                "title": "Google helpful content",
                "url": "https://developers.google.com/search/docs/helpful",
                "snippet": "Create helpful, reliable, people-first content.",
                "domain": "developers.google.com",
            }
        ],
        "source_urls": ["https://developers.google.com/search/docs/helpful"],
    }
