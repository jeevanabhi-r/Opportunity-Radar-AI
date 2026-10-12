import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

import app


@pytest.fixture(autouse=True)
def mock_source_dns_resolution(monkeypatch):
    original_check = app.is_public_source_host

    async def public_host(hostname):
        return bool(hostname)

    monkeypatch.setattr(app, "is_public_source_host", public_host)
    return original_check


class FakeResponse:
    def __init__(self, *, text, status_code=200, url="https://example.com/opportunity", headers=None):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def get(self, *args, **kwargs):
        return self.response


class FakeSerpApiResponse:
    status_code = 200
    text = ""

    def __init__(self, results):
        self.results = results

    def json(self):
        return {"organic_results": self.results}


class FakeSerpApiClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def get(self, *args, **kwargs):
        return self.response


def test_classify_opportunity_rejects_event_dates_as_deadlines():
    result = {
        "title": "AI Innovation Hackathon 2025",
        "snippet": "Event date: 25 June 2025 at IIT Delhi. Registration opens soon.",
        "date": "25 June 2025",
    }

    classified = app.classify_opportunity(result)

    assert classified["deadline"] is None
    assert classified["opportunity_status"] == "unverified"
    assert "No explicit application deadline" in classified["deadline_evidence"]


def test_classify_opportunity_handles_future_and_past_deadlines():
    future_date = date.today() + timedelta(days=12)
    future_result = {"title": "Cybersecurity internship", "snippet": f"Application deadline is {future_date.strftime('%d %B %Y')}. Apply now."}
    future = app.classify_opportunity(future_result)
    assert future["deadline"] == future_date.isoformat()
    assert future["opportunity_status"] in {"deadline_soon", "deadline_upcoming"}

    past_date = date.today() - timedelta(days=5)
    past_result = {"title": "Scholarship opportunity", "snippet": f"Last date to apply was {past_date.strftime('%d %B %Y')}"}
    past = app.classify_opportunity(past_result)
    assert past["deadline"] == past_date.isoformat()
    assert past["opportunity_status"] == "potentially_expired"


