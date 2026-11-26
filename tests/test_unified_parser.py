from __future__ import annotations

from pathlib import Path

import pytest

from cyber_recall.parsers.unified import parse_unified

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = "notes/PreSecurity/PreSecurity-TryHackMe-Unified.md"

HEADER = "# PreSecurity - TryHackMe (Unified Notes)\n"
MODULE = "## Module 5 - Network Fundamentals\n"
UNIT = "### What is Networking?\n"
AR_HEADER = "#### 5. Active Recall & Self-Assessment\n"


def _parse(body: str) -> list:
    text = HEADER + MODULE + UNIT + AR_HEADER + body
    result = parse_unified(text, SOURCE)
    assert result.warnings == [], result.warnings
    return result.cards


def _one(body: str):
    cards = _parse(body)
    assert len(cards) == 1
    return cards[0]


def test_variant_a_numbered_list_with_italic_answer():
    card = _one(
        "1. **What is the fundamental difference between Offensive and Defensive Security?**\n"
        "    - *Answer:* Offensive security simulates attacks, defensive security blocks them.\n"
    )
    assert card.front == "What is the fundamental difference between Offensive and Defensive Security?"
    assert card.back == "Offensive security simulates attacks, defensive security blocks them."


def test_variant_b_bold_question_with_bullet_answer():
    card = _one(
        "**5.1. What is the difference between a private network and a public network?**\n\n"
        "- **Answer:** A private network is a localized collection of devices.\n"
    )
    assert card.front == "What is the difference between a private network and a public network?"
    assert card.back == "A private network is a localized collection of devices."


def test_variant_b_same_line_answer_label():
    card = _one(
        "**5.1. What enables handling an unexpected increase in access?Answer:** "
        "**Scalability.** It allocates more resources on the fly.\n"
    )
    assert card.front == "What enables handling an unexpected increase in access?"
    assert card.back == "**Scalability.** It allocates more resources on the fly."


def test_variant_b_same_line_inline_code_answer():
    card = _one(
        "**6.1. What is the name of the function used to display text on the screen?**`print()`\n"
    )
    assert card.front == "What is the name of the function used to display text on the screen?"
    assert card.back == "`print()`"


def test_variant_b_plain_paragraph_answer():
    card = _one(
        "**5.3. Why must applications rely on System Calls?**\n"
        "If applications had direct access, a malicious app could overwrite system memory.\n"
    )
    assert card.front == "Why must applications rely on System Calls?"
    assert card.back == "If applications had direct access, a malicious app could overwrite system memory."


def test_variant_c_blockquote_answer_with_prefix():
    card = _one(
        "**5.1. What is the fundamental difference between a Packet and a Frame?**\n\n"
        "> **Answer:** A Packet operates at OSI Layer 3 and contains IP addressing.\n"
        ">\n"
    )
    assert card.front == "What is the fundamental difference between a Packet and a Frame?"
    assert card.back == "A Packet operates at OSI Layer 3 and contains IP addressing."


def test_variant_c_blockquote_answer_without_prefix():
    card = _one(
        "**5.1. Why are hexadecimal values heavily used in cybersecurity tools?**\n\n"
        "> Hexadecimal is highly efficient for human readability.\n"
        ">\n"
    )
    assert card.front == "Why are hexadecimal values heavily used in cybersecurity tools?"
    assert card.back == "Hexadecimal is highly efficient for human readability."


def test_variant_d_bullet_question_with_bullet_answer():
    card = _one(
        "- **5.1. Question:** What is the core functional difference between a Switch and a Router?\n"
        "    - **Answer:** A Switch connects devices within the same local network.\n"
    )
    assert card.front == "What is the core functional difference between a Switch and a Router?"
    assert card.back == "A Switch connects devices within the same local network."


def test_variant_e_h5_question_with_bold_answer():
    card = _one(
        "##### 5.1. Why is it safe for cryptographic algorithms to be completely public?\n\n"
        "**Answer:** Under Kerckhoffs's Principle, security relies on the secret key.\n"
    )
    assert card.front == "Why is it safe for cryptographic algorithms to be completely public?"
    assert card.back == "Under Kerckhoffs's Principle, security relies on the secret key."


