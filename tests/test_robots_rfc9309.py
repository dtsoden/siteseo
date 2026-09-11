"""RFC 9309 conformance for the robots evaluator.

The AI crawler matrix is only as good as this. Python's urllib.robotparser does
not implement RFC 9309 longest-match rule precedence, which is exactly the case
that decides whether a crawler is blocked, so the last test here records the
difference rather than trusting the standard library.
"""

from __future__ import annotations

import pytest

import robots_check


def parse(text: str, status: int = 200):
    return robots_check.parse(text, fetch_status=status)


# ---------------------------------------------------------------- precedence


def test_longest_matching_rule_wins_over_order():
    """RFC 9309 2.2.2: the most specific rule wins, not the first or the last."""
    robots = parse(
        "User-agent: *\n"
        "Disallow: /a/\n"
        "Allow: /a/b/\n"
    )
    assert robots.allowed("anybot", "/a/b/page") is True
    assert robots.allowed("anybot", "/a/other") is False


def test_longest_match_wins_even_when_disallow_comes_last():
    robots = parse(
        "User-agent: *\n"
        "Allow: /docs/public/\n"
        "Disallow: /docs/\n"
    )
    assert robots.allowed("anybot", "/docs/public/x") is True
    assert robots.allowed("anybot", "/docs/private/x") is False


def test_equally_specific_rules_resolve_to_allow():
    """RFC 9309 2.2.2: a tie between allow and disallow goes to allow."""
    robots = parse(
        "User-agent: *\n"
        "Disallow: /page\n"
        "Allow: /page\n"
    )
    assert robots.allowed("anybot", "/page") is True


# ---------------------------------------------------------------- group choice


def test_longest_user_agent_token_wins():
    robots = parse(
        "User-agent: *\n"
        "Disallow: /\n"
        "\n"
        "User-agent: Claude\n"
        "Allow: /\n"
        "\n"
        "User-agent: Claude-SearchBot\n"
        "Disallow: /private/\n"
    )
    # The longer token is the more specific group, so its rules apply alone.
    assert robots.allowed("Claude-SearchBot", "/") is True
    assert robots.allowed("Claude-SearchBot", "/private/x") is False
    # A different Anthropic crawler falls to the shorter token, not to "*".
    assert robots.allowed("Claude-User", "/anything") is True


def test_wildcard_group_used_only_when_no_token_matches():
    robots = parse(
        "User-agent: *\n"
        "Disallow: /\n"
        "\n"
        "User-agent: GPTBot\n"
        "Allow: /\n"
    )
    assert robots.allowed("GPTBot", "/") is True
    assert robots.allowed("SomeOtherBot", "/") is False


def test_user_agent_matching_is_case_insensitive():
    robots = parse("User-agent: gptbot\nDisallow: /\n")
    assert robots.allowed("GPTBot", "/") is False


def test_user_agent_line_after_rules_starts_a_new_group():
    robots = parse(
        "User-agent: a\n"
        "Disallow: /x\n"
        "User-agent: b\n"
        "Disallow: /y\n"
    )
    assert len(robots.groups) == 2
    assert robots.allowed("a", "/y") is True
    assert robots.allowed("b", "/x") is True


def test_consecutive_user_agent_lines_share_one_group():
    robots = parse(
        "User-agent: a\n"
        "User-agent: b\n"
        "Disallow: /x\n"
    )
    assert len(robots.groups) == 1
    assert robots.allowed("a", "/x") is False
    assert robots.allowed("b", "/x") is False