def test_verify_one_source_status_is_conservative_and_separate():
    future_deadline = (date.today() + timedelta(days=30)).strftime("%d %B %Y")
    page_text = f"Applications are open. The deadline is {future_deadline}."
    client = FakeAsyncClient(FakeResponse(text=f"<html><body>{page_text}</body></html>", url="https://official.example.com/apply"))
    result = {"title": "AI internship", "link": "https://official.example.com/apply", "snippet": "Official source"}

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())

    assert checked["source_check_status"] == "checked"
    assert checked["source_verified"] is False
    assert checked["source_content_readable"] is True
    assert checked["employer_source_verified"] is False
    assert checked["application_status"] == "open"
    assert checked["deadline_verified"] is True
    assert checked["deadline"] == (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    assert checked["opportunity_status"] in {"deadline_soon", "deadline_upcoming"}

    directory_text = "<html><body>Explore all hackathons in India. Applications are open.</body></html>"
    directory_result = {"title": "Hackathons in India", "link": "https://unstop.com/hackathons", "snippet": "Search page", "listing_quality": "Directory / listing page"}
    directory_client = FakeAsyncClient(FakeResponse(text=directory_text, url="https://unstop.com/hackathons"))

    async def run_directory():
        return await app.verify_one_source(directory_client, directory_result)

    directory = asyncio.run(run_directory())
    assert directory["application_status"] == "unknown"
    assert directory["deadline_verified"] is False


@pytest.mark.parametrize("status_code", [404, 410])
def test_unavailable_event_sources_remain_explicitly_unverified_leads(status_code):
    result = {
        "title": "Scouts AI Agents Challenge",
        "snippet": "Event registration deadline 30 October 2026.",
        "source": "Scouts by Yutori",
        "link": "https://events.example.org/scouts-ai-agents",
        "listing_quality": "Specific opportunity page",
        "deadline": "2026-10-30",
        "opportunity_status": "deadline_upcoming",
        "application_status": "open",
    }
    client = FakeAsyncClient(FakeResponse(
        text="",
        status_code=status_code,
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())
    row = app.build_overview_rows([checked])[0]

    assert checked["source_check_status"] == "unreachable"
    assert checked["source_content_readable"] is False
    assert checked["source_verified"] is False
    assert checked["employer_source_verified"] is False
    assert checked["source_page_type"] == "Specific opportunity page"
    assert checked["listing_quality"] == "Unverified lead — source unreachable"
    assert checked["application_status"] == "unknown"
    assert checked["deadline"] is None
    assert checked["deadline_verified"] is False
    assert checked["opportunity_status"] == "unverified"
    assert checked["link"] == result["link"]
    assert f"HTTP {status_code}" in checked["source_check_note"]
    assert "unverified" in row["source_check"].lower()
    assert "unreachable" in row["source_check"].lower()


def test_source_timeout_marks_lead_unreachable_without_confirmation():
    result = {
        "title": "AI Student Hackathon",
        "snippet": "Registration deadline 30 October 2026.",
        "source": "Event platform",
        "link": "https://events.example.org/hackathon/42",
        "listing_quality": "Specific opportunity page",
        "deadline": "2026-10-30",
        "opportunity_status": "deadline_upcoming",
    }

    class TimeoutClient:
        async def get(self, *args, **kwargs):
            raise app.httpx.TimeoutException("timed out")

    async def run():
        return await app.verify_one_source(TimeoutClient(), result)

    checked = asyncio.run(run())

    assert checked["source_check_status"] == "unreachable"
    assert checked["source_content_readable"] is False
    assert checked["listing_quality"] == "Unverified lead — source unreachable"
    assert checked["application_status"] == "unknown"
    assert checked["deadline"] is None
    assert checked["deadline_verified"] is False
    assert checked["opportunity_status"] == "unverified"
    assert "TimeoutException" in checked["source_check_note"]
    assert checked["link"] == result["link"]


def test_source_check_blocks_private_address_and_private_redirect(monkeypatch):
    result = {
        "title": "AI Student Hackathon",
        "link": "https://events.example.org/hackathon/42",
        "listing_quality": "Specific opportunity page",
    }
    calls = []

    class RedirectClient:
        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(
                text="",
                status_code=302,
                url=url,
                headers={"location": "http://127.0.0.1/admin"},
            )

    async def mocked_public_host(hostname):
        return hostname == "events.example.org"
    monkeypatch.setattr(app, "is_public_source_host", mocked_public_host)

    async def run():
        return await app.verify_one_source(RedirectClient(), result)

    checked = asyncio.run(run())

    assert len(calls) == 1
    assert calls[0][1]["follow_redirects"] is False
    assert checked["source_check_status"] == "unreachable"
    assert checked["application_status"] == "unknown"
    assert checked["deadline"] is None
    assert checked["link"] == "https://events.example.org/hackathon/42"


def test_source_host_guard_rejects_local_and_private_ip_literals(mock_source_dns_resolution):
    is_public_source_host = mock_source_dns_resolution

    async def run():
        return [
            await is_public_source_host("localhost"),
            await is_public_source_host("127.0.0.1"),
            await is_public_source_host("192.168.1.10"),
            await is_public_source_host("::1"),
        ]

    assert asyncio.run(run()) == [False, False, False, False]


def test_source_host_guard_rejects_private_dns_answers(
    monkeypatch, mock_source_dns_resolution
):
    is_public_source_host = mock_source_dns_resolution
    monkeypatch.setattr(
        app.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (app.socket.AF_INET, app.socket.SOCK_STREAM, app.socket.IPPROTO_TCP, "", ("10.0.0.8", 0))
        ],
    )

    assert asyncio.run(is_public_source_host("attacker.example")) is False


def test_readable_third_party_source_does_not_verify_identity_or_infer_status():
    result = {
        "title": "AI Student Hackathon",
        "snippet": "A student event.",
        "source": "Third-party event platform",
        "link": "https://events.example.org/hackathon/42",
        "listing_quality": "Specific opportunity page",
    }
    client = FakeAsyncClient(FakeResponse(
        text="<html><body>Independent event information without current application details.</body></html>",
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())

    assert checked["source_check_status"] == "checked"
    assert checked["source_content_readable"] is True
    assert checked["source_verified"] is False
    assert checked["employer_source_verified"] is False
    assert checked["application_status"] == "unknown"
    assert checked["deadline"] is None
    assert checked["deadline_verified"] is False
    assert "identity" in checked["source_check_note"].lower()


def test_missing_page_deadline_evidence_clears_search_snippet_deadline():
    result = {
        "title": "AI Student Hackathon",
        "snippet": "Registration deadline 30 October 2026.",
        "link": "https://events.example.org/hackathon/42",
        "deadline": "2026-10-30",
        "opportunity_status": "deadline_upcoming",
    }
    client = FakeAsyncClient(FakeResponse(
        text="<html><body>Event date: 30 October 2026. Applications may open later.</body></html>",
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())

    assert checked["source_check_status"] == "checked"
    assert checked["application_status"] == "unknown"
    assert checked["deadline"] is None
    assert checked["deadline_verified"] is False
    assert checked["opportunity_status"] == "unverified"
    assert "No explicit application deadline" in checked["deadline_evidence"]


def test_third_party_job_page_is_never_employer_verified_or_assumed_open():
    result = {
        "title": "Cybersecurity Analyst at Acme",
        "link": "https://www.indeed.com/viewjob?jk=123",
        "snippet": "Applications are open. Apply now.",
        "listing_quality": "Individual job portal listing — secondary source",
        "job_result_tier": "secondary",
    }
    client = FakeAsyncClient(FakeResponse(
        text="<html><body>Applications are open. Apply now.</body></html>",
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())

    assert checked["source_check_status"] == "checked"
    assert checked["source_content_readable"] is True
    assert checked["source_verified"] is False
    assert checked["employer_source_verified"] is False
    assert checked["application_status"] == "unknown"
    assert "identity" in checked["source_check_note"].lower()


def test_listing_quality_distinguishes_direct_pages_from_directories():
    directory_result = {"title": "Unstop Hackathons in India", "snippet": "Browse and discover all opportunities", "link": "https://unstop.com/hackathons"}
    quality, score = app.listing_quality(directory_result)
    assert quality == "Directory / listing page"
    assert score == 0

    specific_result = {"title": "AI Internship at Microsoft", "snippet": "Applications are open. Apply now.", "link": "https://careers.microsoft.com/students/ai-internship"}
    quality, score = app.listing_quality(specific_result)
    assert quality.startswith("Possible direct") or quality == "Specific opportunity page"
    assert score >= 3


def test_hackathon_fallback_query_covers_domain_variants_and_undergraduate_terms():
    request = app.SearchRequest(
        topic="AI agents and cybersecurity",
        opportunity_type="Hackathons",
        location="India",
        student_level="Undergraduate",
    )

    query = app.build_fallback_search_query(request).lower()

    assert '"ai agent hackathon"' in query
    assert '"agentic ai hackathon"' in query
    assert '"cybersecurity competition"' in query
    assert '"cyber security challenge"' in query
    assert '"student innovation challenge"' in query
    assert '"undergraduate hackathon"' in query
    assert '"india"' in query
    assert '"undergraduate"' in query
    assert "eligibility" in query


def test_hackathon_direct_event_is_primary_but_directories_and_articles_are_secondary():
    request = make_focused_hackathon_request()
    candidates = [
        {
            "title": "AI Agents and Cybersecurity Student Hackathon Registration",
            "snippet": "Undergraduate student event in India. Register for the competition.",
            "link": "https://events.example.org/register/ai-agents-cybersecurity",
        },
        {
            "title": "AI Agents and Cybersecurity Hackathons in India",
            "snippet": "Browse all hackathons, competitions, and student events.",
            "link": "https://unstop.com/hackathons",
        },
        {
            "title": "News: AI Agents and Cybersecurity Hackathon Announced",
            "snippet": "A student innovation challenge in India.",
            "link": "https://university.example.edu/news/ai-cyber-hackathon",
        },
    ]

    for candidate in candidates:
        score, reason = app.relevance_and_filter(candidate, request)
        assert reason is None
        assert score > 0

    assert candidates[0]["topic_relevance_tier"] == "primary"
    assert candidates[0]["listing_quality"] == "Specific opportunity page"
    assert candidates[1]["topic_relevance_tier"] == "secondary"
    assert candidates[1]["listing_quality"] == "Directory / listing page"
    assert candidates[2]["topic_relevance_tier"] == "secondary"
    assert candidates[2]["listing_quality"] == "News / announcement page"


def make_job_request(**overrides):
    values = {
        "opportunity_type": "Jobs",
        "topic": "cybersecurity",
        "location": "India",
        "student_level": "Undergraduate",
    }
    values.update(overrides)
    return type("Req", (), values)()


def make_scholarship_request(**overrides):
    values = {
        "opportunity_type": "Scholarships",
        "topic": "STEM",
        "location": "India",
        "student_level": "Undergraduate",
    }
    values.update(overrides)
    return type("Req", (), values)()


def test_scholarship_queries_prioritize_official_portals_and_universities():
    query = app.build_search_query(make_scholarship_request())
    fallback = app.build_fallback_search_query(make_scholarship_request())

    for domain in ("scholarships.gov.in", "nsp.gov.in", "gov.in", "nic.in", "ac.in", "edu.in"):
        assert domain in fallback
    for query_text in (query, fallback):
        assert "National Scholarship Portal" in query_text
        assert "ministry scholarship" in query_text
        assert "university financial aid" in query_text
    assert "notification" in query
    assert "announcement" in query
    assert "site:gov" in fallback
    assert "-filetype:pdf" in query
    assert "-filetype:pdf" in fallback


def test_official_scholarship_pages_rank_above_third_party_leads():
    official = {
        "title": "STEM Scholarship Application Portal",
        "snippet": "Undergraduate scholarship applications for students in India.",
        "source": "National Scholarship Portal",
        "link": "https://scholarships.gov.in/student/apply",
    }
    third_party = {
        "title": "STEM Scholarship opportunity",
        "snippet": "Undergraduate scholarship details for students in India.",
        "source": "Education Portal",
        "link": "https://scholarship-aggregator.example/stem-scholarship",
    }

    official_score, official_reason = app.relevance_and_filter(
        official, make_scholarship_request()
    )
    third_party_score, third_party_reason = app.relevance_and_filter(
        third_party, make_scholarship_request()
    )

    assert official_reason is None
    assert third_party_reason is None
    assert official["scholarship_result_tier"] == "primary"
    assert official["listing_quality"] == "Official scholarship application page"
    assert third_party["scholarship_result_tier"] == "secondary"
    assert third_party_score < official_score


def test_third_party_scholarship_articles_and_directories_are_secondary():
    article = {
        "title": "STEM Scholarship News: New Scheme Announced",
        "snippet": "Undergraduate scholarships in India.",
        "source": "Education News",
        "link": "https://education-news.example/news/stem-scholarship",
    }
    directory = {
        "title": "STEM scholarship listings in India",
        "snippet": "Browse all undergraduate scholarship opportunities.",
        "source": "Scholarship Aggregator",
        "link": "https://scholarship-aggregator.example/scholarships",
    }

    for result in (article, directory):
        score, reason = app.relevance_and_filter(result, make_scholarship_request())
        assert score > 0
        assert reason is None
        assert result["scholarship_result_tier"] == "secondary"
    assert article["listing_quality"] == "Third-party scholarship article — secondary source"
    assert directory["listing_quality"] == "Scholarship directory — secondary source"


def test_official_scholarship_announcement_does_not_imply_open_or_deadline():
    result = {
        "title": "STEM Scholarship Notification",
        "snippet": "Official undergraduate scholarship notification for India.",
        "source": "Ministry of Education",
        "link": "https://education.gov.in/notices/stem-scholarship-notification",
    }
    score, reason = app.relevance_and_filter(result, make_scholarship_request())
    assert score > 0
    assert reason is None
    assert result["scholarship_result_tier"] == "primary"
    assert result["scholarship_application_page"] is False
    assert result["listing_quality"] == (
        "Official scholarship announcement — application status unverified"
    )

    client = FakeAsyncClient(FakeResponse(
        text=(
            "<html><body>Applications are open. Scholarship announcement released "
            "1 June 2026. The award event will take place in 2027.</body></html>"
        ),
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    verified = asyncio.run(run())
    assert verified["application_status"] == "unknown"
    assert verified["deadline"] is None
    assert verified["deadline_verified"] is False
    assert verified["opportunity_status"] == "unverified"


def test_scholarship_application_page_keeps_status_and_deadline_unknown_without_evidence():
    result = {
        "title": "STEM Scholarship Application Portal",
        "snippet": "Undergraduate scholarship application for students in India.",
        "source": "National Scholarship Portal",
        "link": "https://scholarships.gov.in/student/apply",
    }
    app.relevance_and_filter(result, make_scholarship_request())
    client = FakeAsyncClient(FakeResponse(
        text=(
            "<html><body>Apply now for the scholarship. The award ceremony is "
            "scheduled for 15 September 2027.</body></html>"
        ),
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    verified = asyncio.run(run())
    assert verified["scholarship_application_page"] is True
    assert verified["application_status"] == "unknown"
    assert verified["deadline"] is None
    assert verified["deadline_verified"] is False
    assert verified["opportunity_status"] == "unverified"


def test_scholarship_search_separates_official_results_from_secondary_leads(monkeypatch):
    found = [
        {
            "title": "STEM Scholarship Application Portal",
            "snippet": "Undergraduate scholarship application for India.",
            "source": "National Scholarship Portal",
            "link": "https://scholarships.gov.in/student/apply",
            "listing_quality": "Official scholarship application page",
            "scholarship_result_tier": "primary",
            "scholarship_application_page": True,
            "application_status": "unknown",
            "opportunity_status": "unverified",
            "deadline_verified": False,
            "position": 1,
        },
        {
            "title": "STEM Scholarship News and Listings",
            "snippet": "Third-party undergraduate scholarship leads for India.",
            "source": "Education News",
            "link": "https://education-news.example/news/stem-scholarships",
            "listing_quality": "Third-party scholarship article — secondary source",
            "scholarship_result_tier": "secondary",
            "scholarship_application_page": False,
            "deadline": "2027-06-30",
            "opportunity_status": "deadline_upcoming",
            "position": 2,
        },
    ]

    async def fake_serpapi_search(*args, **kwargs):
        return [item.copy() for item in found]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    payload = asyncio.run(app.search(make_scholarship_request()))

    assert payload["count"] == 1
    assert len(payload["results"]) == 1
    assert len(payload["secondary_results"]) == 1
    primary = payload["results"][0]
    secondary = payload["secondary_results"][0]
    row = payload["report_rows"][0]
    assert row["source"] == primary["source"]
    assert row["title"] == primary["title"]
    assert row["listing_type"] == primary["listing_quality"]
    assert row["application_status"] == "Unknown"
    assert row["deadline_status"] == "Unverified"
    assert secondary["application_status"] == "unknown"
    assert secondary["deadline"] is None
    assert secondary["deadline_verified"] is False
    assert secondary["opportunity_status"] == "unverified"


def test_scholarship_official_fallback_adds_application_page_without_losing_leads(
    monkeypatch, caplog
):
    calls = []
    third_party = {
        "title": "STEM Scholarship Directory",
        "snippet": "Browse scholarship listings for India.",
        "source": "Education Portal",
        "link": "https://education-portal.example/scholarships",
        "listing_quality": "Scholarship directory — secondary source",
        "scholarship_result_tier": "secondary",
        "scholarship_application_page": False,
        "relevance_score": 6,
        "position": 1,
    }
    official_application = {
        "title": "STEM Scholarship Application Portal",
        "snippet": "Undergraduate application for eligible students in India.",
        "source": "National Scholarship Portal",
        "link": "https://scholarships.gov.in/student/apply",
        "listing_quality": "Official scholarship application page",
        "scholarship_result_tier": "primary",
        "scholarship_application_page": True,
        "application_status": "unknown",
        "deadline": None,
        "deadline_verified": False,
        "opportunity_status": "unverified",
        "relevance_score": 20,
        "position": 1,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        if len(calls) == 1:
            return [third_party.copy()]
        return [official_application.copy()]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(make_scholarship_request()))

    assert len(calls) == 2
    assert "site:scholarships.gov.in" in calls[1]
    assert "site:nsp.gov.in" in calls[1]
    assert "university financial aid" in calls[1]
    assert len(payload["results"]) == 1
    assert payload["results"][0]["link"] == official_application["link"]
    assert payload["results"][0]["application_status"] == "unknown"
    assert payload["results"][0]["deadline_verified"] is False
    assert [item["link"] for item in payload["secondary_results"]] == [third_party["link"]]
    assert payload["secondary_results"][0]["application_status"] == "unknown"
    assert payload["secondary_results"][0]["deadline"] is None
    assert "Official source fallback outcome=completed" in caplog.text


@pytest.mark.parametrize("fallback_outcome", ["empty", "failed"])
def test_scholarship_empty_or_failed_fallback_is_diagnostic_and_safe(
    monkeypatch, caplog, fallback_outcome
):
    calls = []
    third_party = {
        "title": "STEM Scholarship Directory",
        "snippet": "Browse scholarship listings for India.",
        "source": "Education Portal",
        "link": "https://education-portal.example/scholarships",
        "listing_quality": "Scholarship directory — secondary source",
        "scholarship_result_tier": "secondary",
        "scholarship_application_page": False,
        "relevance_score": 6,
        "position": 1,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        if len(calls) == 1:
            return [third_party.copy()]
        if fallback_outcome == "failed":
            raise HTTPException(status_code=502, detail="Search unavailable.")
        return []

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(make_scholarship_request()))

    assert len(calls) == 2
    assert payload["results"] == []
    assert [item["link"] for item in payload["secondary_results"]] == [third_party["link"]]
    assert payload["secondary_results"][0]["application_status"] == "unknown"
    assert payload["secondary_results"][0]["deadline"] is None
    assert "Official source fallback outcome=started" in caplog.text
    if fallback_outcome == "failed":
        assert "Official source fallback outcome=failed" in caplog.text
        assert "initial_results_retained=true" in caplog.text
        assert "follow-up search could not be completed" in payload["search_message"]
    else:
        assert "Official source fallback outcome=empty" in caplog.text
        assert "initial_results_retained=true" in caplog.text


def test_scholarship_empty_initial_and_fallback_search_returns_no_fabricated_results(
    monkeypatch, caplog
):
    calls = []

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return []

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(make_scholarship_request()))

    assert len(calls) == 2
    assert payload["count"] == 0
    assert payload["results"] == []
    assert payload["report_rows"] == []
    assert payload.get("secondary_results", []) == []
    assert "No official government" in payload["search_message"]
    assert "Official source fallback outcome=empty" in caplog.text


def test_job_query_uses_topic_location_and_level_for_entry_roles():
    query = app.build_search_query(make_job_request())
    fallback = app.build_fallback_search_query(make_job_request())

    for expected in ("cybersecurity", "cyber security", "India", "graduate", "fresher", "entry-level"):
        assert expected.lower() in query.lower()
    assert '"career advice"' in query
    assert '"job listings"' in query
    assert "cybersecurity" in fallback.lower()
    assert "India" in fallback
    assert '("student" OR "graduate" OR "fresher" OR "entry-level")' in query


def test_job_query_variations_cover_related_ai_and_security_roles():
    request = make_job_request(topic="AI agents and cybersecurity", student_level="Graduate")
    queries = app.build_job_search_queries(request)

    assert len(queries) == 2
    combined = " ".join(queries).lower()
    for role in (
        "ai security engineer",
        "cybersecurity graduate trainee",
        "junior security analyst",
        "ai engineer fresher",
        "entry-level security roles",
    ):
        assert role in combined
    assert all('"india"' in query.lower() for query in queries)
    assert all('"graduate"' in query.lower() for query in queries)


@pytest.mark.parametrize(
    ("opportunity_type", "category_term", "official_term"),
    [
        ("Hackathons", "hackathon", "organizer"),
        ("Internships", "internship", "employer"),
        ("Scholarships", "scholarship", "national scholarship portal"),
    ],
)
def test_category_initial_and_fallback_queries_are_complementary(
    opportunity_type, category_term, official_term
):
    request = app.SearchRequest(
        topic="AI agents and cybersecurity",
        opportunity_type=opportunity_type,
        location="India",
        student_level="Undergraduate",
    )

    initial = app.build_search_query(request).lower()
    fallback = app.build_fallback_search_query(request).lower()

    assert initial != fallback
    assert category_term in initial and category_term in fallback
    assert "india" in initial and "india" in fallback
    assert "undergraduate" in initial and "undergraduate" in fallback
    assert official_term in (initial + fallback)
    if opportunity_type == "Scholarships":
        assert '"application portal" or apply or application' in fallback
    elif opportunity_type == "Hackathons":
        assert "registration" in fallback and "register" in fallback
    else:
        assert "(application or apply or registration" in fallback


def test_job_query_variations_add_internship_for_undergraduate_searches():
    queries = app.build_job_search_queries(
        make_job_request(topic="AI agents and cybersecurity", student_level="Undergraduate")
    )

    assert len(queries) == 2
    assert any("internship" in query.lower() or "intern" in query.lower() for query in queries)


def test_job_relevance_prioritizes_specific_employer_vacancy():
    request = make_job_request(location="Bengaluru")
    result = {
        "title": "Graduate Cybersecurity Analyst at Acme Security — Bengaluru, India",
        "snippet": "Entry-level role for cybersecurity graduates. Bengaluru.",
        "source": "Acme Security",
        "link": "https://careers.acme.example/jobs/graduate-cybersecurity-analyst",
    }

    score, reason = app.relevance_and_filter(result, request)

    assert reason is None
    assert score > 10
    assert result["job_result_tier"] == "primary"
    assert result["listing_quality"] == "Specific job listing — direct application page"
    assert "not been independently verified" in result["relevance_note"]


def test_job_classifier_keeps_individual_listings_on_unfamiliar_posting_urls():
    result = {
        "title": "Cybersecurity Graduate Trainee at Acme Security - India",
        "snippet": "Specific graduate trainee vacancy in India.",
        "source": "Acme Security",
        "link": "https://hiring.example.org/posting/req-9482",
    }

    score, reason = app.relevance_and_filter(
        result,
        make_job_request(topic="AI agents and cybersecurity"),
    )

    assert reason is None
    assert score > 10
    assert result["job_result_tier"] == "primary"
    assert result["listing_quality"] == "Specific job listing — third-party portal"


def test_job_classifier_recognizes_unfamiliar_individual_route_on_known_portal():
    result = {
        "title": "Cybersecurity Analyst at Acme Security - India",
        "snippet": "Specific graduate vacancy in India.",
        "source": "Indeed",
        "link": "https://www.indeed.com/job-posting/req-20481",
    }

    score, reason = app.relevance_and_filter(result, make_job_request())

    assert reason is None
    assert score > 10
    assert result["job_result_tier"] == "primary"
    assert result["listing_quality"] == "Specific job listing — third-party portal"


@pytest.mark.parametrize(
    ("source", "link"),
    [
        ("Indeed", "https://www.indeed.com/jobsdetail/req-20481"),
        ("TalentHub", "https://talenthub.example/opportunity/req-20481"),
    ],
)
def test_job_classifier_accepts_specific_vacancy_on_unrecognized_url_path(source, link):
    result = {
        "title": "Cybersecurity Analyst at Acme Security - India",
        "snippet": "Graduate cybersecurity analyst vacancy in India.",
        "source": source,
        "link": link,
    }

    score, reason = app.relevance_and_filter(result, make_job_request())

    assert reason is None
    assert score > 10
    assert result["job_result_tier"] == "primary"
    assert result["listing_quality"] == "Specific job listing — third-party portal"


def test_job_classifier_accepts_ai_agent_vacancy_for_specialist_topic():
    result = {
        "title": "AI Agent Engineer at Acme Labs - India",
        "snippet": "Build autonomous AI agents for enterprise workflows.",
        "source": "Acme Labs",
        "link": "https://careers.acme.example/jobs/ai-agent-engineer",
    }

    score, reason = app.relevance_and_filter(
        result,
        make_job_request(topic="AI agents and cybersecurity"),
    )

    assert reason is None
    assert score > 10
    assert result["job_result_tier"] == "primary"
    assert result["topic_relevance_tier"] == "primary"


def test_job_classifier_demotes_healthcare_ai_when_specialist_terms_are_absent():
    result = {
        "title": "Multimodal AI Engineer at HealthCare Systems - India",
        "snippet": "Build clinical AI tools for hospitals and medical imaging.",
        "source": "HealthCare Systems",
        "link": "https://careers.healthcare.example/jobs/multimodal-ai-engineer",
    }

    score, reason = app.relevance_and_filter(
        result,
        make_job_request(topic="AI agents and cybersecurity"),
    )

    assert reason is None
    assert 0 < score <= 8
    assert result["job_result_tier"] == "secondary"
    assert result["topic_relevance_tier"] == "secondary"
    assert result["listing_quality"] == "Adjacent-topic job listing — secondary source"
    assert "not the requested specialist domain" in result["relevance_note"]
    assert "application_status" not in result
    assert "source_check_status" not in result


def test_job_search_places_adjacent_vacancies_in_secondary_results(monkeypatch):
    request = make_job_request(topic="AI agents and cybersecurity")
    adjacent = {
        "title": "Multimodal AI Engineer at HealthCare Systems - India",
        "snippet": "Build clinical AI tools for hospitals and medical imaging.",
        "source": "HealthCare Systems",
        "link": "https://careers.healthcare.example/jobs/multimodal-ai-engineer",
        "position": 1,
    }
    app.relevance_and_filter(adjacent, request)

    async def fake_serpapi_search(*args, **kwargs):
        return [adjacent.copy()]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    payload = asyncio.run(app.search(request))

    assert payload["results"] == []
    assert payload["report_rows"] == []
    assert payload["count"] == 0
    assert len(payload["secondary_results"]) == 1
    lead = payload["secondary_results"][0]
    assert lead["listing_quality"] == "Adjacent-topic job listing — secondary source"
    assert lead["topic_relevance_tier"] == "secondary"
    assert lead["application_status"] == "unknown"
    assert lead["source_check_status"] == "not_checked"
    assert "No strong individual vacancies matching the requested specialist topic" in payload["search_message"]


def test_job_directories_are_secondary_and_articles_are_excluded():
    request = make_job_request()
    directory = {
        "title": "Cybersecurity jobs in India",
        "snippet": "Browse all cybersecurity job listings and openings.",
        "source": "Indeed",
        "link": "https://www.indeed.com/jobs?q=cybersecurity&l=India",
    }
    article = {
        "title": "Cybersecurity Career Advice for Graduates",
        "snippet": "Career guide, interview tips and resume tips for job seekers.",
        "source": "Career Blog",
        "link": "https://careeradvice.example/articles/cybersecurity",
    }

    directory_score, directory_reason = app.relevance_and_filter(directory, request)
    article_score, article_reason = app.relevance_and_filter(article, request)

    assert directory_reason is None
    assert directory_score < 5
    assert directory["job_result_tier"] == "secondary"
    assert directory["listing_quality"] == "Job directory — secondary source"
    assert article_score == 0
    assert article_reason


def test_specific_third_party_job_vacancy_with_employer_is_primary():
    result = {
        "title": "Cybersecurity Graduate Trainee at Acme Security - India",
        "snippet": "Graduate trainee role in India. Apply on the individual vacancy page.",
        "source": "Indeed",
        "link": "https://www.indeed.com/viewjob?jk=vacancy-123",
    }

    score, reason = app.relevance_and_filter(result, make_job_request())

    assert reason is None
    assert score > 10
    assert result["job_result_tier"] == "primary"
    assert result["listing_quality"] == "Specific job listing — third-party portal"
    assert "not been independently verified" in result["relevance_note"]


def test_third_party_result_without_employer_or_specific_role_stays_secondary():
    missing_employer = {
        "title": "Junior Security Analyst - India",
        "snippet": "Cybersecurity role for graduates in India.",
        "source": "Naukri",
        "link": "https://www.naukri.com/job-listings/security-analyst-123",
    }
    missing_role = {
        "title": "Acme Security jobs in India",
        "snippet": "Graduate cybersecurity openings at Acme Security.",
        "source": "LinkedIn",
        "link": "https://www.linkedin.com/jobs/search/?keywords=cybersecurity",
    }

    for result in (missing_employer, missing_role):
        score, reason = app.relevance_and_filter(result, make_job_request())
        assert score < 10
        assert result["job_result_tier"] != "primary"
        assert result["job_result_tier"] in {"secondary", "excluded"}
        assert reason is None or reason


def test_serpapi_diagnostics_distinguish_primary_secondary_and_excluded(monkeypatch, caplog):
    raw_results = [
        {
            "title": "Cybersecurity Analyst - Acme Security - India",
            "snippet": "Graduate role for cybersecurity candidates in India.",
            "source": "Indeed",
            "link": "https://www.indeed.com/viewjob?jk=role-1",
            "position": 1,
        },
        {
            "title": "Cybersecurity jobs in India",
            "snippet": "Browse all job listings and search openings.",
            "source": "Indeed",
            "link": "https://www.indeed.com/jobs?q=cybersecurity&l=India",
            "position": 2,
        },
        {
            "title": "Cybersecurity Analyst - India",
            "snippet": "Graduate cybersecurity role.",
            "source": "Naukri",
            "link": "https://www.naukri.com/job-listings/cybersecurity-analyst-1",
            "position": 3,
        },
        {
            "title": "Cybersecurity Career Advice",
            "snippet": "Career advice and interview tips.",
            "source": "Career Blog",
            "link": "https://careeradvice.example/cybersecurity",
            "position": 4,
        },
    ]
    monkeypatch.setattr(app, "SERPAPI_KEY", "test-key-not-for-logging")
    monkeypatch.setattr(
        app.httpx,
        "AsyncClient",
        lambda **kwargs: FakeSerpApiClient(FakeSerpApiResponse(raw_results)),
    )

    async def run():
        return await app.serpapi_search(
            "private-user-topic cybersecurity India",
            make_job_request(topic="private-user-topic cybersecurity"),
        )

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        results = asyncio.run(run())

    assert any(item["job_result_tier"] == "primary" for item in results)
    assert any(item["job_result_tier"] == "secondary" for item in results)
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "raw=4" in log_output
    assert "primary" in log_output
    assert "secondary" in log_output
    assert "exclusion_reasons" in log_output
    assert "private-user-topic" not in log_output
    assert "test-key-not-for-logging" not in log_output


def test_genuine_job_directory_with_employer_keywords_stays_secondary():
    results = [
        {
            "title": "Cybersecurity graduate jobs at Acme Security in India",
            "snippet": "Browse all jobs and search openings from employers.",
            "source": "LinkedIn",
            "link": "https://www.linkedin.com/jobs/search/?keywords=cybersecurity",
        },
        {
            "title": "Cybersecurity Analyst at Acme Security - India",
            "snippet": "Browse all jobs and search openings from employers.",
            "source": "LinkedIn",
            "link": "https://www.linkedin.com/discovery/role/req-92",
        },
    ]

    for result in results:
        score, _ = app.relevance_and_filter(result, make_job_request())
        assert score < 10
        assert result["job_result_tier"] == "secondary"
        assert result["listing_quality"] == "Job directory — secondary source"


def test_apply_now_alone_does_not_mark_job_open():
    result = {
        "title": "Cybersecurity Analyst at Acme Security",
        "snippet": "Apply now for this role.",
        "source": "Acme Security",
        "link": "https://careers.acme.example/jobs/cybersecurity-analyst",
        "job_result_tier": "primary",
    }
    client = FakeAsyncClient(FakeResponse(
        text="<html><body>Cybersecurity Analyst. Apply now.</body></html>",
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())

    assert checked["application_status"] == "unknown"


def test_specific_third_party_vacancy_status_stays_unknown_without_explicit_evidence():
    result = {
        "title": "Cybersecurity Graduate Trainee at Acme Security - India",
        "source": "Indeed",
        "link": "https://www.indeed.com/viewjob?jk=vacancy-123",
        "snippet": "Apply now.",
    }
    app.relevance_and_filter(result, make_job_request())
    client = FakeAsyncClient(FakeResponse(
        text="<html><body>Cybersecurity Graduate Trainee at Acme Security. Apply now.</body></html>",
        url=result["link"],
    ))

    async def run():
        return await app.verify_one_source(client, result)

    checked = asyncio.run(run())

    assert checked["job_result_tier"] == "primary"
    assert checked["application_status"] == "unknown"
    assert checked["source_verified"] is False
    assert checked["employer_source_verified"] is False


def test_job_search_keeps_directories_separate_when_no_strong_vacancy(monkeypatch, caplog):
    calls = []
    directory = {
        "title": "Cybersecurity jobs in India",
        "snippet": "Browse job listings for cybersecurity graduates.",
        "source": "Indeed",
        "link": "https://www.indeed.com/jobs?q=cybersecurity&l=India",
        "listing_quality": "Job directory — secondary source",
        "job_result_tier": "secondary",
        "relevance_score": 1,
        "position": 1,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return [directory.copy()]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "No individual vacancy data.", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(
            app.SearchRequest(
                topic="cybersecurity",
                opportunity_type="Jobs",
                location="India",
                student_level="Undergraduate",
            )
        ))

    assert len(calls) == 3
    assert payload["results"] == []
    assert payload["report_rows"] == []
    assert len(payload["secondary_results"]) == 1
    assert "No strong individual employer-linked job vacancies" in payload["search_message"]
    assert payload["secondary_results"][0]["application_status"] == "unknown"
    assert payload["secondary_results"][0]["employer_source_verified"] is False
    assert "cybersecurity graduate trainee" in calls[1].lower()
    assert "entry-level security roles" in calls[2].lower()
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "variation=initial" in log_output
    assert "variation=job_role_variant_1" in log_output
    assert "variation=job_role_variant_2" in log_output
    assert "primary_jobs=0" in log_output
    assert "secondary_jobs=1" in log_output
    assert "Official source fallback outcome=skipped category=Jobs" in log_output
    assert "reason=job_role_variations_use_search_call_budget" in log_output
    assert "cybersecurity" not in log_output.lower()


@pytest.mark.parametrize("followup_outcome", ["empty", "failed"])
def test_job_search_retains_initial_directory_when_role_variations_fail_or_are_empty(
    monkeypatch, caplog, followup_outcome
):
    calls = []
    directory = {
        "title": "Cybersecurity jobs in India",
        "snippet": "Browse all job listings for cybersecurity graduates.",
        "source": "Indeed",
        "link": "https://www.indeed.com/jobs?q=cybersecurity&l=India",
        "listing_quality": "Job directory — secondary source",
        "job_result_tier": "secondary",
        "relevance_score": 1,
        "position": 1,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        if len(calls) == 1:
            return [directory.copy()]
        if followup_outcome == "failed":
            raise HTTPException(status_code=502, detail="Search unavailable.")
        return []

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "No individual vacancy data.", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(
            app.SearchRequest(
                topic="cybersecurity",
                opportunity_type="Jobs",
                location="India",
                student_level="Graduate",
            )
        ))

    assert len(calls) == 3
    assert payload["results"] == []
    assert [item["link"] for item in payload["secondary_results"]] == [directory["link"]]
    assert payload["secondary_results"][0]["application_status"] == "unknown"
    assert "primary_jobs=0" in caplog.text
    if followup_outcome == "failed":
        assert "Job role variation outcome=failed" in caplog.text
        assert "initial_results_retained=true" in caplog.text
    else:
        assert "outcome=empty" in caplog.text


def test_job_search_stops_after_enough_distinct_strong_vacancies(monkeypatch):
    calls = []
    primary_results = [
        {
            "title": f"Cybersecurity Analyst at Example Employer {index}",
            "snippet": "Graduate cybersecurity vacancy in India.",
            "source": f"Example Employer {index}",
            "link": f"https://careers.example{index}.com/jobs/cybersecurity-analyst",
            "listing_quality": "Specific job listing — direct application page",
            "job_result_tier": "primary",
            "relevance_score": 20 - index,
            "position": index,
        }
        for index in range(1, 4)
    ]

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return primary_results if len(calls) == 2 else []

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    payload = asyncio.run(app.search(
        app.SearchRequest(
            topic="cybersecurity",
            opportunity_type="Jobs",
            location="India",
            student_level="Graduate",
        )
    ))

    assert len(calls) == 2
    assert len(payload["results"]) == 3
    assert all(item["job_result_tier"] == "primary" for item in payload["results"])


def test_social_sources_are_labeled_secondary_and_deprioritized():
    request = type("Req", (), {
        "opportunity_type": "Hackathons",
        "topic": "AI",
        "location": "India",
        "student_level": "Undergraduate",
    })()
    social = {
        "title": "AI Hackathon registration",
        "snippet": "AI student hackathon in India, register now.",
        "link": "https://www.linkedin.com/posts/organizer-ai-hackathon",
    }
    official = {
        "title": "AI Hackathon registration",
        "snippet": "AI student hackathon in India, register now.",
        "link": "https://events.example.org/register/ai-hackathon",
    }

    social_score, _ = app.relevance_and_filter(social, request)
    official_score, _ = app.relevance_and_filter(official, request)

    assert social["listing_quality"] == "Social media — secondary source"
    assert "secondary lead" in social["relevance_note"]
    assert social_score < official_score


def make_focused_hackathon_request():
    return type("Req", (), {
        "opportunity_type": "Hackathons",
        "topic": "AI agents and cybersecurity",
        "location": "India",
        "student_level": "Undergraduate",
    })()


def test_focused_topic_matches_cybersecurity_and_ai_agents():
    request = make_focused_hackathon_request()
    results = [
        {
            "title": "Cybersecurity Student Hackathon 2026",
            "snippet": "Build security tools for students in India.",
            "link": "https://events.example.org/cybersecurity-hackathon",
        },
        {
            "title": "AI Agents Innovation Hackathon",
            "snippet": "Create agentic AI systems at a student event in India.",
            "link": "https://events.example.org/ai-agents-hackathon",
        },
    ]

    for result in results:
        score, reason = app.relevance_and_filter(result, request)
        assert reason is None
        assert score > 3
        assert result["topic_relevance_tier"] == "primary"
        assert result["listing_quality"] != "Adjacent topic — secondary lead"


def test_healthcare_multimodal_ai_does_not_match_specialist_search():
    result = {
        "title": "Healthcare-Focused Multimodal AI Hackathon 2026",
        "snippet": "Build multimodal AI solutions for hospitals and clinical care in India.",
        "link": "https://events.example.org/healthcare-multimodal-ai",
    }

    score, reason = app.relevance_and_filter(result, make_focused_hackathon_request())

    assert reason is None
    assert 0 < score <= 3
    assert result["topic_relevance_tier"] == "secondary"
    assert result["listing_quality"] == "Adjacent topic — secondary lead"
    assert "not a requested specialist domain" in result["relevance_note"]
    assert "application_status" not in result
    assert "source_verified" not in result
    assert "source_check_status" not in result


def test_adjacent_topic_results_are_separate_from_primary_report_rows(monkeypatch):
    request = make_focused_hackathon_request()
    primary = {
        "title": "Cybersecurity Student Hackathon 2026",
        "snippet": "Security challenge for students in India.",
        "source": "University Events",
        "link": "https://events.example.org/cybersecurity-hackathon",
        "position": 1,
    }
    adjacent = {
        "title": "Healthcare Multimodal AI Hackathon 2026",
        "snippet": "Healthcare AI and clinical innovation challenge in India.",
        "source": "Health Innovation Hub",
        "link": "https://events.example.org/healthcare-multimodal-ai",
        "position": 2,
    }
    for result in (primary, adjacent):
        app.relevance_and_filter(result, request)

    async def fake_serpapi_search(*args, **kwargs):
        return [primary.copy(), adjacent.copy()]

    verified = []

    async def fake_verify_sources(results):
        verified.extend(results)
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    payload = asyncio.run(app.search(request))

    assert len(payload["results"]) == 1
    assert payload["results"][0]["link"] == primary["link"]
    assert len(payload["report_rows"]) == 1
    assert payload["report_rows"][0]["title"] == primary["title"]
    assert len(payload["secondary_results"]) == 1
    assert payload["secondary_results"][0]["link"] == adjacent["link"]
    assert payload["secondary_results"][0]["topic_relevance_tier"] == "secondary"
    assert payload["secondary_results"][0]["application_status"] == "unknown"
    assert payload["secondary_results"][0]["source_check_status"] == "not_checked"
    assert [item["link"] for item in verified] == [primary["link"]]


def test_search_retries_once_for_weak_social_results_then_uses_official_page(monkeypatch, caplog):
    calls = []
    social_result = {
        "title": "AI hackathon registration",
        "snippet": "Register for the student AI hackathon.",
        "source": "linkedin.com",
        "link": "https://www.linkedin.com/posts/example",
        "listing_quality": "Social media — secondary source",
        "relevance_score": 1,
        "position": 1,
    }
    official_result = {
        "title": "AI Hackathon Registration",
        "snippet": "Official university organizer registration page.",
        "source": "Example University",
        "link": "https://events.example.edu/register/ai-hackathon",
        "listing_quality": "Specific opportunity page",
        "relevance_score": 12,
        "position": 2,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return [social_result.copy()] if len(calls) == 1 else [official_result.copy()]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(
            app.SearchRequest(topic="AI", opportunity_type="Hackathons", location="India", student_level="Undergraduate")
        ))

    assert len(calls) == 2
    assert "organizer" in calls[1] and "university" in calls[1]
    assert "-site:linkedin.com" in calls[1]
    assert payload["results"][0]["link"] == official_result["link"]
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "Official source fallback outcome=started" in log_output
    assert "Official source fallback outcome=completed" in log_output
    assert "result_count=1" in log_output


def test_search_skips_fallback_when_a_specific_primary_result_exists(monkeypatch, caplog):
    calls = []
    primary_results = [
        {
            "title": f"AI Hackathon {index}",
            "snippet": "Official organizer student registration.",
            "link": f"https://events.example.org/register/{index}",
            "listing_quality": "Specific opportunity page",
            "relevance_score": 10 - index,
            "position": index,
        }
        for index in (1,)
    ]

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return [item.copy() for item in primary_results]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        asyncio.run(app.search(
            app.SearchRequest(topic="AI", opportunity_type="Hackathons", location="India", student_level="Undergraduate")
        ))

    assert len(calls) == 1
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "Official source fallback outcome=skipped" in log_output
    assert "reason=primary_result_already_found" in log_output


def test_unreachable_hackathon_primary_moves_to_secondary_and_uses_one_fallback(monkeypatch, caplog):
    calls = []
    unreachable_result = {
        "title": "AI Agents and Cybersecurity Hackathon Registration",
        "snippet": "Undergraduate competition in India.",
        "source": "Example Organizer",
        "link": "https://events.example.org/register/old-event",
        "listing_quality": "Specific opportunity page",
        "topic_relevance_tier": "primary",
        "relevance_score": 14,
        "position": 1,
    }
    fallback_result = {
        "title": "Cybersecurity Student Innovation Challenge Registration",
        "snippet": "Undergraduate cybersecurity competition in India. Register with the organizer.",
        "source": "University Challenge",
        "link": "https://university.example.edu/events/register/cyber-challenge",
        "listing_quality": "Specific opportunity page",
        "topic_relevance_tier": "primary",
        "relevance_score": 12,
        "position": 1,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return [unreachable_result.copy()] if len(calls) == 1 else [fallback_result.copy()]

    async def fake_verify_sources(results):
        for item in results:
            if item["link"] == unreachable_result["link"]:
                app.mark_source_unreachable(item, "Original source returned HTTP 404.", 404)
            else:
                item.update({
                    "source_check_status": "checked",
                    "source_content_readable": True,
                    "source_verified": False,
                    "application_status": "unknown",
                    "deadline": None,
                    "deadline_verified": False,
                    "opportunity_status": "unverified",
                })
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(app.SearchRequest(
            topic="AI agents and cybersecurity",
            opportunity_type="Hackathons",
            location="India",
            student_level="Undergraduate",
        )))

    assert len(calls) == 2
    assert "student innovation challenge" in calls[1].lower()
    assert len(payload["results"]) == 1
    assert payload["results"][0]["link"] == fallback_result["link"]
    assert payload["results"][0]["application_status"] == "unknown"
    assert payload["results"][0]["deadline"] is None
    assert len(payload["secondary_results"]) == 1
    old_lead = payload["secondary_results"][0]
    assert old_lead["link"] == unreachable_result["link"]
    assert old_lead["source_check_status"] == "unreachable"
    assert old_lead["application_status"] == "unknown"
    assert old_lead["deadline"] is None
    assert "HTTP 404" in old_lead["source_check_note"]
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "reason=primary_sources_unreachable" in logs
    assert "moved_to_secondary=1 reason=source_unreachable" in logs


def test_search_keeps_initial_results_when_targeted_fallback_fails(monkeypatch, caplog):
    calls = []
    initial_result = {
        "title": "AI Hackathon announcement",
        "snippet": "Student AI hackathon announced by organizer.",
        "link": "https://www.linkedin.com/posts/organizer",
        "listing_quality": "Social media — secondary source",
        "relevance_score": 1,
        "position": 1,
    }

    async def fake_serpapi_search(query, request):
        calls.append(query)
        if len(calls) == 2:
            raise HTTPException(status_code=502, detail="SerpApi temporarily unavailable.")
        return [initial_result.copy()]

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(
            app.SearchRequest(topic="AI", opportunity_type="Hackathons", location="India", student_level="Undergraduate")
        ))

    assert len(calls) == 2
    assert len(payload["results"]) == 1
    assert payload["results"][0]["link"] == initial_result["link"]
    assert "follow-up search could not be completed" in payload["search_message"]
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "Official source fallback outcome=failed" in log_output
    assert "reason=http_exception status=502" in log_output
    assert "initial_results_retained=true" in log_output


def test_search_keeps_initial_results_when_targeted_fallback_is_empty(monkeypatch, caplog):
    initial_result = {
        "title": "AI Hackathon announcement",
        "snippet": "Student AI hackathon announced by organizer.",
        "link": "https://www.linkedin.com/posts/organizer",
        "listing_quality": "Social media — secondary source",
        "relevance_score": 1,
        "position": 1,
    }
    calls = []

    async def fake_serpapi_search(query, request):
        calls.append(query)
        return [initial_result.copy()] if len(calls) == 1 else []

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        payload = asyncio.run(app.search(
            app.SearchRequest(topic="AI", opportunity_type="Hackathons", location="India", student_level="Undergraduate")
        ))

    assert len(calls) == 2
    assert len(payload["results"]) == 1
    assert payload["results"][0]["link"] == initial_result["link"]
    assert "follow-up search could not be completed" not in payload.get("search_message", "")
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "Official source fallback outcome=empty" in log_output
    assert "reason=no_accepted_results" in log_output
    assert "initial_results_retained=true" in log_output


def test_expired_deadline_overrides_open_and_report_keeps_same_evidence(monkeypatch):
    past_deadline = (date.today() - timedelta(days=1)).isoformat()
    results = [
        {
            "title": f"AI Hackathon {index}",
            "snippet": "Organizer registration page.",
            "source": f"events{index}.example.org",
            "link": f"https://events{index}.example.org/register/{index}",
            "listing_quality": "Specific opportunity page",
            "relevance_score": 10 - index,
            "position": index,
            "deadline": past_deadline,
            "opportunity_status": "deadline_upcoming",
        }
        for index in (1, 2)
    ]
    results[0]["application_status"] = "open"

    async def fake_serpapi_search(*args, **kwargs):
        return results

    async def fake_verify_sources(found):
        return found

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "Summary", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    payload = asyncio.run(app.search(
        app.SearchRequest(topic="AI", opportunity_type="Hackathons", location="India", student_level="Undergraduate")
    ))

    expired = payload["results"][0]
    row = payload["report_rows"][0]
    assert expired["opportunity_status"] == "potentially_expired"
    assert expired["application_status"] == "unknown"
    assert "deadline has passed" in expired["application_status_note"]
    assert past_deadline in row["deadline_status"]
    assert row["source"] == expired["source"]
    assert row["application_status"] == "Unknown"
    assert "No current, actionable opportunities" in payload["search_message"]


def test_deduplicate_removes_duplicate_urls_and_titles():
    items = [
        {"title": "AI internship", "link": "https://example.com/internship"},
        {"title": "AI internship", "link": "https://example.com/internship?utm_source=test"},
        {"title": "Different title", "link": "https://example.com/internship"},
        {"title": "Another internship", "link": "https://example.com/other"},
    ]

    unique = app.deduplicate(items)
    assert len(unique) == 2
    assert {item["title"] for item in unique} == {"AI internship", "Another internship"}


def test_extract_page_deadline_rejects_non_application_dates():
    page = "Event date: 30 May 2025. The announcement was posted on 12 April 2025."
    assert app.extract_page_deadline(page) is None

    deadline_page = "Application deadline: 30 May 2025. Last date to apply is 31 May 2025."
    parsed = app.extract_page_deadline(deadline_page)
    assert parsed is not None
    assert parsed.isoformat() == "2025-05-30"


def test_relevance_and_filter_excludes_document_and_stale_pages():
    request = type("Req", (), {"opportunity_type": "Hackathons", "topic": "AI", "location": "India", "student_level": "Undergraduate"})()

    doc_result = {"title": "AI Hackathon Guide", "snippet": "How to build an AI hackathon team", "link": "https://www.scribd.com/document/12345/ai-hackathon-guide"}
    score, reason = app.relevance_and_filter(doc_result, request)
    assert score == 0
    assert "document" in reason.lower() or "mirror" in reason.lower()

    stale_result = {"title": "Upcoming AI Hackathon 2024", "snippet": "Register for our upcoming hackathons in India", "link": "https://example.com/upcoming-ai-hackathons"}
    score, reason = app.relevance_and_filter(stale_result, request)
    assert score == 0
    assert "stale" in reason.lower() or "past" in reason.lower() or "current" in reason.lower()


def test_search_returns_helpful_message_when_no_strong_matches(monkeypatch):
    async def fake_serpapi_search(*args, **kwargs):
        return []

    async def fake_verify_sources(results):
        return results

    async def fake_groq_summary(*args, **kwargs):
        return {"summary": "## AI summary unavailable", "recommendations": [], "status": "search_only"}

    monkeypatch.setattr(app, "serpapi_search", fake_serpapi_search)
    monkeypatch.setattr(app, "verify_sources", fake_verify_sources)
    monkeypatch.setattr(app, "groq_summary", fake_groq_summary)

    payload = asyncio.run(app.search(
        app.SearchRequest(topic="AI security", opportunity_type="Jobs", location="India", student_level="Undergraduate")
    ))

    assert payload["results"] == []
    assert "No strong individual employer-linked job vacancies" in payload["search_message"]


def test_build_overview_rows_preserves_one_row_for_malformed_text():
    results = [{
        "title": "LinkedIn AI | Internship\n2026\n● Apply now",
        "snippet": "- Deadline: 15 Aug 2026\n| Official company page with open application.",
        "source": "linkedin.com/company/example",
        "link": "https://www.linkedin.com/company/example/jobs",
        "listing_quality": "Possible direct listing",
        "source_check_status": "checked",
        "application_status": "open",
        "opportunity_status": "deadline_upcoming",
        "deadline": "2026-08-15",
    }]

    rows = app.build_overview_rows(results)

    assert len(rows) == 1
    assert rows[0]["title"] == "LinkedIn AI Internship 2026 Apply now"
    assert "|" not in rows[0]["title"]
    assert "|" not in rows[0]["key_points"]
    assert rows[0]["source_check"] == "Readable; identity unverified"
    assert rows[0]["application_status"] == "Open"
    assert rows[0]["deadline_status"] == "Deadline Upcoming — 2026-08-15"


def test_report_rows_distinguish_readable_page_from_verified_identity():
    past_deadline = (date.today() - timedelta(days=2)).isoformat()
    result = {
        "title": "Graduate Security Analyst at Acme",
        "source": "Indeed",
        "link": "https://indeed.com/viewjob?id=1",
        "snippet": "Applications are open.",
        "listing_quality": "Individual job portal listing — secondary source",
        "source_check_status": "checked",
        "application_status": "unknown",
        "deadline": past_deadline,
        "opportunity_status": "potentially_expired",
        "source_verified": False,
        "employer_source_verified": False,
    }

    row = app.build_overview_rows([result])[0]

    assert row["source"] == result["source"]
    assert row["title"] == result["title"]
    assert row["listing_type"] == result["listing_quality"]
    assert row["source_check"] == "Readable; identity unverified"
    assert row["application_status"] == "Unknown"
    assert row["deadline_status"] == f"Potentially Expired — {past_deadline}"


def test_groq_request_uses_server_side_bearer_key_without_exposing_it(monkeypatch):
    api_key = "mock-groq-secret-for-test"
    captured = {}

    class GroqResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{
                    "message": {"content": "Evidence-based summary."},
                    "finish_reason": "stop",
                }]
            }

    class GroqClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = json
            return GroqResponse()

    monkeypatch.setattr(app, "GROQ_API_KEY", api_key)
    monkeypatch.setattr(app.httpx, "AsyncClient", lambda **kwargs: GroqClient())

    payload = asyncio.run(app.groq_summary(
        app.SearchRequest(
            topic="AI agents",
            opportunity_type="Hackathons",
            location="India",
            student_level="Undergraduate",
        ),
        [{
            "title": "AI agent hackathon",
            "link": "https://events.example.org/hackathon",
            "source": "Example events",
            "snippet": "Student event listing.",
            "application_status": "unknown",
            "deadline_verified": False,
        }],
    ))

    assert captured["headers"]["Authorization"] == f"Bearer {api_key}"
    assert payload["status"] == "ai_enabled"
    assert payload["summary"] == "Evidence-based summary."
    assert api_key not in str(payload)


def test_deadline_date_without_status_is_not_reported_as_verified():
    row = app.build_overview_rows([{
        "title": "Analyst role",
        "deadline": "2027-01-15",
        "application_status": "unknown",
    }])[0]

    assert row["deadline_status"] == "Unknown — 2027-01-15"


def test_serpapi_search_raises_on_api_failures(monkeypatch):
    async def fake_get(*args, **kwargs):
        raise app.httpx.RequestError("offline")

    monkeypatch.setattr(app.httpx.AsyncClient, "get", fake_get)
    with pytest.raises(HTTPException):
        asyncio.run(app.serpapi_search("test query", type("Req", (), {"opportunity_type": "Jobs", "topic": "AI", "location": "India", "student_level": "Undergraduate"})()))


def test_serpapi_search_requires_api_key(monkeypatch):
    monkeypatch.setattr(app, "SERPAPI_KEY", "")
    with pytest.raises(HTTPException, match="SERPAPI_KEY"):
        asyncio.run(app.serpapi_search("test query", type("Req", (), {"opportunity_type": "Jobs", "topic": "AI", "location": "India", "student_level": "Undergraduate"})()))


def test_serpapi_search_rejects_malformed_response_shape_without_logging_query(monkeypatch, caplog):
    class MalformedResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return ["unexpected", "response"]

    monkeypatch.setattr(app, "SERPAPI_KEY", "test-key-not-for-logging")
    monkeypatch.setattr(
        app.httpx,
        "AsyncClient",
        lambda **kwargs: FakeSerpApiClient(MalformedResponse()),
    )
    request = make_job_request(topic="private live-search phrase")

    with caplog.at_level("WARNING", logger="opportunity_radar.search"):
        with pytest.raises(HTTPException, match="invalid response"):
            asyncio.run(app.serpapi_search("private live-search phrase", request))

    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "reason=invalid_response_shape" in log_output
    assert "private live-search phrase" not in log_output
    assert "test-key-not-for-logging" not in log_output


def test_serpapi_search_skips_malformed_candidates_and_logs_counts_safely(monkeypatch, caplog):
    class MalformedCandidatesResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"organic_results": [None, "not-a-result"]}

    monkeypatch.setattr(app, "SERPAPI_KEY", "test-key-not-for-logging")
    monkeypatch.setattr(
        app.httpx,
        "AsyncClient",
        lambda **kwargs: FakeSerpApiClient(MalformedCandidatesResponse()),
    )

    with caplog.at_level("INFO", logger="opportunity_radar.search"):
        results = asyncio.run(app.serpapi_search(
            "private live-search phrase",
            make_job_request(topic="private live-search phrase"),
        ))

    assert results == []
    log_output = "\n".join(record.getMessage() for record in caplog.records)
    assert "malformed_candidate" in log_output
    assert "raw=2" in log_output
    assert "private live-search phrase" not in log_output
    assert "test-key-not-for-logging" not in log_output