def test_code_block_inside_answer_is_preserved():
    card = _one(
        "**5.3. Write a SQL query that retrieves the `drink` and `price` columns.**\n\n"
        "- **Answer:**\n\n"
        "    ```sql\n"
        "    SELECT drink, price\n"
        "    FROM Orders\n"
        "    ```\n\n"
        "    `DESC` sorts from most expensive to cheapest.\n"
    )
    assert "```sql" in card.back
    assert "SELECT drink, price" in card.back
    assert "FROM Orders" in card.back
    assert "`DESC` sorts from most expensive to cheapest." in card.back


def test_noise_after_blockquote_is_trimmed():
    cards = _parse(
        "**5.1. Why is an accurate asset inventory mandatory?**\n\n"
        "> **Answer:** You cannot protect systems you do not know exist.\n"
        ">\n\n"
        "Explore how independent Defense in Depth layers interact:\n"
        "For a guided visual walkthrough, check out the video.\n"
    )
    assert len(cards) == 1
    assert cards[0].back == "You cannot protect systems you do not know exist."


def test_noise_after_bullet_answer_is_trimmed():
    cards = _parse(
        "**5.5. At which two OSI layers can switches operate?**\n\n"
        "- **Answer:** Switches operate at **Layer 2** and **Layer 3**.\n\n"
        "Explore how **Port Forwarding**, **Firewall filtering (port 80)**, and **VLAN segmentation**"
        " interact in real time as a packet travels:\n"
    )
    assert len(cards) == 1
    assert cards[0].back == "Switches operate at **Layer 2** and **Layer 3**."


def test_indented_paragraph_after_bullet_is_kept():
    # An indented continuation of a bullet answer is genuine content (not noise).
    cards = _parse(
        "**5.3. Write a SQL query.**\n\n"
        "- **Answer:**\n"
        "    ```sql\n"
        "    SELECT drink, price\n"
        "    FROM Orders\n"
        "    ```\n"
        "    `DESC` sorts from most expensive to cheapest.\n"
    )
    assert len(cards) == 1
    assert "SELECT drink, price" in cards[0].back
    assert "`DESC` sorts from most expensive to cheapest." in cards[0].back


def test_code_block_preserves_relative_indentation():
    card = _one(
        "**5.1. Write a function that checks parity.**\n\n"
        "- **Answer:**\n\n"
        "    ```python\n"
        "    def is_even(n):\n"
        "        if n % 2 == 0:\n"
        "            return True\n"
        "        return False\n"
        "    ```\n"
    )
    assert "def is_even(n):" in card.back
    assert "    if n % 2 == 0:" in card.back
    assert "        return True" in card.back
    assert "    return False" in card.back


def test_multiple_questions_are_all_parsed():
    cards = _parse(
        "1. **First question?**\n"
        "    - *Answer:* First answer.\n"
        "2. **Second question?**\n"
        "    - *Answer:* Second answer.\n"
    )
    assert [c.front for c in cards] == ["First question?", "Second question?"]


def test_question_numbering_is_stripped_consistently():
    cards = _parse(
        "1. **What is X?**\n    - *Answer:* X is one.\n"
        "2. **What is Y?**\n    - *Answer:* Y is two.\n"
    )
    assert all(not c.front[0].isdigit() for c in cards)


def test_full_fixture_parses_without_warnings():
    text = (FIXTURES / "unified_sample.md").read_text(encoding="utf-8")
    result = parse_unified(text, SOURCE)
    assert result.warnings == [], result.warnings


def test_full_fixture_card_count():
    text = (FIXTURES / "unified_sample.md").read_text(encoding="utf-8")
    result = parse_unified(text, SOURCE)
    # 2 (M1) + 3 (What is Networking) + 2 (Packets) + 1 (Intro to LAN)
    #   + 1 (SQL) + 1 (Crypto) + 1 (Defender) + 1 (Computer types) = 12
    assert len(result.cards) == 12
    assert all(c.card_type == "recall" for c in result.cards)