# ---------------------------------------------------------------- patterns


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("/fish", "/fish.html", True),
        ("/fish", "/fishheads/", True),
        ("/fish", "/Fish.asp", False),
        ("/fish/", "/fish/salmon.htm", True),
        ("/fish/", "/fish.html", False),
        ("/*.php", "/index.php", True),
        ("/*.php", "/windows.PHP", False),
        ("/*.php$", "/filename.php", True),
        ("/*.php$", "/filename.php?parameters", False),
        ("/fish*.php", "/fish.php", True),
        ("/fish*.php", "/fishheads/catfish.php?parameters", True),
        ("/$", "/", True),
        ("/$", "/page", False),
    ],
)
def test_path_matching(pattern, path, expected):
    assert robots_check._pattern_matches(pattern, path) is expected


def test_empty_disallow_grants_access():
    robots = parse("User-agent: *\nDisallow:\n")
    assert robots.allowed("anybot", "/anything") is True


# ---------------------------------------------------------------- fetch status


def test_server_error_means_disallow_all():
    """RFC 9309 2.3.1.4: a 5xx on robots.txt is treated as full disallow."""
    robots = parse("User-agent: *\nAllow: /\n", status=503)
    assert robots.allowed("anybot", "/") is False


def test_missing_robots_means_no_restrictions():
    robots = parse("", status=404)
    assert robots.allowed("anybot", "/anything") is True


# ---------------------------------------------------------------- parse errors


def test_line_without_colon_is_reported_not_silently_dropped():
    robots = parse("User-agent: *\nDisallow /missing-colon\n")
    assert any("field: value" in error.reason for error in robots.errors)


def test_rule_before_any_user_agent_is_reported():
    robots = parse("Disallow: /\nUser-agent: *\nAllow: /\n")
    assert any("before any User-agent" in error.reason for error in robots.errors)


def test_sitemap_lines_are_collected():
    robots = parse("User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n")
    assert robots.sitemaps == ["https://example.com/sitemap.xml"]


def test_unknown_directives_are_ignored_without_error():
    robots = parse("User-agent: *\nCrawl-delay: 10\nHost: example.com\nAllow: /\n")
    assert robots.errors == []


# ------------------------------------------------- why we did not use stdlib


def test_stdlib_robotparser_is_order_dependent_and_we_are_not():
    """Documents the reason this module exists.

    urllib.robotparser returns the FIRST matching rule rather than the most
    specific one, so its answer changes when the same two rules are written in
    the other order. RFC 9309 says the longer pattern wins regardless of order.

    Both spellings below mean "everything under /docs/ is closed except
    /docs/public/". We answer "allowed" for both. The standard library answers
    "allowed" only when the Allow line happens to come first.

    If a future Python fixes this, this test fails and the decision to carry our
    own evaluator can be revisited.
    """
    from urllib.robotparser import RobotFileParser

    disallow_first = "User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\n"
    allow_first = "User-agent: *\nAllow: /docs/public/\nDisallow: /docs/\n"
    path = "/docs/public/x"

    def stdlib_says(text: str) -> bool:
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return parser.can_fetch("anybot", path)

    # We give the same answer either way, which is the point.
    assert parse(disallow_first).allowed("anybot", path) is True
    assert parse(allow_first).allowed("anybot", path) is True

    # The standard library does not.
    assert stdlib_says(allow_first) is True
    assert stdlib_says(disallow_first) is False, (
        "urllib.robotparser now applies RFC 9309 longest-match precedence. "
        "Re-evaluate whether robots_check still needs to exist."
    )


def test_rule_order_never_changes_our_answer():
    """The same rules in any order must produce the same decision."""
    orderings = [
        "User-agent: *\nDisallow: /a/\nAllow: /a/b/\nDisallow: /a/b/c/\n",
        "User-agent: *\nDisallow: /a/b/c/\nDisallow: /a/\nAllow: /a/b/\n",
        "User-agent: *\nAllow: /a/b/\nDisallow: /a/b/c/\nDisallow: /a/\n",
    ]
    for path, expected in (("/a/x", False), ("/a/b/x", True), ("/a/b/c/x", False)):
        answers = {parse(text).allowed("anybot", path) for text in orderings}
        assert answers == {expected}, f"{path} gave {answers}, expected {expected}"
