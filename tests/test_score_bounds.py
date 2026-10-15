"""Search health stays between 0 and 100 when errors name URLs never checked."""


def test_errors_on_unchecked_urls_do_not_count_against_checked_pages():
    import score

    findings = [
        # A broken link target and a sitemap entry that does not load are not
        # pages the crawl checked, so they cannot lower the clean share.
        {"id": "http.status_4xx", "module": "A", "score": "search",
         "severity": "error", "urls": ["https://x/missing"]},
        {"id": "sitemap.contains_non_200", "module": "A", "score": "search",
         "severity": "error", "urls": [f"https://x/gone-{i}" for i in range(9)]},
        {"id": "title.missing", "module": "B", "score": "search",
         "severity": "error", "urls": ["https://x/a"]},
    ]
    checked = [f"https://x/{name}" for name in "abcdefgh"]
    result = score.search_health(findings, urls_checked=8, checked_urls=checked)
    assert result.components["urls_with_errors"] == 1
    assert result.components["clean_share"] == 87.5
    assert "7 of 8 URLs" in result.basis


def test_clean_share_never_goes_negative_without_a_url_list():
    import score

    findings = [{"id": "http.status_4xx", "module": "A", "score": "search",
                 "severity": "error", "urls": [f"https://x/{i}" for i in range(12)]}]
    result = score.search_health(findings, urls_checked=8)
    assert result.components["clean_share"] == 0.0
    assert result.value == 0.0
